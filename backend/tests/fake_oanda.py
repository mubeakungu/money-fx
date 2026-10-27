"""A small stateful stand-in for the OANDA v20 API, priced from the money fx mock feed.

Used by tests, and for trying the Real account locally without an OANDA login:
    uvicorn tests.fake_oanda:app --port 8099
    OANDA_BASE_URL=http://localhost:8099 OANDA_API_TOKEN=x OANDA_ACCOUNT_ID=001 OANDA_OWNER_EMAILS=you@example.com uvicorn app.main:app
"""
import time
from decimal import Decimal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.brokers import OANDA_GRANULARITY, OANDA_SYMBOLS
from app.market import INSTRUMENTS, feed

app = FastAPI()
REVERSE = {v: k for k, v in OANDA_SYMBOLS.items()}
GRAN = {v: k for k, v in OANDA_GRANULARITY.items()}
SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
SPECS = {OANDA_SYMBOLS[r[0]]: {"name": OANDA_SYMBOLS[r[0]], "displayPrecision": r[6],
                               "tradeUnitsPrecision": 0, "minimumTradeSize": "1"}
         for r in INSTRUMENTS if r[0] in OANDA_SYMBOLS}
state = {"seq": 100, "balance": Decimal("100000"), "trades": {}, "orders": {}}


def reset():
    state.update(seq=100, balance=Decimal("100000"), trades={}, orders={})


def _id():
    state["seq"] += 1
    return str(state["seq"])


def _q(inst):
    q = feed.quote(REVERSE[inst])
    return q["bid"], q["ask"]


def _upl(t):
    bid, ask = _q(t["instrument"])
    units = Decimal(t["currentUnits"])
    exit_price = bid if units > 0 else ask
    return (exit_price - Decimal(t["price"])) * units


def _trade_json(t):
    out = dict(t)
    if t["state"] == "OPEN":
        out["unrealizedPL"] = str(_upl(t).quantize(Decimal("0.0001")))
    return out


@app.get("/v3/accounts/{acct}/summary")
def summary(acct: str):
    upl = sum((_upl(t) for t in state["trades"].values() if t["state"] == "OPEN"), Decimal(0))
    return {"account": {"id": acct, "currency": "USD", "balance": str(state["balance"]), "NAV": str(state["balance"] + upl),
                        "unrealizedPL": str(upl.quantize(Decimal("0.0001"))), "pl": "0", "marginUsed": "0",
                        "marginAvailable": str(state["balance"]),
                        "openTradeCount": sum(t["state"] == "OPEN" for t in state["trades"].values()),
                        "pendingOrderCount": len(state["orders"])}}


@app.get("/v3/accounts/{acct}/instruments")
def instruments(acct: str):
    return {"instruments": list(SPECS.values())}


@app.get("/v3/accounts/{acct}/pricing")
def pricing(acct: str, instruments: str):
    out = []
    for name in instruments.split(","):
        bid, ask = _q(name)
        out.append({"instrument": name, "bids": [{"price": str(bid)}], "asks": [{"price": str(ask)}],
                    "status": "tradeable", "time": f"{time.time():.9f}"})
    return {"prices": out}


@app.get("/v3/instruments/{inst}/candles")
def candles(inst: str, granularity: str, count: int = 500, price: str = "M"):
    bars = feed.candles(REVERSE[inst], SECONDS[GRAN[granularity]], count)
    return {"candles": [{"time": f"{b['time']}.000000000", "complete": i < len(bars) - 1, "volume": 1,
                         "mid": {k[0]: str(b[k]) for k in ("open", "high", "low", "close")}}
                        for i, b in enumerate(bars)]}


def _open(inst, units, price, extra):
    tid = _id()
    t = {"id": tid, "instrument": inst, "price": str(price), "initialUnits": str(units), "currentUnits": str(units),
         "state": "OPEN", "realizedPL": "0", "openTime": f"{time.time():.9f}"}
    if "stopLossOnFill" in extra:
        t["stopLossOrder"] = {"price": extra["stopLossOnFill"]["price"]}
    if "takeProfitOnFill" in extra:
        t["takeProfitOrder"] = {"price": extra["takeProfitOnFill"]["price"]}
    state["trades"][tid] = t
    return tid


@app.post("/v3/accounts/{acct}/orders", status_code=201)
async def order(acct: str, request: Request):
    o = (await request.json())["order"]
    units = Decimal(o["units"])
    if o["instrument"] not in SPECS:
        return JSONResponse({"errorMessage": "Invalid instrument"}, 400)
    if o["type"] == "MARKET":
        bid, ask = _q(o["instrument"])
        price = ask if units > 0 else bid
        tid = _open(o["instrument"], units, price, o)
        return {"orderCreateTransaction": {"id": _id()},
                "orderFillTransaction": {"id": _id(), "price": str(price), "units": str(units), "pl": "0",
                                         "tradeOpened": {"tradeID": tid, "units": str(units), "price": str(price)}}}
    oid = _id()
    state["orders"][oid] = {"id": oid, "type": "LIMIT", "instrument": o["instrument"], "units": str(units),
                            "price": o["price"], "createTime": f"{time.time():.9f}", "extra": o}
    return {"orderCreateTransaction": {"id": oid}}


@app.get("/v3/accounts/{acct}/pendingOrders")
def pending(acct: str):
    return {"orders": [{k: v for k, v in o.items() if k != "extra"} for o in state["orders"].values()]}


@app.put("/v3/accounts/{acct}/orders/{oid}/cancel")
def cancel(acct: str, oid: str):
    if state["orders"].pop(oid, None) is None:
        return JSONResponse({"errorMessage": "Order not found"}, 404)
    return {"orderCancelTransaction": {"id": _id(), "orderID": oid}}


@app.get("/v3/accounts/{acct}/openTrades")
def open_trades(acct: str):
    return {"trades": [_trade_json(t) for t in state["trades"].values() if t["state"] == "OPEN"]}


@app.get("/v3/accounts/{acct}/trades")
def trades(acct: str, request: Request, count: int = 50):
    want = request.query_params.get("state", "OPEN")
    rows = [_trade_json(t) for t in state["trades"].values() if want == "ALL" or t["state"] == want]
    return {"trades": rows[-count:][::-1]}


@app.get("/v3/accounts/{acct}/trades/{tid}")
def trade(acct: str, tid: str):
    t = state["trades"].get(tid)
    return {"trade": _trade_json(t)} if t else JSONResponse({"errorMessage": "Trade not found"}, 404)


@app.put("/v3/accounts/{acct}/trades/{tid}/close")
def close(acct: str, tid: str):
    t = state["trades"].get(tid)
    if not t or t["state"] != "OPEN":
        return JSONResponse({"errorMessage": "Trade not open"}, 404)
    bid, ask = _q(t["instrument"])
    units = Decimal(t["currentUnits"])
    price = bid if units > 0 else ask
    pl = ((price - Decimal(t["price"])) * units).quantize(Decimal("0.0001"))
    state["balance"] += pl
    t.update(state="CLOSED", currentUnits="0", realizedPL=str(pl), averageClosePrice=str(price), closeTime=f"{time.time():.9f}")
    return {"orderFillTransaction": {"id": _id(), "price": str(price), "pl": str(pl),
                                     "tradesClosed": [{"tradeID": tid, "units": str(-units), "realizedPL": str(pl)}]}}
