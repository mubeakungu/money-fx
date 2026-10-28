import os
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..alerts import TelegramError, new_link_code, send_pending, telegram
from ..bots import backtest, bot_log, record_close, todays_bot_pnl
from ..brokers import OANDA_SYMBOLS, BrokerError, get_broker, oanda_configured
from ..config import OANDA_OWNER_EMAILS
from ..database import get_db
from ..schemas import Dec, Out
from ..security import get_account
from ..strategies import STRATEGIES, validate

router = APIRouter(prefix="/api/bots", tags=["bots"])
Interval = Literal["1m", "5m", "15m", "1h", "4h", "1d"]


class StrategyConfig(BaseModel):
    symbol: str
    broker: Literal["paper", "oanda"] = "paper"
    strategy: str
    params: dict = {}
    interval: Interval = "5m"
    trade_size_usd: Decimal = Field(gt=0, le=1_000_000)
    stop_loss_pct: float | None = Field(default=None, gt=0, le=50)
    take_profit_pct: float | None = Field(default=None, gt=0, le=500)
    direction: Literal["long", "short", "both"] = "long"
    risk_pct: float | None = Field(default=None, gt=0, le=10)


class BotIn(StrategyConfig):
    name: str = Field(min_length=1, max_length=80)


class BacktestIn(StrategyConfig):
    bars: int = Field(default=500, ge=50, le=5000)
    capital: float = Field(default=10_000, gt=0)


class BotOut(Out):
    id: int
    name: str
    symbol: str
    broker: str
    strategy: str
    params: dict
    interval: str
    trade_size_usd: Dec
    stop_loss_pct: float | None
    take_profit_pct: float | None
    direction: str | None
    risk_pct: float | None
    status: str
    error: str | None
    position_qty: Dec
    position_side: str | None
    entry_price: Dec | None
    realized_pnl: Dec
    trades_closed: int
    wins: int


class BotTradeOut(Out):
    id: int
    action: str
    side: str | None
    reason: str
    quantity: Dec
    price: Dec
    pnl: Dec | None
    created_at: datetime


class BotLogOut(Out):
    id: int
    level: str
    message: str
    created_at: datetime


def oanda_allowed(account: models.Account) -> bool:
    return account.user.email.lower() in OANDA_OWNER_EMAILS


def _require_oanda(account: models.Account):
    if not oanda_allowed(account):
        raise HTTPException(403, "OANDA trading is limited to the account owner (OANDA_OWNER_EMAILS)")


def _check(db: Session, account: models.Account, cfg: StrategyConfig) -> dict:
    if cfg.broker == "oanda":
        _require_oanda(account)
    symbol = cfg.symbol.upper()
    if not db.scalars(select(models.Instrument).where(models.Instrument.symbol == symbol)).first():
        raise HTTPException(400, f"Unknown instrument {cfg.symbol}")
    if cfg.broker == "oanda" and symbol not in OANDA_SYMBOLS:
        raise HTTPException(400, f"OANDA bots can trade {', '.join(OANDA_SYMBOLS)}")
    if cfg.risk_pct and not cfg.stop_loss_pct:
        raise HTTPException(400, "Risk-based sizing needs a stop-loss: the stop decides how much a trade can lose")
    try:
        return validate(cfg.strategy, cfg.params)
    except ValueError as e:
        raise HTTPException(400, str(e))


def _own(db: Session, account: models.Account, bot_id: int) -> models.Bot:
    bot = db.get(models.Bot, bot_id)
    if bot is None or bot.account_id != account.id:
        raise HTTPException(404, "Bot not found")
    return bot


@router.get("/strategies")
def strategies():
    return [{"key": s.key, "name": s.name, "description": s.description,
             "params": [p.__dict__ for p in s.params]} for s in STRATEGIES.values()]


@router.get("/brokers")
def brokers(account: models.Account = Depends(get_account)):
    allowed = oanda_allowed(account)
    oanda = {"configured": oanda_configured() and allowed, "allowed": allowed,
             "environment": os.getenv("OANDA_ENV", "practice"), "symbols": list(OANDA_SYMBOLS)}
    if oanda["configured"]:
        try:
            s = get_broker("oanda").summary()
            oanda["account"] = {k: s.get(k) for k in ("id", "currency", "balance", "NAV", "unrealizedPL")}
        except BrokerError as e:
            oanda["error"] = str(e)
    return {"paper": {"configured": True}, "oanda": oanda}


class BotSettings(BaseModel):
    daily_loss_limit_usd: Decimal | None = Field(default=None, gt=0, le=10_000_000)


def _settings(db: Session, account: models.Account) -> dict:
    limit = account.bot_daily_loss_limit
    return {"daily_loss_limit_usd": None if limit is None else format(limit.normalize(), "f"),
            "today_pnl_usd": format(todays_bot_pnl(db, account.id).quantize(Decimal("0.01")), "f"),
            "telegram": {"available": telegram() is not None, "connected": bool(account.telegram_chat_id)}}


def _telegram():
    client = telegram()
    if client is None:
        raise HTTPException(400, "Telegram alerts are not set up on this server. Set TELEGRAM_BOT_TOKEN (see README).")
    return client


@router.get("/settings")
def get_settings(account: models.Account = Depends(get_account), db: Session = Depends(get_db)):
    return _settings(db, account)


@router.put("/settings")
def put_settings(body: BotSettings, account: models.Account = Depends(get_account), db: Session = Depends(get_db)):
    account.bot_daily_loss_limit = body.daily_loss_limit_usd
    db.commit()
    return _settings(db, account)


@router.post("/telegram/link")
def telegram_link(account: models.Account = Depends(get_account), db: Session = Depends(get_db)):
    """Start linking: the user opens the returned t.me link and presses Start, which sends the code to the bot."""
    client = _telegram()
    try:
        username = client.username()
    except TelegramError as e:
        raise HTTPException(400, str(e))
    account.telegram_link_code = new_link_code()
    db.commit()
    return {"url": f"https://t.me/{username}?start={account.telegram_link_code}", "bot": username,
            "code": account.telegram_link_code}


@router.post("/telegram/verify")
def telegram_verify(account: models.Account = Depends(get_account), db: Session = Depends(get_db)):
    client = _telegram()
    if not account.telegram_link_code:
        raise HTTPException(400, "Press Connect Telegram first")
    try:
        chat = client.find_chat(account.telegram_link_code)
        if chat is None:
            raise HTTPException(400, "No message from you yet. Open the link, press Start in Telegram, then try again.")
        client.send(chat, "money fx is connected. You'll get a message here whenever one of your bots trades or stops.")
    except TelegramError as e:
        raise HTTPException(400, str(e))
    account.telegram_chat_id = chat
    account.telegram_link_code = None
    db.commit()
    return _settings(db, account)


@router.post("/telegram/test")
def telegram_test(account: models.Account = Depends(get_account)):
    client = _telegram()
    if not account.telegram_chat_id:
        raise HTTPException(400, "Telegram is not connected")
    try:
        client.send(account.telegram_chat_id, "Test alert from money fx. Bot alerts are working.")
    except TelegramError as e:
        raise HTTPException(400, str(e))
    return {"sent": True}


@router.delete("/telegram")
def telegram_disconnect(account: models.Account = Depends(get_account), db: Session = Depends(get_db)):
    account.telegram_chat_id = None
    account.telegram_link_code = None
    db.commit()
    return _settings(db, account)


@router.post("/backtest")
def run_backtest(body: BacktestIn, account: models.Account = Depends(get_account), db: Session = Depends(get_db)):
    params = _check(db, account, body)
    symbol = body.symbol.upper()
    inst = db.scalars(select(models.Instrument).where(models.Instrument.symbol == symbol)).one()
    try:
        candles = get_broker(body.broker).closed_candles(symbol, body.interval, body.bars)
    except BrokerError as e:
        raise HTTPException(400, str(e))
    if len(candles) < 20:
        raise HTTPException(400, "Not enough price history for a backtest")
    result = backtest(candles, body.strategy, params, body.stop_loss_pct, body.take_profit_pct,
                      float(body.trade_size_usd), body.capital, inst.spread_bps, body.direction, body.risk_pct)
    result["data_source"] = "OANDA" if body.broker == "oanda" else "money fx simulated feed"
    return result


@router.get("", response_model=list[BotOut])
def list_bots(account: models.Account = Depends(get_account), db: Session = Depends(get_db)):
    return db.scalars(select(models.Bot).where(models.Bot.account_id == account.id).order_by(models.Bot.id.desc())).all()


@router.post("", response_model=BotOut, status_code=201)
def create_bot(body: BotIn, account: models.Account = Depends(get_account), db: Session = Depends(get_db)):
    params = _check(db, account, body)
    bot = models.Bot(account_id=account.id, name=body.name.strip(), symbol=body.symbol.upper(), broker=body.broker,
                     strategy=body.strategy, params=params, interval=body.interval,
                     trade_size_usd=body.trade_size_usd, stop_loss_pct=body.stop_loss_pct,
                     take_profit_pct=body.take_profit_pct, direction=body.direction, risk_pct=body.risk_pct,
                     status="stopped", position_qty=Decimal(0),
                     realized_pnl=Decimal(0), trades_closed=0, wins=0)
    db.add(bot)
    db.flush()
    size = (f"risking {body.risk_pct}% of the balance per trade, at most {body.trade_size_usd} USD" if body.risk_pct
            else f"{body.trade_size_usd} USD per trade")
    trades = {"long": "buys only", "short": "sells short only", "both": "buys and sells short"}[body.direction]
    bot_log(db, bot, f"Created: {STRATEGIES[bot.strategy].name} on {bot.symbol} {bot.interval}, {trades}, {size}, "
                     f"via {'OANDA' if bot.broker == 'oanda' else 'paper trading'}")
    db.commit()
    return bot


@router.get("/{bot_id}")
def bot_detail(bot_id: int, account: models.Account = Depends(get_account), db: Session = Depends(get_db)):
    bot = _own(db, account, bot_id)
    trades = db.scalars(select(models.BotTrade).where(models.BotTrade.bot_id == bot.id)
                        .order_by(models.BotTrade.id.desc()).limit(200)).all()
    logs = db.scalars(select(models.BotLog).where(models.BotLog.bot_id == bot.id)
                      .order_by(models.BotLog.id.desc()).limit(200)).all()
    unrealized = None
    if bot.position_qty > 0:
        try:
            q = get_broker(bot.broker).quote(bot.symbol)
            move = bot.entry_price - q["ask"] if bot.position_side == "short" else q["bid"] - bot.entry_price
            pnl = move * bot.position_qty
            unrealized = format(pnl.quantize(Decimal("0.01")), "f")
        except BrokerError:
            pass
    return {"bot": BotOut.model_validate(bot).model_dump(mode="json"), "unrealized_pnl": unrealized,
            "trades": [BotTradeOut.model_validate(t).model_dump(mode="json") for t in trades],
            "logs": [BotLogOut.model_validate(entry).model_dump(mode="json") for entry in logs]}


@router.post("/{bot_id}/start", response_model=BotOut)
def start(bot_id: int, account: models.Account = Depends(get_account), db: Session = Depends(get_db)):
    bot = _own(db, account, bot_id)
    if bot.broker == "oanda":
        _require_oanda(account)
    try:
        get_broker(bot.broker)
    except BrokerError as e:
        raise HTTPException(400, str(e))
    bot.status = "running"
    bot.error = None
    bot.last_candle_time = None
    bot_log(db, bot, "Started")
    db.commit()
    return bot


@router.post("/{bot_id}/stop", response_model=BotOut)
def stop(bot_id: int, account: models.Account = Depends(get_account), db: Session = Depends(get_db)):
    bot = _own(db, account, bot_id)
    bot.status = "stopped"
    bot_log(db, bot, "Stopped" + (" (open position kept; its stop-loss and take-profit stay active on OANDA)"
                                  if bot.position_qty > 0 and bot.broker == "oanda" else
                                  " (open position kept)" if bot.position_qty > 0 else ""))
    db.commit()
    return bot


@router.post("/{bot_id}/close-position", response_model=BotOut)
def close_position(bot_id: int, account: models.Account = Depends(get_account), db: Session = Depends(get_db)):
    bot = _own(db, account, bot_id)
    if bot.position_qty == 0:
        raise HTTPException(400, "This bot has no open position")
    try:
        record_close(db, bot, get_broker(bot.broker).close(db, bot, "manual"))
    except BrokerError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    db.commit()
    send_pending(db)
    return bot


@router.delete("/{bot_id}", status_code=204)
def delete_bot(bot_id: int, account: models.Account = Depends(get_account), db: Session = Depends(get_db)):
    bot = _own(db, account, bot_id)
    if bot.status == "running" or bot.position_qty > 0:
        raise HTTPException(400, "Stop the bot and close its position before deleting it")
    for model in (models.BotTrade, models.BotLog):
        for row in db.scalars(select(model).where(model.bot_id == bot.id)):
            db.delete(row)
    db.delete(bot)
    db.commit()
