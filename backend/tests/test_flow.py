from decimal import Decimal

from app.market import feed


def D(x):
    return Decimal(str(x))


def test_signup_deposit_order_portfolio(client, user):
    me = client.get("/api/auth/me", headers=user).json()
    assert me["full_name"] == "Test Trader" and me["account_status"] == "active"

    r = client.post("/api/wallet/deposit", json={"amount": "10000", "method": "card"}, headers=user)
    assert r.status_code == 201 and D(r.json()["balance_after"]) == 10000

    r = client.post("/api/orders", json={"symbol": "AAPL", "side": "buy", "quantity": "10"}, headers=user)
    assert r.status_code == 201, r.text
    order = r.json()
    assert order["status"] == "filled"
    cost = (D(order["filled_price"]) * 10).quantize(D("0.01"), rounding="ROUND_UP")

    wallet = client.get("/api/wallet", headers=user).json()
    assert D(wallet["balance"]) == 10000 - cost

    pf = client.get("/api/portfolio", headers=user).json()
    assert [p["symbol"] for p in pf["positions"]] == ["AAPL"]
    assert D(pf["positions"][0]["quantity"]) == 10
    assert D(pf["net_deposits"]) == 10000
    assert D(pf["equity"]) == D(pf["cash"]) + D(pf["positions_value"])

    r = client.post("/api/orders", json={"symbol": "AAPL", "side": "sell", "quantity": "4"}, headers=user)
    assert r.json()["status"] == "filled"
    pf = client.get("/api/portfolio", headers=user).json()
    assert D(pf["positions"][0]["quantity"]) == 6
    txns = client.get("/api/wallet/transactions", headers=user).json()
    assert [t["type"] for t in txns] == ["trade_sell", "trade_buy", "deposit"]


def test_all_asset_classes_tradable(client, user):
    client.post("/api/wallet/deposit", json={"amount": "500000"}, headers=user)
    for sym, qty in [("EURUSD", "1000"), ("BTCUSD", "0.01"), ("NVDA", "2.5"), ("XAUUSD", "0.5")]:
        r = client.post("/api/orders", json={"symbol": sym, "side": "buy", "quantity": qty}, headers=user)
        assert r.json()["status"] == "filled", r.text
    alloc = client.get("/api/portfolio", headers=user).json()["allocation"]
    assert set(alloc) == {"cash", "forex", "crypto", "stock", "commodity"}


def test_rejections(client, user):
    r = client.post("/api/orders", json={"symbol": "BTCUSD", "side": "buy", "quantity": "1"}, headers=user)
    assert r.json()["status"] == "rejected" and "Insufficient funds" in r.json()["reject_reason"]
    r = client.post("/api/orders", json={"symbol": "TSLA", "side": "sell", "quantity": "1"}, headers=user)
    assert r.json()["status"] == "rejected" and "Insufficient holdings" in r.json()["reject_reason"]
    r = client.post("/api/orders", json={"symbol": "EURUSD", "side": "buy", "quantity": "1.5"}, headers=user)
    assert r.status_code == 400
    r = client.post("/api/wallet/withdraw", json={"amount": "5"}, headers=user)
    assert r.status_code == 400


def test_limit_order_reserves_and_cancels(client, user):
    client.post("/api/wallet/deposit", json={"amount": "1000"}, headers=user)
    low = (feed.quote("MSFT")["ask"] * D("0.5")).quantize(D("0.01"))
    r = client.post("/api/orders", json={"symbol": "MSFT", "side": "buy", "type": "limit",
                                         "quantity": "2", "limit_price": str(low)}, headers=user)
    order = r.json()
    assert order["status"] == "open"
    w = client.get("/api/wallet", headers=user).json()
    assert D(w["locked"]) == low * 2 and D(w["available"]) == 1000 - low * 2
    assert client.post("/api/wallet/withdraw", json={"amount": "1000"}, headers=user).status_code == 400
    r = client.delete(f"/api/orders/{order['id']}", headers=user)
    assert r.json()["status"] == "cancelled"
    assert D(client.get("/api/wallet", headers=user).json()["locked"]) == 0


def test_marketable_limit_fills_and_matcher(client, user):
    from app.database import SessionLocal
    from app.trading import match_open_orders
    client.post("/api/wallet/deposit", json={"amount": "50000"}, headers=user)
    high = (feed.quote("ETHUSD")["ask"] * D("1.5")).quantize(D("0.01"))
    r = client.post("/api/orders", json={"symbol": "ETHUSD", "side": "buy", "type": "limit",
                                         "quantity": "1", "limit_price": str(high)}, headers=user)
    assert r.json()["status"] == "filled"
    assert D(r.json()["filled_price"]) < high  # filled at market, not at the limit
    assert D(client.get("/api/wallet", headers=user).json()["locked"]) == 0
    # A sell limit far below market rests only if not marketable; one above rests until matched.
    far = (feed.quote("ETHUSD")["bid"] * D("3")).quantize(D("0.01"))
    r = client.post("/api/orders", json={"symbol": "ETHUSD", "side": "sell", "type": "limit",
                                         "quantity": "1", "limit_price": str(far)}, headers=user)
    assert r.json()["status"] == "open"
    # Holdings are committed to the open sell.
    r2 = client.post("/api/orders", json={"symbol": "ETHUSD", "side": "sell", "quantity": "1"}, headers=user)
    assert r2.json()["status"] == "rejected"
    with SessionLocal() as db:
        match_open_orders(db)
        db.commit()
    assert client.get("/api/orders?status=open", headers=user).json()[0]["id"] == r.json()["id"]


def test_auth_and_account(client, user):
    assert client.get("/api/portfolio").status_code == 401
    r = client.patch("/api/auth/me", json={"full_name": "Renamed", "country": "ke"}, headers=user)
    assert r.json()["full_name"] == "Renamed" and r.json()["country"] == "KE"
    email = r.json()["email"]
    assert client.post("/api/auth/login", json={"email": email, "password": "wrong-pass"}).status_code == 401
    assert client.post("/api/auth/change-password", json={"current_password": "s3cret-pass",
                                                         "new_password": "n3w-password"}, headers=user).status_code == 204
    assert client.post("/api/auth/login", json={"email": email, "password": "n3w-password"}).status_code == 200
    assert client.post("/api/auth/register", json={"email": email, "password": "whatever1",
                                                   "full_name": "Dup"}).status_code == 409


def test_market_data(client):
    assert len(client.get("/api/markets/instruments").json()) == 14
    q = client.get("/api/markets/quotes/btcusd").json()
    assert D(q["bid"]) < D(q["ask"])
    c = client.get("/api/markets/candles/EURUSD?interval=5m&limit=50").json()
    assert len(c) == 50 and all(x["low"] <= min(x["open"], x["close"]) for x in c)
    with client.websocket_connect("/api/markets/ws") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "quotes" and len(msg["data"]) == 14
