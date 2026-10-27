// In-browser port of backend/app/market.py: prices are a deterministic function of
// (symbol, time) built from smooth noise at 13 time scales, so they behave like a random walk.
export const INSTRUMENTS = [
  ['EURUSD', 'Euro / US Dollar', 'forex', 1.085, 0.005, 1.0, 5, 0, 1],
  ['GBPUSD', 'British Pound / US Dollar', 'forex', 1.27, 0.006, 1.2, 5, 0, 1],
  ['AUDUSD', 'Australian Dollar / US Dollar', 'forex', 0.66, 0.007, 1.5, 5, 0, 1],
  ['NZDUSD', 'New Zealand Dollar / US Dollar', 'forex', 0.6, 0.007, 1.8, 5, 0, 1],
  ['BTCUSD', 'Bitcoin', 'crypto', 68000, 0.035, 5.0, 2, 6, 0.000001],
  ['ETHUSD', 'Ethereum', 'crypto', 3400, 0.045, 6.0, 2, 5, 0.00001],
  ['SOLUSD', 'Solana', 'crypto', 160, 0.06, 8.0, 3, 4, 0.0001],
  ['AAPL', 'Apple Inc.', 'stock', 225, 0.016, 2.0, 2, 4, 0.0001],
  ['MSFT', 'Microsoft Corp.', 'stock', 430, 0.015, 2.0, 2, 4, 0.0001],
  ['TSLA', 'Tesla Inc.', 'stock', 250, 0.035, 3.0, 2, 4, 0.0001],
  ['NVDA', 'NVIDIA Corp.', 'stock', 130, 0.03, 2.5, 2, 4, 0.0001],
  ['XAUUSD', 'Gold (troy oz)', 'commodity', 2400, 0.01, 3.0, 2, 3, 0.001],
  ['XAGUSD', 'Silver (troy oz)', 'commodity', 29, 0.018, 4.0, 3, 2, 0.01],
  ['WTIUSD', 'WTI Crude Oil (bbl)', 'commodity', 78, 0.02, 4.0, 2, 2, 0.01],
].map(([symbol, name, asset_class, base, vol, spread, price_decimals, qty_decimals, min_qty], i) => ({
  id: i + 1, symbol, name, asset_class, quote_currency: 'USD', base, vol, spread, price_decimals, qty_decimals, min_qty,
}))
export const BY_SYMBOL = Object.fromEntries(INSTRUMENTS.map((i) => [i.symbol, i]))

const SCALES = Array.from({ length: 13 }, (_, k) => 5 * 3 ** k)
const WEIGHTS = SCALES.map((s) => Math.sqrt(s / 86400))
const DAY = 86400

function seedOf(symbol) {
  let h = 2166136261
  for (const ch of symbol) h = Math.imul(h ^ ch.charCodeAt(0), 16777619)
  return h | 0
}
const SEEDS = Object.fromEntries(INSTRUMENTS.map((i) => [i.symbol, seedOf(i.symbol)]))

function hash(seed, k, i) {
  let x = (seed ^ Math.imul(k + 1, 0x9e3779b1) ^ Math.imul(i, 0x85ebca77)) | 0
  x ^= x >>> 16
  x = Math.imul(x, 0x7feb352d)
  x ^= x >>> 15
  x = Math.imul(x, 0x846ca68b)
  x ^= x >>> 16
  return (x >>> 0) / 2147483648 - 1
}

export function priceAt(symbol, t) {
  const inst = BY_SYMBOL[symbol]
  const seed = SEEDS[symbol]
  let x = 0
  for (let k = 0; k < SCALES.length; k++) {
    const u = t / SCALES[k]
    const i = Math.floor(u)
    let f = u - i
    f = f * f * (3 - 2 * f)
    const a = hash(seed, k, i)
    x += WEIGHTS[k] * (a + (hash(seed, k, i + 1) - a) * f)
  }
  return inst.base * Math.exp(inst.vol * x)
}

export const roundTo = (v, dp) => Math.round(v * 10 ** dp) / 10 ** dp
export const fixed = (v, dp) => roundTo(v, dp).toFixed(dp)

export function quote(symbol, t = Date.now() / 1000) {
  const inst = BY_SYMBOL[symbol]
  const mid = priceAt(symbol, t)
  const half = inst.spread / 2 / 10000
  const dp = inst.price_decimals
  return {
    symbol,
    bid: roundTo(mid * (1 - half), dp),
    ask: roundTo(mid * (1 + half), dp),
    mid: roundTo(mid, dp),
    change_24h_pct: roundTo((mid / priceAt(symbol, t - DAY) - 1) * 100, 3),
    ts: Math.round(t * 1000),
  }
}

export function quoteJson(symbol) {
  const q = quote(symbol)
  const dp = BY_SYMBOL[symbol].price_decimals
  return { ...q, bid: fixed(q.bid, dp), ask: fixed(q.ask, dp), mid: fixed(q.mid, dp) }
}

export function candles(symbol, interval, limit, end = Date.now() / 1000) {
  const dp = BY_SYMBOL[symbol].price_decimals
  const lastOpen = Math.floor(end / interval) * interval
  const step = Math.max(interval / 12, 1)
  const out = []
  for (let n = limit - 1; n >= 0; n--) {
    const start = lastOpen - n * interval
    const stop = Math.min(start + interval, end)
    const s = []
    for (let t = start; t < stop; t += step) s.push(priceAt(symbol, t))
    s.push(priceAt(symbol, stop))
    out.push({ time: start, open: roundTo(s[0], dp), high: roundTo(Math.max(...s), dp), low: roundTo(Math.min(...s), dp), close: roundTo(s[s.length - 1], dp) })
  }
  return out
}
