from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import get_account
from ..trading import OrderError, cancel_order, place_order

router = APIRouter(prefix="/api/orders", tags=["orders"])


def order_out(o: models.Order) -> schemas.OrderOut:
    return schemas.OrderOut(id=o.id, symbol=o.instrument.symbol, side=o.side, type=o.type, quantity=o.quantity,
                            limit_price=o.limit_price, status=o.status, filled_price=o.filled_price,
                            reject_reason=o.reject_reason, created_at=o.created_at, filled_at=o.filled_at)


@router.post("", response_model=schemas.OrderOut, status_code=201)
def create(body: schemas.OrderIn, account: models.Account = Depends(get_account), db: Session = Depends(get_db)):
    try:
        order = place_order(db, account, body.symbol, body.side, body.type, body.quantity, body.limit_price)
    except OrderError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    db.commit()
    return order_out(order)


@router.get("", response_model=list[schemas.OrderOut])
def list_orders(status: str | None = None, limit: int = 100, account: models.Account = Depends(get_account),
                db: Session = Depends(get_db)):
    stmt = select(models.Order).where(models.Order.account_id == account.id)
    if status:
        stmt = stmt.where(models.Order.status == status)
    return [order_out(o) for o in db.scalars(stmt.order_by(models.Order.id.desc()).limit(min(limit, 500)))]


@router.delete("/{order_id}", response_model=schemas.OrderOut)
def cancel(order_id: int, account: models.Account = Depends(get_account), db: Session = Depends(get_db)):
    order = db.get(models.Order, order_id)
    if order is None or order.account_id != account.id:
        raise HTTPException(404, "Order not found")
    try:
        cancel_order(db, account, order)
    except OrderError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return order_out(order)
