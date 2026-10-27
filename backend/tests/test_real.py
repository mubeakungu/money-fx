from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import brokers
from app.brokers import OandaBroker
from tests import fake_oanda


@pytest.fixture
def real(client, user, monkeypatch):
    """The test user owns an OANDA account served by the fake v20 API."""
    from app.routers import bots as bots_router
    email = client.get("/api/auth/me", headers=user).json()["email"]
    monkeypatch.setattr(bots_router, "OANDA_OWNER_EMAILS", {email})
    fake_oanda.reset()
    b = OandaBroker("tok", "001-001", "practice")
    b.http = TestClient(fake_oanda.app, base_url="http://oanda", headers=dict(b.http.headers))
    brokers.set_oanda_broker(b)
    yield user
    brokers.set_oanda_broker(None)


def test_real_account_is_owner_only(client, user):
    assert client.get("/api/real/account", headers=user).status_code == 403


def test_real_trading_flow(client, real):
    h = real
    acct = client.get("/api/real/account", headers=h).json()
    assert acct["balance"] == "100000" and acct["environment"] == "practice"
    symbols = {i["symbol"] for i in client.get("/api/real/instruments", headers=h).json()}
    assert symbols == {"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "XAUUSD", "XAGUSD", "WTIUSD"}
    prices = client.get("/api/real/prices", headers=h).json()
    assert {p["symbol"] for p in prices} == symbols and all(Decimal(p["bid"]) < Decimal(p["ask"]) for p in prices)
    bars = client.get("/api/real/candles/XAUUSD?interval=5m&limit=50", headers=h).json()
    assert len(bars) == 50

    # Buy with stops, short-sell gold, then close both.
    r = client.post("/api/real/orders", json={"symbol": "EURUSD", "side": "buy", "units": "1000",
                                              "stop_loss_pct": 1, "take_profit_pct": 2}, headers=h)
    assert r.status_code == 201 and r.json()["status"] == "filled", r.text
    r2 = client.post("/api/real/orders", json={"symbol": "XAUUSD", "side": "sell", "units": "2"}, headers=h)
    assert r2.json()["status"] == "filled"
    trades = client.get("/api/real/trades", headers=h).json()
    by_sym = {t["symbol"]: t for t in trades}
    assert by_sym["EURUSD"]["side"] == "buy" and by_sym["EURUSD"]["stop_loss"] and by_sym["EURUSD"]["take_profit"]
    assert Decimal(by_sym["EURUSD"]["stop_loss"]) < Decimal(by_sym["EURUSD"]["open_price"]) < Decimal(by_sym["EURUSD"]["take_profit"])
    assert by_sym["XAUUSD"]["side"] == "sell" and by_sym["XAUUSD"]["units"] == "2"
    for t in trades:
        assert client.post(f"/api/real/trades/{t['id']}/close", headers=h).status_code == 200
    assert client.get("/api/real/trades", headers=h).json() == []
    closed = client.get("/api/real/trades?state=closed", headers=h).json()
    assert len(closed) == 2 and {c["units"] for c in closed} == {"1000", "2"} and all(c["close_price"] for c in closed)


def test_real_limit_orders(client, real):
    h = real
    r = client.post("/api/real/orders", json={"symbol": "GBPUSD", "side": "buy", "type": "limit", "units": "500",
                                              "limit_price": "0.5"}, headers=h)
    assert r.json()["status"] == "pending"
    pending = client.get("/api/real/orders", headers=h).json()
    assert pending[0]["symbol"] == "GBPUSD" and pending[0]["type"] == "limit"
    assert client.delete(f"/api/real/orders/{pending[0]['id']}", headers=h).status_code == 204
    assert client.get("/api/real/orders", headers=h).json() == []
    assert client.post("/api/real/orders", json={"symbol": "BTCUSD", "side": "buy", "units": "1"}, headers=h).status_code == 400
    assert client.post("/api/real/orders", json={"symbol": "GBPUSD", "side": "buy", "type": "limit", "units": "5"},
                       headers=h).status_code == 400
