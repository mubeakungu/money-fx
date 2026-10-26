"""Order execution against the mock feed. Long-only, cash-settled in USD."""
from datetime import datetime, timezone
from decimal import ROUND_DOWN, ROUND_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models
from .market import feed

CENT = Decimal("0.01")


class OrderError(ValueError):
    pass


def cash_wallet(db: Session, account: models.Account) -> models.Wallet:
    return db.scalars(
        select(models.Wallet).where(models.Wallet.account_id == account.id,
                                    models.Wallet.currency == account.base_currency)
    ).one()


def get_position(db: Session, account_id: int, instrument_id: int) -> models.Position:
    pos = db.scalars(select(models.Position).where(models.Position.account_id == account_id,
                                                   models.Position.instrument_id == instrument_id)).first()
    if pos is None:
        pos = models.Position(account_id=account_id, instrument_id=instrument_id,
                              quantity=Decimal(0), avg_price=Decimal(0), realized_pnl=Decimal(0))
        db.add(pos)
        db.flush()
    return pos


def open_sell_qty(db: Session, account_id: int, instrument_id: int, exclude_id: int | None = None) -> Decimal:
    q = db.scalar(select(func.coalesce(func.sum(models.Order.quantity), 0)).where(
        models.Order.account_id == account_id, models.Order.instrument_id == instrument_id,
        models.Order.side == "sell", models.Order.status == "open", models.Order.id != (exclude_id or 0)))
    return Decimal(q)


def _reject(db, order, reason):
    order.status = "rejected"
    order.reject_reason = reason
    db.add(order)
    db.flush()
    return order


def _fill(db: Session, order: models.Order, wallet: models.Wallet, price: Decimal):
    pos = get_position(db, order.account_id, order.instrument_id)
    qty = order.quantity
    if order.side == "buy":
        cost = (price * qty).quantize(CENT, rounding=ROUND_UP)
        wallet.locked -= order.reserved
        order.reserved = Decimal(0)
        wallet.balance -= cost
        new_qty = pos.quantity + qty
        pos.avg_price = (pos.quantity * pos.avg_price + qty * price) / new_qty
        pos.quantity = new_qty
        amount = -cost
    else:
        proceeds = (price * qty).quantize(CENT, rounding=ROUND_DOWN)
        wallet.balance += proceeds
        pos.realized_pnl += (price - pos.avg_price) * qty
        pos.quantity -= qty
        if pos.quantity == 0:
            pos.avg_price = Decimal(0)
        amount = proceeds
    order.status = "filled"
    order.filled_price = price
    order.filled_at = datetime.now(timezone.utc)
    db.add(models.Transaction(wallet_id=wallet.id, type=f"trade_{order.side}", amount=amount,
                              balance_after=wallet.balance, order_id=order.id,
                              reference=f"{order.side.upper()} {qty.normalize():f} {order.instrument.symbol} @ {price}"))


def place_order(db: Session, account: models.Account, symbol: str, side: str, type_: str,
                quantity: Decimal, limit_price: Decimal | None) -> models.Order:
    inst = db.scalars(select(models.Instrument).where(models.Instrument.symbol == symbol.upper())).first()
    if inst is None:
        raise OrderError(f"Unknown instrument {symbol}")
    step = Decimal(1).scaleb(-inst.qty_decimals)
    if quantity != quantity.quantize(step) or quantity < inst.min_qty:
        raise OrderError(f"Quantity must be at least {inst.min_qty.normalize():f} "
                         f"with at most {inst.qty_decimals} decimal places")
    if type_ == "limit":
        if limit_price is None:
            raise OrderError("Limit orders need a limit_price")
        limit_price = limit_price.quantize(Decimal(1).scaleb(-inst.price_decimals))
    else:
        limit_price = None

    wallet = cash_wallet(db, account)
    order = models.Order(account_id=account.id, instrument=inst, side=side, type=type_,
                         quantity=quantity, limit_price=limit_price, reserved=Decimal(0))
    db.add(order)
    db.flush()

    q = feed.quote(inst.symbol)
    if side == "buy":
        if type_ == "market":
            cost = (q["ask"] * quantity).quantize(CENT, rounding=ROUND_UP)
            if cost > wallet.available:
                return _reject(db, order, f"Insufficient funds: need {cost} USD, available {wallet.available.quantize(CENT)}")
            _fill(db, order, wallet, q["ask"])
        else:
            reserve = (limit_price * quantity).quantize(CENT, rounding=ROUND_UP)
            if reserve > wallet.available:
                return _reject(db, order, f"Insufficient funds: need {reserve} USD, available {wallet.available.quantize(CENT)}")
            order.reserved = reserve
            wallet.locked += reserve
            if q["ask"] <= limit_price:
                _fill(db, order, wallet, q["ask"])
    else:
        pos = get_position(db, account.id, inst.id)
        free = pos.quantity - open_sell_qty(db, account.id, inst.id, exclude_id=order.id)
        if quantity > free:
            return _reject(db, order, f"Insufficient holdings: you can sell up to {free.normalize():f} {inst.symbol}")
        if type_ == "market":
            _fill(db, order, wallet, q["bid"])
        elif q["bid"] >= limit_price:
            _fill(db, order, wallet, q["bid"])
    db.flush()
    return order


def cancel_order(db: Session, account: models.Account, order: models.Order):
    if order.status != "open":
        raise OrderError("Only open orders can be cancelled")
    if order.reserved:
        wallet = cash_wallet(db, account)
        wallet.locked -= order.reserved
        order.reserved = Decimal(0)
    order.status = "cancelled"


def match_open_orders(db: Session) -> int:
    """Fill resting limit orders whose price has been reached. Returns fills."""
    fills = 0
    for order in db.scalars(select(models.Order).where(models.Order.status == "open")).all():
        q = feed.quote(order.instrument.symbol)
        account = db.get(models.Account, order.account_id)
        if order.side == "buy" and q["ask"] <= order.limit_price:
            _fill(db, order, cash_wallet(db, account), q["ask"])
            fills += 1
        elif order.side == "sell" and q["bid"] >= order.limit_price:
            _fill(db, order, cash_wallet(db, account), q["bid"])
            fills += 1
    return fills
