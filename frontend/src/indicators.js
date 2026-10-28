// Indicators shared by the charts and the in-browser demo. sma and rsi match backend/app/strategies.py.

export function sma(values, n) {
  let total = 0
  return values.map((v, i) => {
    total += v
    if (i >= n) total -= values[i - n]
    return i >= n - 1 ? total / n : null
  })
}

/** Wilder's RSI. */
export function rsi(closes, n) {
  const out = closes.map(() => null)
  if (closes.length <= n) return out
  let g = 0
  let l = 0
  for (let i = 1; i <= n; i++) {
    const d = closes[i] - closes[i - 1]
    g += Math.max(d, 0)
    l += Math.max(-d, 0)
  }
  let ag = g / n
  let al = l / n
  for (let i = n; i < closes.length; i++) {
    if (i > n) {
      const d = closes[i] - closes[i - 1]
      ag = (ag * (n - 1) + Math.max(d, 0)) / n
      al = (al * (n - 1) + Math.max(-d, 0)) / n
    }
    out[i] = al === 0 ? 100 : 100 - 100 / (1 + ag / al)
  }
  return out
}

/** Highest high and lowest low of the n candles before each candle (the breakout strategy's channel). */
export function channel(candles, n) {
  return {
    upper: candles.map((_, i) => (i < n ? null : Math.max(...candles.slice(i - n, i).map((c) => c.high)))),
    lower: candles.map((_, i) => (i < n ? null : Math.min(...candles.slice(i - n, i).map((c) => c.low)))),
  }
}

/** Line series data; candles with no value yet become whitespace so the line starts late. */
export const lineData = (candles, values) => candles.map((c, i) => (values[i] == null ? { time: c.time } : { time: c.time, value: values[i] }))
