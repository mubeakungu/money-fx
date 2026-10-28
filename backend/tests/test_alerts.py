import json

import httpx
import pytest

from app import alerts, models
from app.alerts import Telegram
from app.bots import run_bots, step
from app.database import SessionLocal

from tests.test_bots import forced  # noqa: F401  (fixture)


class FakeTelegram:
    def __init__(self):
        self.sent = []
        self.updates = []
        self.fail = False

    def __call__(self, request: httpx.Request):
        assert request.url.path.startswith("/botTOKEN/")
        method = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content or b"{}")
        if self.fail:
            return httpx.Response(200, json={"ok": False, "description": "Forbidden: bot was blocked by the user"})
        if method == "getMe":
            return httpx.Response(200, json={"ok": True, "result": {"username": "moneyfx_test_bot"}})
        if method == "getUpdates":
            return httpx.Response(200, json={"ok": True, "result": self.updates})
        if method == "sendMessage":
            self.sent.append((str(body["chat_id"]), body["text"]))
            return httpx.Response(200, json={"ok": True, "result": {}})
        return httpx.Response(404, json={"ok": False, "description": "not found"})


@pytest.fixture
def tg():
    fake = FakeTelegram()
    alerts.set_telegram(Telegram("TOKEN", transport=httpx.MockTransport(fake)))
    yield fake
    alerts.set_telegram(None)


def test_telegram_not_configured(client, user):
    assert client.get("/api/bots/settings", headers=user).json()["telegram"] == {"available": False, "connected": False}
    r = client.post("/api/bots/telegram/link", headers=user)
    assert r.status_code == 400 and "TELEGRAM_BOT_TOKEN" in r.json()["detail"]


def test_link_and_alerts(client, user, tg, forced):  # noqa: F811
    r = client.post("/api/bots/telegram/link", headers=user).json()
    assert r["url"] == f"https://t.me/moneyfx_test_bot?start={r['code']}"
    assert client.post("/api/bots/telegram/verify", headers=user).status_code == 400  # not pressed Start yet
    tg.updates = [{"update_id": 1, "message": {"text": "/start someone-else", "chat": {"id": 111}}},
                  {"update_id": 2, "message": {"text": f"/start {r['code']}", "chat": {"id": 4242}}}]
    s = client.post("/api/bots/telegram/verify", headers=user).json()
    assert s["telegram"]["connected"] is True and tg.sent[-1][0] == "4242"
    assert client.post("/api/bots/telegram/test", headers=user).status_code == 200

    client.post("/api/wallet/deposit", json={"amount": "20000"}, headers=user)
    bot_id = client.post("/api/bots", json={"name": "Gold", "symbol": "XAUUSD", "strategy": "rsi",
                                            "trade_size_usd": "1000", "interval": "1m"}, headers=user).json()["id"]
    client.post(f"/api/bots/{bot_id}/start", headers=user)
    with SessionLocal() as db:
        db.get(models.Bot, bot_id).last_candle_time = 0
        db.commit()
    tg.sent.clear()
    forced["signal"] = "buy"
    with SessionLocal() as db:
        run_bots(db)
    assert len(tg.sent) == 1 and tg.sent[0][0] == "4242"
    assert tg.sent[0][1].startswith("Gold · XAUUSD\n[Paper] Bought")

    tg.fail = True  # a Telegram outage must not break the bot
    forced["signal"], forced["t"] = "sell", forced["t"] + 60
    with SessionLocal() as db:
        run_bots(db)
        assert db.get(models.Bot, bot_id).trades_closed == 1
    client.post(f"/api/bots/{bot_id}/stop", headers=user)

    assert client.delete("/api/bots/telegram", headers=user).json()["telegram"]["connected"] is False


def test_rolled_back_trade_sends_nothing(client, user, tg, forced):  # noqa: F811
    with SessionLocal() as db:
        db.get(models.Account, client.get("/api/auth/me", headers=user).json()["account_id"]).telegram_chat_id = "999"
        db.commit()
    # No deposit: the paper order is rejected, the step rolls back, and no trade alert goes out
    bot_id = client.post("/api/bots", json={"name": "Broke", "symbol": "XAUUSD", "strategy": "rsi",
                                            "trade_size_usd": "1000", "interval": "1m"}, headers=user).json()["id"]
    client.post(f"/api/bots/{bot_id}/start", headers=user)
    with SessionLocal() as db:
        db.get(models.Bot, bot_id).last_candle_time = 0
        db.commit()
    forced["signal"] = "buy"
    tg.sent.clear()
    with SessionLocal() as db:
        run_bots(db)
    assert not any("Bought" in t for _, t in tg.sent)
    client.post(f"/api/bots/{bot_id}/stop", headers=user)
