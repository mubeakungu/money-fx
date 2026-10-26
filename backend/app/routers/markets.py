import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..market import feed

router = APIRouter(prefix="/api/markets", tags=["markets"])

INTERVALS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}


def _quote_json(symbol):
    q = feed.quote(symbol)
    return {**q, "bid": str(q["bid"]), "ask": str(q["ask"]), "mid": str(q["mid"])}


@router.get("/instruments", response_model=list[schemas.InstrumentOut])
def instruments(asset_class: str | None = None, db: Session = Depends(get_db)):
    stmt = select(models.Instrument).order_by(models.Instrument.id)
    if asset_class:
        stmt = stmt.where(models.Instrument.asset_class == asset_class)
    return db.scalars(stmt).all()


@router.get("/quotes")
def quotes():
    return [_quote_json(s) for s in feed.symbols()]


@router.get("/quotes/{symbol}")
def quote(symbol: str):
    if symbol.upper() not in feed.symbols():
        raise HTTPException(404, "Unknown instrument")
    return _quote_json(symbol.upper())


@router.get("/candles/{symbol}")
def candles(symbol: str, interval: str = "1m", limit: int = Query(200, ge=1, le=1000)):
    if symbol.upper() not in feed.symbols():
        raise HTTPException(404, "Unknown instrument")
    if interval not in INTERVALS:
        raise HTTPException(400, f"interval must be one of {', '.join(INTERVALS)}")
    return feed.candles(symbol.upper(), INTERVALS[interval], limit)


@router.websocket("/ws")
async def stream(ws: WebSocket):
    """Pushes every quote once a second."""
    await ws.accept()
    try:
        while True:
            await ws.send_json({"type": "quotes", "data": [_quote_json(s) for s in feed.symbols()]})
            await asyncio.sleep(1)
    except (WebSocketDisconnect, RuntimeError):
        pass
