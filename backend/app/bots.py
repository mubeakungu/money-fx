"""Bot engine: runs each active bot once per closed candle, and a backtester that replays
the same strategy over history."""
import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .brokers import BrokerError, Fill, get_broker, stop_prices
from .strategies import STRATEGIES

log = logging.getLogger("moneyfx.bots")
WARMUP_BARS = 300
MAX_CONSECUTIVE_ERRORS = 5
_errors: dict[int, int] = {}


def bot_log(db: Session, bot: models.Bot, message: str, level: str = "info"):
    db.add(models.BotLog(bot_id=bot.id, level=level, message=message[:400]))


def _fmt(d: Decimal) -> str:
    return f"{d.normalize():f}"


def record_open(db: Session, bot: models.Bot, fill: Fill):
    bot.position_qty = fill.quantity
    bot.entry_price = fill.price
    bot.external_trade_id = fill.external_id
    db.add(models.BotTrade(bot_id=bot.id, action="open", reason="signal", quantity=fill.quantity, price=fill.price,
                           order_id=fill.order_id, external_id=fill.external_id))
    sl, tp = stop_prices(fill.price, bot)
    stops = ", ".join(s for s in [sl and f"stop-loss {sl:.5g}", tp and f"take-profit {tp:.5g}"] if s)
    bot_log(db, bot, f"Bought {_fmt(fill.quantity)} {bot.symbol} at {fill.price}" + (f" ({stops})" if stops else ""))


def record_close(db: Session, bot: models.Bot, fill: Fill):
    pnl = fill.pnl if fill.pnl is not None else (fill.price - bot.entry_price) * fill.quantity
    bot.realized_pnl += pnl
    bot.trades_closed += 1
    bot.wins += 1 if pnl > 0 else 0
    db.add(models.BotTrade(bot_id=bot.id, action="close", reason=fill.reason or "signal", quantity=fill.quantity,
                           price=fill.price, pnl=pnl, order_id=fill.order_id, external_id=fill.external_id))
    label = {"signal": "sell signal", "stop_loss": "stop-loss", "take_profit": "take-profit",
             "manual": "you closed it", "closed_on_oanda": "closed on OANDA"}.get(fill.reason, fill.reason)
    bot_log(db, bot, f"Sold {_fmt(fill.quantity)} {bot.symbol} at {fill.price} ({label}), P&L {pnl:+.2f}")
    bot.position_qty = Decimal(0)
    bot.entry_price = None
    bot.external_trade_id = None


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
    signal = STRATEGIES[bot.strategy].signals(candles, bot.params)[-1]

    if signal == "buy" and bot.position_qty == 0:
        ask = broker.quote(bot.symbol)["ask"]
        qty = broker.units_for(db, bot.symbol, bot.trade_size_usd, ask)
        record_open(db, bot, broker.open_long(db, bot, qty))
    elif signal == "sell" and bot.position_qty > 0:
        record_close(db, bot, broker.close_long(db, bot, "signal"))


def run_bots(db: Session) -> int:
    bots = db.scalars(select(models.Bot).where(models.Bot.status == "running")).all()
    for bot in bots:
        try:
            step(db, bot)
            db.commit()
            _errors.pop(bot.id, None)
        except BrokerError as e:
            db.rollback()
            n = _errors[bot.id] = _errors.get(bot.id, 0) + 1
            bot_log(db, bot, str(e), "error")
            if n >= MAX_CONSECUTIVE_ERRORS:
                bot.status = "error"
                bot.error = str(e)[:300]
                bot_log(db, bot, f"Stopped after {n} errors in a row", "error")
                _errors.pop(bot.id, None)
            db.commit()
        except Exception:
            db.rollback()
            log.exception("bot %s failed", bot.id)
    return len(bots)


def backtest(candles: list[dict], strategy: str, params: dict, stop_loss_pct: float | None,
             take_profit_pct: float | None, trade_size: float, capital: float, spread_bps: float = 0) -> dict:
    """Replay the strategy candle by candle. Entries and signal exits fill at the candle close,
    stops fill at the stop price (or the open, if price gapped through it)."""
    signals = STRATEGIES[strategy].signals(candles, params)
    half = spread_bps / 2 / 10_000
    cash, qty, entry, entry_time = capital, 0.0, 0.0, 0
    trades, equity = [], []

    def close(price, t, reason):
        nonlocal cash, qty
        pnl = (price - entry) * qty
        cash += price * qty
        trades.append({"entry_time": entry_time, "exit_time": t, "entry_price": entry, "exit_price": price,
                       "quantity": qty, "pnl": round(pnl, 2), "return_pct": round((price / entry - 1) * 100, 3),
                       "reason": reason})
        qty = 0.0

    for c, sig in zip(candles, signals):
        if qty:
            sl = entry * (1 - stop_loss_pct / 100) if stop_loss_pct else None
            tp = entry * (1 + take_profit_pct / 100) if take_profit_pct else None
            if sl and c["low"] <= sl:
                close(min(c["open"], sl), c["time"], "stop_loss")
            elif tp and c["high"] >= tp:
                close(max(c["open"], tp), c["time"], "take_profit")
        if sig == "buy" and not qty:
            price = c["close"] * (1 + half)
            size = min(trade_size, cash)
            if size > 0:
                qty, entry, entry_time = size / price, price, c["time"]
                cash -= size
        elif sig == "sell" and qty:
            close(c["close"] * (1 - half), c["time"], "signal")
        equity.append({"time": c["time"], "value": round(cash + qty * c["close"], 2)})

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
        "open_position": bool(qty),
        "trade_list": trades,
        "equity_curve": equity,
        "from": candles[0]["time"] if candles else None,
        "to": candles[-1]["time"] if candles else None,
    }
