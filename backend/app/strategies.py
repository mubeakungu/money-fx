"""Trading strategies. Each one turns a candle series into one signal per candle:
"buy", "sell" or None. The bot acts on the signal of the last closed candle, and the
backtester walks the whole list, so both always agree.
"""
from dataclasses import dataclass, field


@dataclass
class Param:
    name: str
    label: str
    default: float
    min: float
    max: float
    integer: bool = True


@dataclass
class Strategy:
    key: str
    name: str
    description: str
    params: list[Param] = field(default_factory=list)

    def signals(self, candles: list[dict], p: dict) -> list[str | None]:
        raise NotImplementedError

    def clean_params(self, raw: dict | None) -> dict:
        raw = raw or {}
        out = {}
        for prm in self.params:
            v = float(raw.get(prm.name, prm.default))
            if not prm.min <= v <= prm.max:
                raise ValueError(f"{prm.label} must be between {prm.min:g} and {prm.max:g}")
            out[prm.name] = int(v) if prm.integer else v
        return out


def sma(values: list[float], n: int) -> list[float | None]:
    out, total = [], 0.0
    for i, v in enumerate(values):
        total += v
        if i >= n:
            total -= values[i - n]
        out.append(total / n if i >= n - 1 else None)
    return out


def rsi(closes: list[float], n: int) -> list[float | None]:
    """Wilder's RSI."""
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    avg_g, avg_l = gains / n, losses / n
    for i in range(n, len(closes)):
        if i > n:
            d = closes[i] - closes[i - 1]
            avg_g = (avg_g * (n - 1) + max(d, 0)) / n
            avg_l = (avg_l * (n - 1) + max(-d, 0)) / n
        out[i] = 100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    return out


class SmaCross(Strategy):
    def signals(self, candles, p):
        closes = [c["close"] for c in candles]
        fast, slow = sma(closes, p["fast"]), sma(closes, p["slow"])
        out = [None] * len(closes)
        for i in range(1, len(closes)):
            if None in (fast[i], slow[i], fast[i - 1], slow[i - 1]):
                continue
            if fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]:
                out[i] = "buy"
            elif fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]:
                out[i] = "sell"
        return out


class RsiReversion(Strategy):
    def signals(self, candles, p):
        r = rsi([c["close"] for c in candles], p["period"])
        out = [None] * len(candles)
        for i in range(1, len(candles)):
            if r[i] is None or r[i - 1] is None:
                continue
            if r[i - 1] < p["oversold"] <= r[i]:
                out[i] = "buy"
            elif r[i - 1] > p["overbought"] >= r[i]:
                out[i] = "sell"
        return out


class Breakout(Strategy):
    def signals(self, candles, p):
        n = p["lookback"]
        out = [None] * len(candles)
        for i in range(n, len(candles)):
            window = candles[i - n:i]
            if candles[i]["close"] > max(c["high"] for c in window):
                out[i] = "buy"
            elif candles[i]["close"] < min(c["low"] for c in window):
                out[i] = "sell"
        return out


STRATEGIES: dict[str, Strategy] = {s.key: s for s in [
    SmaCross("sma_cross", "Moving average crossover",
             "Buys when the fast average crosses above the slow one (uptrend starting) and sells when it crosses back below.",
             [Param("fast", "Fast period", 9, 2, 100), Param("slow", "Slow period", 21, 3, 300)]),
    RsiReversion("rsi", "RSI mean reversion",
                 "Buys when RSI climbs back out of oversold and sells when it falls back from overbought.",
                 [Param("period", "RSI period", 14, 2, 100), Param("oversold", "Oversold level", 30, 5, 50),
                  Param("overbought", "Overbought level", 70, 50, 95)]),
    Breakout("breakout", "Channel breakout",
             "Buys when price closes above the highest high of the last N candles and sells on a close below the lowest low.",
             [Param("lookback", "Lookback candles", 20, 3, 200)]),
]}


def validate(strategy: str, params: dict | None) -> dict:
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy {strategy}")
    p = STRATEGIES[strategy].clean_params(params)
    if strategy == "sma_cross" and p["fast"] >= p["slow"]:
        raise ValueError("Fast period must be shorter than slow period")
    return p
