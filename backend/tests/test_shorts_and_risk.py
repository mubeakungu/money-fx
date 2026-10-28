import json
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect, text

from app import database, models
from app.bots import backtest, step
from app.brokers import PaperBroker
from app.database import SessionLocal
from app.strategies import STRATEGIES

from tests.test_bots import bars, forced, oanda, owner  # noqa: F401  (fixtures)


def _bot(client, user, **kw):
    body = {"name": "b", "symbol": "XAUUSD", "strategy": "rsi", "trade_size_usd": "5000", "interval": "1m", **kw}
    r = client.post("/api/bots", json=body, headers=user)
    assert r.status_code == 201, r.text
    client.post(f"/api/bots/{r.json()['id']}/start", headers=user)
    return r.json()["id"]


def _wallet(client, user):
    return client.get("/api/wallet", headers=user).json()


def test_paper_bot_shorts_and_flips(client, user, forced):
    client.post("/api/wallet/deposit", json={"amount": "20000"}, headers=user)
    bot_id = _bot(client, user, direction="both")
    with SessionLocal() as db:
        bot = db.get(models.Bot, bot_id)
        step(db, bot)  # starts watching
        forced["signal"], forced["t"] = "sell", forced["t"] + 60
        step(db, bot)
        assert bot.position_side == "short" and bot.position_qty > 0
        db.commit()
        locked = Decimal(_wallet(client, user)["locked"])
        assert locked == pytest.approx(bot.entry_price * bot.position_qty)

        forced["signal"], forced["t"] = "buy", forced["t"] + 60
        step(db, bot)  # closes the short, then opens a long
        assert bot.position_side == "long" and bot.trades_closed == 1
        db.commit()
    w = _wallet(client, user)
    assert Decimal(w["locked"]) == 0
    trades = client.get(f"/api/bots/{bot_id}", headers=user).json()["trades"]
    assert [(t["action"], t["side"]) for t in trades] == [("open", "long"), ("close", "short"), ("open", "short")]
    assert Decimal(trades[1]["pnl"]) < 0  # the spread: bought back at the ask


def test_short_only_bot_ignores_buy_signals(client, user, forced):
    client.post("/api/wallet/deposit", json={"amount": "20000"}, headers=user)
    bot_id = _bot(client, user, direction="short")
    with SessionLocal() as db:
        bot = db.get(models.Bot, bot_id)
        step(db, bot)
        forced["signal"], forced["t"] = "buy", forced["t"] + 60
        step(db, bot)
        assert bot.position_qty == 0
        forced["signal"], forced["t"] = "sell", forced["t"] + 60
        step(db, bot)
        assert bot.position_side == "short"
        forced["signal"], forced["t"] = "buy", forced["t"] + 60
        step(db, bot)
        assert bot.position_qty == 0 and bot.trades_closed == 1


def test_paper_short_stop_loss(client, user, forced, monkeypatch):
    client.post("/api/wallet/deposit", json={"amount": "20000"}, headers=user)
    bot_id = _bot(client, user, direction="short", stop_loss_pct=1)
    with SessionLocal() as db:
        bot = db.get(models.Bot, bot_id)
        step(db, bot)
        forced["signal"], forced["t"] = "sell", forced["t"] + 60
        step(db, bot)
        entry = bot.entry_price
        monkeypatch.setattr(PaperBroker, "quote", lambda self, s: {"bid": entry * Decimal("1.02"), "ask": entry * Decimal("1.021")})
        forced["signal"] = None
        step(db, bot)
        assert bot.position_qty == 0 and bot.realized_pnl < 0
        db.commit()
    assert client.get(f"/api/bots/{bot_id}", headers=user).json()["trades"][0]["reason"] == "stop_loss"


def test_risk_sizing(client, user, forced):
    client.post("/api/wallet/deposit", json={"amount": "10000"}, headers=user)
    r = client.post("/api/bots", json={"name": "r", "symbol": "XAUUSD", "strategy": "rsi", "trade_size_usd": "5000",
                                       "risk_pct": 1}, headers=user)
    assert r.status_code == 400 and "stop-loss" in r.json()["detail"]
    # 1% of 10,000 at risk with a 2% stop: a 5,000 position, capped by the 3,000 maximum
    bot_id = _bot(client, user, trade_size_usd="3000", risk_pct=1, stop_loss_pct=2)
    bot2 = _bot(client, user, trade_size_usd="50000", risk_pct=1, stop_loss_pct=2)
    with SessionLocal() as db:
        for b in (bot_id, bot2):
            bot = db.get(models.Bot, b)
            bot.last_candle_time = 0
        forced["signal"] = "buy"
        b1, b2 = db.get(models.Bot, bot_id), db.get(models.Bot, bot2)
        step(db, b1)
        assert float(b1.position_qty * b1.entry_price) == pytest.approx(3000, rel=0.01)
        step(db, b2)  # the first bot spent 3,000 of the balance, so 1% of the 7,000 left is at risk
        assert float(b2.position_qty * b2.entry_price) == pytest.approx(7000 * 0.01 / 0.02, rel=0.01)


def test_daily_loss_limit(client, user, forced, monkeypatch):
    client.post("/api/wallet/deposit", json={"amount": "20000"}, headers=user)
    r = client.put("/api/bots/settings", json={"daily_loss_limit_usd": "10"}, headers=user)
    assert r.json()["daily_loss_limit_usd"] == "10"
    bot_id = _bot(client, user, direction="both")
    with SessionLocal() as db:
        bot = db.get(models.Bot, bot_id)
        step(db, bot)
        forced["signal"], forced["t"] = "buy", forced["t"] + 60
        step(db, bot)
        entry = bot.entry_price
        from app import trading
        monkeypatch.setattr(trading.feed, "quote", lambda s: {"bid": entry * Decimal("0.99"), "ask": entry * Decimal("0.991"),
                                                              "mid": entry})
        monkeypatch.setattr(PaperBroker, "quote", lambda self, s: {"bid": entry * Decimal("0.99"), "ask": entry * Decimal("0.991")})
        forced["signal"], forced["t"] = "sell", forced["t"] + 60
        step(db, bot)  # closes the long at a ~50 USD loss, then must not open the short
        assert bot.trades_closed == 1 and bot.position_qty == 0
        db.commit()
    s = client.get("/api/bots/settings", headers=user).json()
    assert Decimal(s["today_pnl_usd"]) < -10
    logs = client.get(f"/api/bots/{bot_id}", headers=user).json()["logs"]
    assert "Daily loss limit reached" in logs[0]["message"]
    assert client.put("/api/bots/settings", json={"daily_loss_limit_usd": None}, headers=user).json()["daily_loss_limit_usd"] is None


def test_oanda_short(client, owner, oanda, monkeypatch):  # noqa: F811
    bot_id = client.post("/api/bots", json={"name": "fx", "symbol": "EURUSD", "broker": "oanda", "strategy": "rsi",
                                            "trade_size_usd": "5000", "stop_loss_pct": 1, "take_profit_pct": 2,
                                            "direction": "short", "interval": "1m"}, headers=owner).json()["id"]
    client.post(f"/api/bots/{bot_id}/start", headers=owner)
    monkeypatch.setattr(STRATEGIES["rsi"], "signals", lambda c, p: [None] * (len(c) - 1) + ["sell"])
    with SessionLocal() as db:
        bot = db.get(models.Bot, bot_id)
        bot.last_candle_time = 0
        step(db, bot)
        order = json.loads([r for r in oanda.requests if r.method == "POST"][0].content)["order"]
        assert order["units"] == "-4545"  # 5000 / 1.10000 bid
        assert order["stopLossOnFill"]["price"] == "1.11100" and order["takeProfitOnFill"]["price"] == "1.07800"
        assert bot.position_side == "short" and bot.position_qty == 4545


def test_backtest_short():
    candles = bars([100.0] * 10 + [100.0, 90.0, 80.0, 85.0])
    STRATEGIES["breakout"].signals, orig = (lambda c, p: [None] * 10 + ["sell", None, "buy", None]), STRATEGIES["breakout"].signals
    try:
        long_only = backtest(candles, "breakout", {"lookback": 5}, None, None, 1000, 10_000)
        r = backtest(candles, "breakout", {"lookback": 5}, None, None, 1000, 10_000, direction="short")
        both = backtest(candles, "breakout", {"lookback": 5}, None, None, 1000, 10_000, direction="both")
    finally:
        STRATEGIES["breakout"].signals = orig
    assert long_only["trades"] == 0
    t = r["trade_list"][0]
    assert t["side"] == "short" and t["pnl"] == 200.0 and r["final_equity"] == 10_200
    assert both["trades"] == 1 and both["open_position"]  # flipped long at 80
    assert both["equity_curve"][-1]["value"] == pytest.approx(10_200 + 1000 / 80 * 5)


def test_add_missing_columns(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as c:
        c.execute(text("CREATE TABLE bots (id INTEGER PRIMARY KEY, name VARCHAR(80))"))
        c.execute(text("INSERT INTO bots (id, name) VALUES (1, 'old')"))
    monkeypatch.setattr(database, "engine", engine)
    database.add_missing_columns()
    cols = {c["name"] for c in inspect(engine).get_columns("bots")}
    assert {"direction", "risk_pct", "position_side"} <= cols
    with engine.connect() as c:
        assert c.execute(text("SELECT direction FROM bots")).scalar() == "long"
