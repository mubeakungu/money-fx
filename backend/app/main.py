import asyncio
import logging
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from . import models
from .config import CORS_ORIGINS
from .database import Base, SessionLocal, engine
from .market import INSTRUMENTS
from .routers import auth, markets, orders, portfolio, wallet
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task = asyncio.create_task(matcher())
    yield
    task.cancel()


app = FastAPI(title="money fx API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
for r in (auth, wallet, markets, orders, portfolio):
    app.include_router(r.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
