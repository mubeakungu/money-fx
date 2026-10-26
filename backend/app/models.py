"""Database schema for money fx.

users 1--1 accounts 1--* wallets 1--* transactions
accounts 1--* orders *--1 instruments
accounts 1--* positions *--1 instruments
"""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    JSON,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

Money = Numeric(24, 8)


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    account: Mapped["Account"] = relationship(back_populates="user", uselist=False)


class Account(Base):
    """A trading account. One per user for the MVP; the schema allows more later."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    base_currency: Mapped[str] = mapped_column(String(10), default="USD")
    status: Mapped[str] = mapped_column(Enum("active", "suspended", "closed", name="account_status"), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="account")
    wallets: Mapped[list["Wallet"]] = relationship(back_populates="account")


class Wallet(Base):
    """Cash balance in one currency. `locked` is cash reserved by open buy limit orders."""

    __tablename__ = "wallets"
    __table_args__ = (UniqueConstraint("account_id", "currency"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    currency: Mapped[str] = mapped_column(String(10))
    balance: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    locked: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))

    account: Mapped[Account] = relationship(back_populates="wallets")

    @property
    def available(self) -> Decimal:
        return self.balance - self.locked


class Transaction(Base):
    """Ledger entry for every balance change."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), index=True)
    type: Mapped[str] = mapped_column(
        Enum("deposit", "withdrawal", "trade_buy", "trade_sell", name="txn_type")
    )
    amount: Mapped[Decimal] = mapped_column(Money)  # signed: + credit, - debit
    balance_after: Mapped[Decimal] = mapped_column(Money)
    method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="completed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Instrument(Base):
    """A tradable market. All MVP instruments are quoted in USD."""

    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    asset_class: Mapped[str] = mapped_column(
        Enum("forex", "crypto", "stock", "commodity", name="asset_class")
    )
    quote_currency: Mapped[str] = mapped_column(String(10), default="USD")
    base_price: Mapped[Decimal] = mapped_column(Money)
    volatility: Mapped[float] = mapped_column()  # mock feed: daily-ish volatility
    spread_bps: Mapped[float] = mapped_column()
    price_decimals: Mapped[int] = mapped_column(Integer)
    qty_decimals: Mapped[int] = mapped_column(Integer)
    min_qty: Mapped[Decimal] = mapped_column(Money)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"))
    side: Mapped[str] = mapped_column(Enum("buy", "sell", name="order_side"))
    type: Mapped[str] = mapped_column(Enum("market", "limit", name="order_type"))
    quantity: Mapped[Decimal] = mapped_column(Money)
    limit_price: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("open", "filled", "cancelled", "rejected", name="order_status"), default="open", index=True
    )
    filled_price: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    reserved: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))  # cash locked by a buy limit
    reject_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    instrument: Mapped[Instrument] = relationship()


class Position(Base):
    """Current holding of one instrument (long only in the MVP)."""

    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("account_id", "instrument_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"))
    quantity: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    avg_price: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    realized_pnl: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))

    instrument: Mapped[Instrument] = relationship()


class Bot(Base):
    """An automated strategy trading one instrument, long only, one position at a time."""

    __tablename__ = "bots"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    symbol: Mapped[str] = mapped_column(String(20))
    broker: Mapped[str] = mapped_column(Enum("paper", "oanda", name="bot_broker"), default="paper")
    strategy: Mapped[str] = mapped_column(String(30))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    interval: Mapped[str] = mapped_column(String(5), default="5m")
    trade_size_usd: Mapped[Decimal] = mapped_column(Money)
    stop_loss_pct: Mapped[float | None] = mapped_column(nullable=True)
    take_profit_pct: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(Enum("running", "stopped", "error", name="bot_status"), default="stopped")
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Current open position (quantity 0 = flat)
    position_qty: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    entry_price: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    external_trade_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_candle_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Running stats
    realized_pnl: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    trades_closed: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BotTrade(Base):
    __tablename__ = "bot_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    action: Mapped[str] = mapped_column(Enum("open", "close", name="bot_trade_action"))
    reason: Mapped[str] = mapped_column(String(30))  # signal / stop_loss / take_profit / manual
    quantity: Mapped[Decimal] = mapped_column(Money)
    price: Mapped[Decimal] = mapped_column(Money)
    pnl: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class BotLog(Base):
    __tablename__ = "bot_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    level: Mapped[str] = mapped_column(String(10), default="info")
    message: Mapped[str] = mapped_column(String(400))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
