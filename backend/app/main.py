import asyncio
import logging
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from . import models
from .config import BACKGROUND_WORKERS, CORS_ORIGINS
from .database import Base, SessionLocal, engine
from .market import INSTRUMENTS
from .bots import run_bots
from .routers import auth, bots, markets, orders, portfolio, wallet
from .trading import match_open_orders

log = logging.getLogger("moneyfx")


def init_db():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        existing = set(db.scalars(select(models.Instrument.symbol)))
        for symbol, name, cls, base, vol, spread, pdp, qdp, min_qty in INSTRUMENTS:
            if symbol not in existing:
                db.add(models.Instrument(symbol=symbol, name=name, asset_class=cls, base_price=Decimal(base),
                                         volatility=vol, spread_bps=spread, price_decimals=pdp,
                                         qty_decimals=qdp, min_qty=Decimal(min_qty)))
        db.commit()


async def matcher(interval: float = 1.0):
    while True:
        try:
            with SessionLocal() as db:
                if match_open_orders(db):
                    db.commit()
        except Exception:
            log.exception("limit order matching failed")
        await asyncio.sleep(interval)


def _run_bots_once():
    with SessionLocal() as db:
        run_bots(db)


async def bot_runner(interval: float = 2.0):
    while True:
        try:
            # Broker calls block on the network, so keep them off the event loop.
            await asyncio.to_thread(_run_bots_once)
        except Exception:
            log.exception("bot runner failed")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    tasks = [asyncio.create_task(matcher()), asyncio.create_task(bot_runner())] if BACKGROUND_WORKERS else []
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(title="money fx API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
for r in (auth, wallet, markets, orders, portfolio, bots):
    app.include_router(r.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
