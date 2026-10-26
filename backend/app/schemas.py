from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, PlainSerializer

# Money goes over the wire as a plain decimal string ("1250.5") so the client never
# sees float rounding.
Dec = Annotated[Decimal, PlainSerializer(lambda v: format(v.normalize(), "f"), return_type=str, when_used="json")]


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)
    country: str | None = Field(default=None, min_length=2, max_length=2)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(Out):
    id: int
    email: EmailStr
    full_name: str
    country: str | None
    created_at: datetime
    account_id: int
    account_status: str


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    country: str | None = Field(default=None, min_length=2, max_length=2)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class WalletOut(Out):
    id: int
    currency: str
    balance: Dec
    locked: Dec
    available: Dec


class MoneyIn(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    method: Literal["card", "bank_transfer", "mobile_money", "crypto"] = "card"


class TransactionOut(Out):
    id: int
    type: str
    amount: Dec
    balance_after: Dec
    method: str | None
    reference: str | None
    order_id: int | None
    status: str
    created_at: datetime


class InstrumentOut(Out):
    id: int
    symbol: str
    name: str
    asset_class: str
    quote_currency: str
    price_decimals: int
    qty_decimals: int
    min_qty: Dec


class OrderIn(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    type: Literal["market", "limit"] = "market"
    quantity: Decimal = Field(gt=0)
    limit_price: Decimal | None = Field(default=None, gt=0)


class OrderOut(Out):
    id: int
    symbol: str
    side: str
    type: str
    quantity: Dec
    limit_price: Dec | None
    status: str
    filled_price: Dec | None
    reject_reason: str | None
    created_at: datetime
    filled_at: datetime | None


class PositionOut(Out):
    symbol: str
    name: str
    asset_class: str
    quantity: Dec
    avg_price: Dec
    price: Dec
    market_value: Dec
    unrealized_pnl: Dec
    unrealized_pnl_pct: float
    realized_pnl: Dec


class PortfolioOut(Out):
    cash: Dec
    cash_locked: Dec
    positions_value: Dec
    equity: Dec
    unrealized_pnl: Dec
    realized_pnl: Dec
    net_deposits: Dec
    allocation: dict[str, Dec]
    positions: list[PositionOut]
