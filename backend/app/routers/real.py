"""The "Real" account: manual trading and account views on the owner's OANDA account."""
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..brokers import OANDA_SYMBOLS, BrokerError, OandaBroker, get_broker
from ..database import get_db
from ..security import get_account
from .bots import oanda_allowed
from .markets import INTERVALS

router = APIRouter(prefix="/api/real", tags=["real account"])


def oanda(account: models.Account = Depends(get_account)) -> OandaBroker:
    if not oanda_allowed(account):
        raise HTTPException(403, "The real account is limited to the account owner (OANDA_OWNER_EMAILS)")
    try:
        return get_broker("oanda")
    except BrokerError as e:
        raise HTTPException(400, str(e))


def call(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except BrokerError as e:
        raise HTTPException(502, str(e))


class RealOrderIn(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    type: Literal["market", "limit"] = "market"
    units: Decimal = Field(gt=0)
    limit_price: Decimal | None = Field(default=None, gt=0)
    stop_loss_pct: float | None = Field(default=None, gt=0, le=50)
    take_profit_pct: float | None = Field(default=None, gt=0, le=500)


@router.get("/account")
def account_summary(b: OandaBroker = Depends(oanda)):
    s = call(b.summary)
    return {"environment": b.env, "id": s.get("id"), "currency": s.get("currency"), "balance": s.get("balance"),
            "nav": s.get("NAV"), "unrealized_pnl": s.get("unrealizedPL"), "realized_pnl": s.get("pl"),
            "margin_used": s.get("marginUsed"), "margin_available": s.get("marginAvailable"),
            "open_trades": s.get("openTradeCount"), "pending_orders": s.get("pendingOrderCount")}


@router.get("/instruments")
def instruments(b: OandaBroker = Depends(oanda), db: Session = Depends(get_db)):
    available = call(b.instruments)
    rows = db.scalars(select(models.Instrument).where(models.Instrument.symbol.in_(list(OANDA_SYMBOLS)))).all()
    out = []
    for r in rows:
        spec = available.get(OANDA_SYMBOLS[r.symbol])
        if spec:
            out.append({"id": r.id, "symbol": r.symbol, "name": r.name, "asset_class": r.asset_class, "quote_currency": "USD",
                        "price_decimals": int(spec["displayPrecision"]), "qty_decimals": int(spec["tradeUnitsPrecision"]),
                        "min_qty": spec["minimumTradeSize"]})
    return out


@router.get("/prices")
def prices(b: OandaBroker = Depends(oanda)):
    return call(b.prices)


@router.get("/candles/{symbol}")
def candles(symbol: str, interval: str = "1m", limit: int = Query(200, ge=1, le=1000), b: OandaBroker = Depends(oanda)):
    if interval not in INTERVALS:
        raise HTTPException(400, f"interval must be one of {', '.join(INTERVALS)}")
    return call(b.chart_candles, symbol.upper(), interval, limit)


def _bot_names(db: Session, account: models.Account) -> dict:
    bots = db.scalars(select(models.Bot).where(models.Bot.account_id == account.id, models.Bot.broker == "oanda")).all()
    return {b.external_trade_id: b.name for b in bots if b.external_trade_id}


@router.get("/trades")
def trades(state: Literal["open", "closed"] = "open", b: OandaBroker = Depends(oanda),
           account: models.Account = Depends(get_account), db: Session = Depends(get_db)):
    rows = call(b.open_trades) if state == "open" else call(b.closed_trades)
    names = _bot_names(db, account)
    for t in rows:
        t["bot"] = names.get(t["id"])
    return rows


@router.post("/trades/{trade_id}/close")
def close_trade(trade_id: str, b: OandaBroker = Depends(oanda)):
    return call(b.close_trade, trade_id)


@router.get("/orders")
def pending(b: OandaBroker = Depends(oanda)):
    return call(b.pending_orders)


@router.post("/orders", status_code=201)
def place(body: RealOrderIn, b: OandaBroker = Depends(oanda)):
    symbol = body.symbol.upper()
    if symbol not in OANDA_SYMBOLS:
        raise HTTPException(400, f"The real account can trade {', '.join(OANDA_SYMBOLS)}")
    if body.type == "limit" and body.limit_price is None:
        raise HTTPException(400, "Limit orders need a limit_price")
    return call(b.place, symbol, body.side, body.units, body.type, body.limit_price,
                body.stop_loss_pct, body.take_profit_pct)


@router.delete("/orders/{order_id}", status_code=204)
def cancel(order_id: str, b: OandaBroker = Depends(oanda)):
    call(b.cancel_order, order_id)
