"""Bot engine: runs each active bot once per closed candle, and a backtester that replays
the same strategy over history."""
import logging
from datetime import date, datetime, time, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models
from .alerts import discard, notify, send_pending
from .brokers import BrokerError, Fill, get_broker, stop_prices
from .strategies import STRATEGIES

log = logging.getLogger("moneyfx.bots")
WARMUP_BARS = 300
MAX_CONSECUTIVE_ERRORS = 5
_errors: dict[int, int] = {}
_limit_logged: dict[int, date] = {}


def bot_log(db: Session, bot: models.Bot, message: str, level: str = "info"):
    db.add(models.BotLog(bot_id=bot.id, level=level, message=message[:400]))


def alert(db: Session, bot: models.Bot, text: str):
    notify(db, bot, f"[{'OANDA' if bot.broker == 'oanda' else 'Paper'}] {text}")


def _fmt(d: Decimal) -> str:
    return f"{d.normalize():f}"


def record_open(db: Session, bot: models.Bot, fill: Fill, side: str = "long"):
    bot.position_qty = fill.quantity
    bot.position_side = side
    bot.entry_price = fill.price
    bot.external_trade_id = fill.external_id
    db.add(models.BotTrade(bot_id=bot.id, action="open", side=side, reason="signal", quantity=fill.quantity,
                           price=fill.price, order_id=fill.order_id, external_id=fill.external_id))
    sl, tp = stop_prices(fill.price, bot)
    stops = ", ".join(s for s in [sl and f"stop-loss {sl:.5g}", tp and f"take-profit {tp:.5g}"] if s)
    verb = "Bought" if side == "long" else "Sold short"
    msg = f"{verb} {_fmt(fill.quantity)} {bot.symbol} at {fill.price}" + (f" ({stops})" if stops else "")
    bot_log(db, bot, msg)
    alert(db, bot, msg)


def record_close(db: Session, bot: models.Bot, fill: Fill):
    side = bot.position_side or "long"
    sign = -1 if side == "short" else 1
    pnl = fill.pnl if fill.pnl is not None else sign * (fill.price - bot.entry_price) * fill.quantity
    bot.realized_pnl += pnl
    bot.trades_closed += 1
    bot.wins += 1 if pnl > 0 else 0
    db.add(models.BotTrade(bot_id=bot.id, action="close", side=side, reason=fill.reason or "signal",
                           quantity=fill.quantity, price=fill.price, pnl=pnl, order_id=fill.order_id,
                           external_id=fill.external_id))
    label = {"signal": "signal", "stop_loss": "stop-loss", "take_profit": "take-profit",
             "manual": "you closed it", "closed_on_oanda": "closed on OANDA"}.get(fill.reason, fill.reason)
    verb = "Sold" if side == "long" else "Bought back"
    msg = f"{verb} {_fmt(fill.quantity)} {bot.symbol} at {fill.price} ({label}), P&L {pnl:+.2f}"
    bot_log(db, bot, msg)
    alert(db, bot, msg)
    bot.position_qty = Decimal(0)
    bot.position_side = None
    bot.entry_price = None
    bot.external_trade_id = None


def trade_size_usd(db: Session, bot: models.Bot, broker) -> Decimal:
    """The fixed trade size, or with risk sizing, the size whose stop-loss loses risk_pct of the balance
    (never more than the fixed size)."""
    size = bot.trade_size_usd
    if bot.risk_pct and bot.stop_loss_pct:
        size = min(size, broker.equity(db, bot) * Decimal(str(bot.risk_pct)) / Decimal(str(bot.stop_loss_pct)))
    return size


def todays_bot_pnl(db: Session, account_id: int) -> Decimal:
    """Realized P&L of all the account's bots since 00:00 UTC."""
    midnight = datetime.combine(datetime.now(timezone.utc).date(), time(), timezone.utc)
    db.flush()  # include a trade closed earlier in this same pass
    total = db.scalar(select(func.sum(models.BotTrade.pnl)).join(models.Bot, models.BotTrade.bot_id == models.Bot.id)
                      .where(models.Bot.account_id == account_id, models.BotTrade.action == "close",
                             models.BotTrade.created_at >= midnight))
    return Decimal(total or 0)


def daily_limit_reached(db: Session, bot: models.Bot) -> bool:
    limit = db.get(models.Account, bot.account_id).bot_daily_loss_limit
    if not limit:
        return False
    pnl = todays_bot_pnl(db, bot.account_id)
    if pnl > -limit:
        return False
    today = datetime.now(timezone.utc).date()
    if _limit_logged.get(bot.id) != today:
        _limit_logged[bot.id] = today
        msg = (f"Daily loss limit reached (bots lost {-pnl:.2f} of {limit:.2f} USD today). "
               "No new trades until 00:00 UTC; open positions keep their stops.")
        bot_log(db, bot, msg, "error")
        alert(db, bot, msg)
    return True


def step(db: Session, bot: models.Bot):
    """One pass for one bot: check stops, then act on a newly closed candle."""
    broker = get_broker(bot.broker)
    if bot.position_qty > 0:
        fill = broker.sync(db, bot)
        if fill:
            record_close(db, bot, fill)

    candles = broker.closed_candles(bot.symbol, bot.interval, WARMUP_BARS)
    if not candles:
        return
    last = candles[-1]["time"]
    if bot.last_candle_time is None:
        # Wait for the next candle instead of acting on a signal that may be old.
        bot.last_candle_time = last
        bot_log(db, bot, f"Watching {bot.symbol} on {bot.interval} candles")
        return
    if last <= bot.last_candle_time:
        return
    bot.last_candle_time = last
    want = {"buy": "long", "sell": "short"}.get(STRATEGIES[bot.strategy].signals(candles, bot.params)[-1])
    if want is None:
        return

    side = (bot.position_side or "long") if bot.position_qty > 0 else None
    if side and side != want:
        record_close(db, bot, broker.close(db, bot, "signal"))
        db.commit()  # keep the close even if opening the opposite trade fails
        send_pending(db)
        side = None
    if side is None and (bot.direction or "long") in (want, "both") and not daily_limit_reached(db, bot):
        price = broker.quote(bot.symbol)["ask" if want == "long" else "bid"]
        qty = broker.units_for(db, bot.symbol, trade_size_usd(db, bot, broker), price)
        record_open(db, bot, broker.open(db, bot, qty, want), want)


def run_bots(db: Session) -> int:
    bots = db.scalars(select(models.Bot).where(models.Bot.status == "running")).all()
    for bot in bots:
        try:
            step(db, bot)
            db.commit()
            send_pending(db)
            _errors.pop(bot.id, None)
        except BrokerError as e:
            db.rollback()
            discard(db)
            n = _errors[bot.id] = _errors.get(bot.id, 0) + 1
            bot_log(db, bot, str(e), "error")
            if n >= MAX_CONSECUTIVE_ERRORS:
                bot.status = "error"
                bot.error = str(e)[:300]
                bot_log(db, bot, f"Stopped after {n} errors in a row", "error")
                alert(db, bot, f"Bot stopped after {n} errors in a row. Last error: {e}")
                _errors.pop(bot.id, None)
            db.commit()
            send_pending(db)
        except Exception:
            db.rollback()
            discard(db)
            log.exception("bot %s failed", bot.id)
    return len(bots)


def backtest(candles: list[dict], strategy: str, params: dict, stop_loss_pct: float | None,
             take_profit_pct: float | None, trade_size: float, capital: float, spread_bps: float = 0,
             direction: str = "long", risk_pct: float | None = None) -> dict:
    """Replay the strategy candle by candle. Entries and signal exits fill at the candle close,
    stops fill at the stop price (or the open, if price gapped through it). A short holds its
    full value as collateral, like the paper broker."""
    signals = STRATEGIES[strategy].signals(candles, params)
    half = spread_bps / 2 / 10_000
    cash, qty, entry, entry_time, side = capital, 0.0, 0.0, 0, None
    trades, equity = [], []

    def value(price):  # what the open position is worth at this price, collateral included
        return qty * price if side == "long" else qty * (2 * entry - price)

    def close(price, t, reason):
        nonlocal cash, qty, side
        sign = 1 if side == "long" else -1
        cash += value(price)
        trades.append({"side": side, "entry_time": entry_time, "exit_time": t, "entry_price": entry, "exit_price": price,
                       "quantity": qty, "pnl": round(sign * (price - entry) * qty, 2),
                       "return_pct": round(sign * (price / entry - 1) * 100, 3), "reason": reason})
        qty, side = 0.0, None

    for c, sig in zip(candles, signals):
        if side == "long":
            sl = entry * (1 - stop_loss_pct / 100) if stop_loss_pct else None
            tp = entry * (1 + take_profit_pct / 100) if take_profit_pct else None
            if sl and c["low"] <= sl:
                close(min(c["open"], sl), c["time"], "stop_loss")
            elif tp and c["high"] >= tp:
                close(max(c["open"], tp), c["time"], "take_profit")
        elif side == "short":
            sl = entry * (1 + stop_loss_pct / 100) if stop_loss_pct else None
            tp = entry * (1 - take_profit_pct / 100) if take_profit_pct else None
            if sl and c["high"] >= sl:
                close(max(c["open"], sl), c["time"], "stop_loss")
            elif tp and c["low"] <= tp:
                close(min(c["open"], tp), c["time"], "take_profit")
        want = {"buy": "long", "sell": "short"}.get(sig)
        if want and side and side != want:
            close(c["close"] * (1 - half if side == "long" else 1 + half), c["time"], "signal")
        if want and side is None and direction in (want, "both"):
            price = c["close"] * (1 + half if want == "long" else 1 - half)
            size = trade_size
            if risk_pct and stop_loss_pct:
                size = min(size, cash * risk_pct / stop_loss_pct)
            size = min(size, cash)
            if size > 0:
                qty, entry, entry_time, side = size / price, price, c["time"], want
                cash -= size
        equity.append({"time": c["time"], "value": round(cash + (value(c["close"]) if side else 0), 2)})

    final = equity[-1]["value"] if equity else capital
    peak, max_dd = capital, 0.0
    for e in equity:
        peak = max(peak, e["value"])
        max_dd = max(max_dd, (peak - e["value"]) / peak * 100)
    wins = [t for t in trades if t["pnl"] > 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in trades if t["pnl"] <= 0)
    return {
        "start_capital": capital,
        "final_equity": final,
        "total_return_pct": round((final / capital - 1) * 100, 2),
        "buy_hold_return_pct": round((candles[-1]["close"] / candles[0]["close"] - 1) * 100, 2) if candles else 0,
        "trades": len(trades),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else None,
        "max_drawdown_pct": round(max_dd, 2),
        "open_position": bool(side),
        "trade_list": trades,
        "equity_curve": equity,
        "from": candles[0]["time"] if candles else None,
        "to": candles[-1]["time"] if candles else None,
    }
