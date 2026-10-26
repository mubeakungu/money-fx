import json
from decimal import Decimal

import httpx
import pytest

from app import brokers, models
from app.bots import backtest, run_bots, step
from app.brokers import OandaBroker, PaperBroker
from app.database import SessionLocal
from app.strategies import STRATEGIES, rsi, sma, validate


def bars(closes, start=0, step_s=60):
    return [{"time": start + i * step_s, "open": c, "high": c, "low": c, "close": c} for i, c in enumerate(closes)]


def test_indicators():
    assert sma([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]
    up = rsi([float(i) for i in range(30)], 14)
    assert up[13] is None and up[14] == 100.0


def test_sma_cross_signals():
    closes = [10] * 30 + [10 + i for i in range(1, 15)] + [24 - i * 2 for i in range(1, 15)]
    sig = STRATEGIES["sma_cross"].signals(bars(closes), {"fast": 3, "slow": 8})
    assert "buy" in sig and "sell" in sig and sig.index("buy") < sig.index("sell")


def test_validation():
    with pytest.raises(ValueError):
        validate("sma_cross", {"fast": 30, "slow": 10})
    with pytest.raises(ValueError):
        validate("rsi", {"period": 1})
    assert validate("breakout", {}) == {"lookback": 20}


def test_backtest_stop_loss_and_metrics(monkeypatch):
    candles = bars([100.0] * 10 + [110.0, 120.0, 90.0, 95.0])
    # Buy on candle 10, then the price collapses through the 5% stop.
    monkeypatch.setattr(STRATEGIES["breakout"], "signals", lambda c, p: [None] * 10 + ["buy"] + [None] * 3)
    r = backtest(candles, "breakout", {"lookback": 5}, 5, None, 1000, 10_000)
    t = r["trade_list"][0]
    assert t["reason"] == "stop_loss" and t["exit_price"] == 90.0  # gapped below the 104.5 stop: fills at open
    assert r["trades"] == 1 and r["win_rate_pct"] == 0 and r["total_return_pct"] < 0
    assert r["max_drawdown_pct"] > 0 and r["equity_curve"][-1]["value"] == r["final_equity"]


def test_backtest_endpoint(client, user):
    body = {"symbol": "EURUSD", "strategy": "sma_cross", "params": {"fast": 5, "slow": 20}, "interval": "5m",
            "trade_size_usd": "5000", "stop_loss_pct": 1, "take_profit_pct": 2, "bars": 600}
    r = client.post("/api/bots/backtest", json=body, headers=user)
    assert r.status_code == 200, r.text
    res = r.json()
    assert len(res["equity_curve"]) == 600 and res["trades"] > 0
    assert client.post("/api/bots/backtest", json={**body, "params": {"fast": 50, "slow": 20}}, headers=user).status_code == 400


@pytest.fixture
def forced(monkeypatch):
    """Drive a strategy's signal and the candle clock by hand."""
    state = {"signal": None, "t": 1_000_000}
    monkeypatch.setattr(STRATEGIES["rsi"], "signals", lambda c, p: [None] * (len(c) - 1) + [state["signal"]])
    monkeypatch.setattr(PaperBroker, "closed_candles",
                        lambda self, s, i, n: bars([1.0] * 5, start=state["t"] - 240))
    return state


def test_paper_bot_lifecycle(client, user, forced):
    client.post("/api/wallet/deposit", json={"amount": "20000"}, headers=user)
    r = client.post("/api/bots", json={"name": "Gold RSI", "symbol": "XAUUSD", "strategy": "rsi",
                                       "trade_size_usd": "5000", "interval": "1m"}, headers=user)
    bot_id = r.json()["id"]
    assert r.json()["status"] == "stopped"
    assert client.post(f"/api/bots/{bot_id}/start", headers=user).json()["status"] == "running"

    with SessionLocal() as db:
        bot = db.get(models.Bot, bot_id)
        forced["signal"] = "buy"
        step(db, bot)  # first pass only starts watching
        assert bot.position_qty == 0
        forced["t"] += 60
        step(db, bot)
        assert bot.position_qty > 0 and bot.entry_price > 0
        step(db, bot)  # same candle again: no double buy
        forced["signal"] = "sell"
        forced["t"] += 60
        step(db, bot)
        assert bot.position_qty == 0 and bot.trades_closed == 1
        db.commit()

    detail = client.get(f"/api/bots/{bot_id}", headers=user).json()
    assert [t["action"] for t in detail["trades"]] == ["close", "open"]
    orders = client.get("/api/orders", headers=user).json()
    assert [o["side"] for o in orders[:2]] == ["sell", "buy"] and orders[0]["symbol"] == "XAUUSD"
    assert client.delete(f"/api/bots/{bot_id}", headers=user).status_code == 400  # still running
    client.post(f"/api/bots/{bot_id}/stop", headers=user)
    assert client.delete(f"/api/bots/{bot_id}", headers=user).status_code == 204


def test_paper_stop_loss_and_manual_close(client, user, forced, monkeypatch):
    client.post("/api/wallet/deposit", json={"amount": "20000"}, headers=user)
    bot_id = client.post("/api/bots", json={"name": "SL", "symbol": "AAPL", "strategy": "rsi", "trade_size_usd": "1000",
                                            "stop_loss_pct": 2, "interval": "1m"}, headers=user).json()["id"]
    client.post(f"/api/bots/{bot_id}/start", headers=user)
    with SessionLocal() as db:
        bot = db.get(models.Bot, bot_id)
        step(db, bot)
        forced["signal"], forced["t"] = "buy", forced["t"] + 60
        step(db, bot)
        entry = bot.entry_price
        real_quote = PaperBroker.quote
        monkeypatch.setattr(PaperBroker, "quote", lambda self, s: {"bid": entry * Decimal("0.97"), "ask": entry})
        from app import trading
        monkeypatch.setattr(trading.feed, "quote", lambda s: {"bid": (entry * Decimal("0.97")).quantize(Decimal("0.01")),
                                                              "ask": entry, "mid": entry})
        forced["signal"] = None
        step(db, bot)
        assert bot.position_qty == 0
        db.commit()
        monkeypatch.setattr(PaperBroker, "quote", real_quote)
    trades = client.get(f"/api/bots/{bot_id}", headers=user).json()["trades"]
    assert trades[0]["reason"] == "stop_loss" and Decimal(trades[0]["pnl"]) < 0
    assert client.post(f"/api/bots/{bot_id}/close-position", headers=user).status_code == 400


def test_bot_errors_stop_after_retries(client, user):
    bot_id = client.post("/api/bots", json={"name": "Broke", "symbol": "BTCUSD", "strategy": "breakout",
                                            "trade_size_usd": "100000"}, headers=user).json()["id"]
    client.post(f"/api/bots/{bot_id}/start", headers=user)
    with SessionLocal() as db:
        bot = db.get(models.Bot, bot_id)
        bot.last_candle_time = 0
        db.commit()
    import app.bots as engine
    orig = STRATEGIES["breakout"].signals
    STRATEGIES["breakout"].signals = lambda c, p: [None] * (len(c) - 1) + ["buy"]
    try:
        for _ in range(5):
            with SessionLocal() as db:
                b = db.get(models.Bot, bot_id)
                b.last_candle_time = 0
                db.commit()
                run_bots(db)
    finally:
        STRATEGIES["breakout"].signals = orig
    d = client.get(f"/api/bots/{bot_id}", headers=user).json()
    assert d["bot"]["status"] == "error" and "Insufficient funds" in d["bot"]["error"]
    assert engine.MAX_CONSECUTIVE_ERRORS == 5


@pytest.fixture
def owner(client, user, monkeypatch):
    """Make the test user the OANDA account owner."""
    from app.routers import bots as bots_router
    email = client.get("/api/auth/me", headers=user).json()["email"]
    monkeypatch.setattr(bots_router, "OANDA_OWNER_EMAILS", {email})
    return user


def test_oanda_is_owner_only(client, user):
    r = client.post("/api/bots", json={"name": "x", "symbol": "EURUSD", "broker": "oanda", "strategy": "rsi",
                                       "trade_size_usd": "100"}, headers=user)
    assert r.status_code == 403
    r = client.post("/api/bots/backtest", json={"symbol": "EURUSD", "broker": "oanda", "strategy": "rsi",
                                                "trade_size_usd": "100"}, headers=user)
    assert r.status_code == 403
    assert client.get("/api/bots/brokers", headers=user).json()["oanda"]["allowed"] is False


def test_oanda_validation(client, owner):
    user = owner
    r = client.post("/api/bots", json={"name": "x", "symbol": "BTCUSD", "broker": "oanda", "strategy": "rsi",
                                       "trade_size_usd": "100"}, headers=user)
    assert r.status_code == 400 and "OANDA bots can trade" in r.json()["detail"]
    r = client.post("/api/bots", json={"name": "x", "symbol": "EURUSD", "broker": "oanda", "strategy": "rsi",
                                       "trade_size_usd": "100"}, headers=user)
    assert r.status_code == 201
    r = client.post(f"/api/bots/{r.json()['id']}/start", headers=user)
    assert r.status_code == 400 and "not connected" in r.json()["detail"]
    assert client.get("/api/bots/brokers", headers=user).json()["oanda"]["configured"] is False


class FakeOanda:
    """Just enough of the v20 API for the bot."""

    def __init__(self):
        self.requests = []
        self.trade_state = "OPEN"

    def __call__(self, request: httpx.Request):
        self.requests.append(request)
        path, m = request.url.path, request.method
        assert request.headers["Authorization"] == "Bearer tok"
        if path.endswith("/instruments"):
            return httpx.Response(200, json={"instruments": [
                {"name": "EUR_USD", "displayPrecision": 5, "tradeUnitsPrecision": 0, "minimumTradeSize": "1"}]})
        if path.endswith("/pricing"):
            return httpx.Response(200, json={"prices": [{"bids": [{"price": "1.10000"}], "asks": [{"price": "1.10010"}]}]})
        if path.endswith("/candles"):
            return httpx.Response(200, json={"candles": [
                {"time": f"{1000 + i * 60}.000000000", "complete": i < 3,
                 "mid": {"o": "1.1", "h": "1.2", "l": "1.0", "c": "1.1"}} for i in range(4)]})
        if path.endswith("/orders") and m == "POST":
            return httpx.Response(201, json={"orderFillTransaction": {
                "price": "1.10010", "units": "4545", "tradeOpened": {"tradeID": "77", "units": "4545", "price": "1.10010"}}})
        if path.endswith("/trades/77/close"):
            return httpx.Response(200, json={"orderFillTransaction": {"price": "1.10500", "pl": "22.27"}})
        if path.endswith("/trades/77"):
            t = {"id": "77", "state": self.trade_state, "price": "1.10010"}
            if self.trade_state == "CLOSED":
                t.update(averageClosePrice="1.08910", realizedPL="-50.00")
            return httpx.Response(200, json={"trade": t})
        return httpx.Response(404, json={"errorMessage": f"unexpected {m} {path}"})


@pytest.fixture
def oanda():
    fake = FakeOanda()
    brokers.set_oanda_broker(OandaBroker("tok", "001-001-1-001", "practice", transport=httpx.MockTransport(fake)))
    yield fake
    brokers.set_oanda_broker(None)


def test_oanda_broker(client, owner, oanda, monkeypatch):
    user = owner
    b = brokers.get_broker("oanda")
    candles = b.closed_candles("EURUSD", "1m", 300)
    assert len(candles) == 3 and candles[-1]["time"] == 1120

    bot_id = client.post("/api/bots", json={"name": "fx", "symbol": "EURUSD", "broker": "oanda", "strategy": "rsi",
                                            "trade_size_usd": "5000", "stop_loss_pct": 1, "take_profit_pct": 2,
                                            "interval": "1m"}, headers=user).json()["id"]
    assert client.post(f"/api/bots/{bot_id}/start", headers=user).status_code == 200
    monkeypatch.setattr(STRATEGIES["rsi"], "signals", lambda c, p: [None] * (len(c) - 1) + ["buy"])
    with SessionLocal() as db:
        bot = db.get(models.Bot, bot_id)
        bot.last_candle_time = 0
        step(db, bot)
        assert bot.external_trade_id == "77" and bot.position_qty == 4545
        order = json.loads([r for r in oanda.requests if r.method == "POST"][0].content)["order"]
        assert order["units"] == "4545" and order["instrument"] == "EUR_USD"
        assert order["stopLossOnFill"]["price"] == "1.08910" and order["takeProfitOnFill"]["price"] == "1.12210"

        oanda.trade_state = "CLOSED"  # OANDA's stop-loss fired while we were away
        step(db, bot)
        assert bot.position_qty == 0 and bot.realized_pnl == Decimal("-50")
        db.commit()
    trades = client.get(f"/api/bots/{bot_id}", headers=user).json()["trades"]
    assert trades[0]["reason"] == "stop_loss"
