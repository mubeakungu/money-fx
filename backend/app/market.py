"""Mock market data.

Prices are a deterministic function of (symbol, time), so every process, chart and
order fill sees the same price for the same moment and history is available for any
range without storing ticks. Swap `MockFeed` for a live provider later by
implementing the same `price_at` / `quote` / `candles` methods.
"""
import hashlib
import math
import time
from decimal import ROUND_HALF_UP, Decimal

# symbol, name, asset_class, base_price, daily volatility, spread (bps), price dp, qty dp, min qty
INSTRUMENTS = [
    ("EURUSD", "Euro / US Dollar", "forex", "1.0850", 0.005, 1.0, 5, 0, "1"),
    ("GBPUSD", "British Pound / US Dollar", "forex", "1.2700", 0.006, 1.2, 5, 0, "1"),
    ("AUDUSD", "Australian Dollar / US Dollar", "forex", "0.6600", 0.007, 1.5, 5, 0, "1"),
    ("NZDUSD", "New Zealand Dollar / US Dollar", "forex", "0.6000", 0.007, 1.8, 5, 0, "1"),
    ("BTCUSD", "Bitcoin", "crypto", "68000", 0.035, 5.0, 2, 6, "0.000001"),
    ("ETHUSD", "Ethereum", "crypto", "3400", 0.045, 6.0, 2, 5, "0.00001"),
    ("SOLUSD", "Solana", "crypto", "160", 0.06, 8.0, 3, 4, "0.0001"),
    ("AAPL", "Apple Inc.", "stock", "225", 0.016, 2.0, 2, 4, "0.0001"),
    ("MSFT", "Microsoft Corp.", "stock", "430", 0.015, 2.0, 2, 4, "0.0001"),
    ("TSLA", "Tesla Inc.", "stock", "250", 0.035, 3.0, 2, 4, "0.0001"),
    ("NVDA", "NVIDIA Corp.", "stock", "130", 0.03, 2.5, 2, 4, "0.0001"),
    ("XAUUSD", "Gold (troy oz)", "commodity", "2400", 0.01, 3.0, 2, 3, "0.001"),
    ("XAGUSD", "Silver (troy oz)", "commodity", "29", 0.018, 4.0, 3, 2, "0.01"),
    ("WTIUSD", "WTI Crude Oil (bbl)", "commodity", "78", 0.02, 4.0, 2, 2, "0.01"),
]

# Overlapping cycles from 90 seconds to ~11 days give movement at every chart zoom.
_PERIODS = [90, 420, 2460, 18000, 172800, 950400]
_AMPLITUDES = [0.05, 0.1, 0.2, 0.35, 0.5, 0.7]  # in units of the instrument's daily volatility
DAY = 86400


def _seed(symbol: str, k: int) -> float:
    h = hashlib.sha256(f"{symbol}:{k}".encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def _noise(symbol: str, bucket: int) -> float:
    h = hashlib.blake2b(f"{symbol}:{bucket}".encode(), digest_size=8).digest()
    return int.from_bytes(h, "big") / 2**63 - 1.0


class MockFeed:
    def __init__(self):
        self._spec = {}
        for row in INSTRUMENTS:
            symbol, _, _, base, vol, spread, pdp, *_ = row
            phases = [_seed(symbol, k) * 2 * math.pi for k in range(len(_PERIODS))]
            self._spec[symbol] = (float(base), vol, spread, pdp, phases)

    def symbols(self):
        return list(self._spec)

    def price_at(self, symbol: str, t: float) -> float:
        base, vol, _, _, phases = self._spec[symbol]
        x = 0.0
        for period, amp, phase in zip(_PERIODS, _AMPLITUDES, phases):
            x += amp * math.sin(2 * math.pi * t / period + phase)
        x += 0.01 * _noise(symbol, int(t // 5))
        return base * math.exp(vol * x)

    def _q(self, symbol: str, value: float) -> Decimal:
        dp = self._spec[symbol][3]
        return Decimal(str(value)).quantize(Decimal(1).scaleb(-dp), rounding=ROUND_HALF_UP)

    def quote(self, symbol: str, t: float | None = None) -> dict:
        t = time.time() if t is None else t
        _, _, spread, _, _ = self._spec[symbol]
        mid = self.price_at(symbol, t)
        prev = self.price_at(symbol, t - DAY)
        half = spread / 2 / 10_000
        return {
            "symbol": symbol,
            "bid": self._q(symbol, mid * (1 - half)),
            "ask": self._q(symbol, mid * (1 + half)),
            "mid": self._q(symbol, mid),
            "change_24h_pct": round((mid / prev - 1) * 100, 3),
            "ts": int(t * 1000),
        }

    def candles(self, symbol: str, interval: int, limit: int, end: float | None = None) -> list[dict]:
        end = time.time() if end is None else end
        last_open = int(end // interval) * interval
        step = max(interval / 12, 1)
        out = []
        for i in range(limit - 1, -1, -1):
            start = last_open - i * interval
            stop = min(start + interval, end)
            samples, t = [], start
            while t < stop:
                samples.append(self.price_at(symbol, t))
                t += step
            samples.append(self.price_at(symbol, stop))
            out.append({
                "time": start,
                "open": float(self._q(symbol, samples[0])),
                "high": float(self._q(symbol, max(samples))),
                "low": float(self._q(symbol, min(samples))),
                "close": float(self._q(symbol, samples[-1])),
            })
        return out


feed = MockFeed()
