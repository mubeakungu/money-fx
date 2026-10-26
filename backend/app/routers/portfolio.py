from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..market import feed
from ..security import get_account
from ..trading import CENT, cash_wallet

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("", response_model=schemas.PortfolioOut)
def portfolio(account: models.Account = Depends(get_account), db: Session = Depends(get_db)):
    wallet = cash_wallet(db, account)
    rows = db.scalars(select(models.Position).where(models.Position.account_id == account.id)).all()
    positions, realized = [], Decimal(0)
    allocation = {"cash": wallet.balance.quantize(CENT)}
    for p in rows:
        realized += p.realized_pnl
        if p.quantity <= 0:
            continue
        inst = p.instrument
        price = feed.quote(inst.symbol)["bid"]  # value at what you could sell for now
        value = price * p.quantity
        cost = p.avg_price * p.quantity
        pnl = value - cost
        positions.append(schemas.PositionOut(
            symbol=inst.symbol, name=inst.name, asset_class=inst.asset_class, quantity=p.quantity,
            avg_price=p.avg_price.quantize(Decimal(1).scaleb(-inst.price_decimals - 2)), price=price,
            market_value=value.quantize(CENT), unrealized_pnl=pnl.quantize(CENT),
            unrealized_pnl_pct=round(float(pnl / cost * 100), 2) if cost else 0.0,
            realized_pnl=p.realized_pnl.quantize(CENT)))
        allocation[inst.asset_class] = allocation.get(inst.asset_class, Decimal(0)) + value.quantize(CENT)
    positions_value = sum((p.market_value for p in positions), Decimal(0))
    net_deposits = db.scalar(select(func.coalesce(func.sum(models.Transaction.amount), 0)).where(
        models.Transaction.wallet_id == wallet.id,
        models.Transaction.type.in_(["deposit", "withdrawal"])))
    return schemas.PortfolioOut(
        cash=wallet.balance.quantize(CENT), cash_locked=wallet.locked.quantize(CENT),
        positions_value=positions_value, equity=(wallet.balance + positions_value).quantize(CENT),
        unrealized_pnl=sum((p.unrealized_pnl for p in positions), Decimal(0)),
        realized_pnl=realized.quantize(CENT), net_deposits=Decimal(net_deposits).quantize(CENT),
        allocation=allocation, positions=sorted(positions, key=lambda p: -p.market_value))
