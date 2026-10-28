// Port of backend/app/strategies.py and the backtester in backend/app/bots.py.
import { rsi, sma } from '../indicators'

const p = (name, label, def, min, max) => ({ name, label, default: def, min, max, integer: true })

export const STRATEGIES = {
  sma_cross: {
    key: 'sma_cross', name: 'Moving average crossover',
    description: 'Buys when the fast average crosses above the slow one (uptrend starting) and sells when it crosses back below.',
    params: [p('fast', 'Fast period', 9, 2, 100), p('slow', 'Slow period', 21, 3, 300)],
    signals(c, pr) {
      const closes = c.map((x) => x.close)
      const f = sma(closes, pr.fast)
      const s = sma(closes, pr.slow)
      return closes.map((_, i) => {
        if (i === 0 || [f[i], s[i], f[i - 1], s[i - 1]].includes(null)) return null
        if (f[i - 1] <= s[i - 1] && f[i] > s[i]) return 'buy'
        if (f[i - 1] >= s[i - 1] && f[i] < s[i]) return 'sell'
        return null
      })
    },
  },
  rsi: {
    key: 'rsi', name: 'RSI mean reversion',
    description: 'Buys when RSI climbs back out of oversold and sells when it falls back from overbought.',
    params: [p('period', 'RSI period', 14, 2, 100), p('oversold', 'Oversold level', 30, 5, 50), p('overbought', 'Overbought level', 70, 50, 95)],
    signals(c, pr) {
      const r = rsi(c.map((x) => x.close), pr.period)
      return c.map((_, i) => {
        if (i === 0 || r[i] === null || r[i - 1] === null) return null
        if (r[i - 1] < pr.oversold && pr.oversold <= r[i]) return 'buy'
        if (r[i - 1] > pr.overbought && pr.overbought >= r[i]) return 'sell'
        return null
      })
    },
  },
  breakout: {
    key: 'breakout', name: 'Channel breakout',
    description: 'Buys when price closes above the highest high of the last N candles and sells on a close below the lowest low.',
    params: [p('lookback', 'Lookback candles', 20, 3, 200)],
    signals(c, pr) {
      const n = pr.lookback
      return c.map((x, i) => {
        if (i < n) return null
        const w = c.slice(i - n, i)
        if (x.close > Math.max(...w.map((y) => y.high))) return 'buy'
        if (x.close < Math.min(...w.map((y) => y.low))) return 'sell'
        return null
      })
    },
  },
}

export function validate(key, raw = {}) {
  const s = STRATEGIES[key]
  if (!s) throw new Error(`Unknown strategy ${key}`)
  const out = {}
  for (const prm of s.params) {
    const v = Number(raw[prm.name] ?? prm.default)
    if (!(v >= prm.min && v <= prm.max)) throw new Error(`${prm.label} must be between ${prm.min} and ${prm.max}`)
    out[prm.name] = Math.trunc(v)
  }
  if (key === 'sma_cross' && out.fast >= out.slow) throw new Error('Fast period must be shorter than slow period')
  return out
}

export function backtest(candles, key, params, sl, tp, tradeSize, capital, spreadBps = 0, direction = 'long', riskPct = null) {
  const signals = STRATEGIES[key].signals(candles, params)
  const half = spreadBps / 2 / 10000
  let cash = capital
  let qty = 0
  let entry = 0
  let entryTime = 0
  let side = null
  const trades = []
  const equity = []
  // What the open position is worth at a price; a short holds its full value as collateral
  const value = (price) => (side === 'long' ? qty * price : qty * (2 * entry - price))
  const close = (price, t, reason) => {
    const sign = side === 'long' ? 1 : -1
    cash += value(price)
    trades.push({ side, entry_time: entryTime, exit_time: t, entry_price: entry, exit_price: price, quantity: qty,
      pnl: Math.round(sign * (price - entry) * qty * 100) / 100, return_pct: sign * (price / entry - 1) * 100, reason })
    qty = 0
    side = null
  }
  candles.forEach((c, i) => {
    if (side === 'long') {
      const slp = sl ? entry * (1 - sl / 100) : null
      const tpp = tp ? entry * (1 + tp / 100) : null
      if (slp && c.low <= slp) close(Math.min(c.open, slp), c.time, 'stop_loss')
      else if (tpp && c.high >= tpp) close(Math.max(c.open, tpp), c.time, 'take_profit')
    } else if (side === 'short') {
      const slp = sl ? entry * (1 + sl / 100) : null
      const tpp = tp ? entry * (1 - tp / 100) : null
      if (slp && c.high >= slp) close(Math.max(c.open, slp), c.time, 'stop_loss')
      else if (tpp && c.low <= tpp) close(Math.min(c.open, tpp), c.time, 'take_profit')
    }
    const want = { buy: 'long', sell: 'short' }[signals[i]]
    if (want && side && side !== want) close(c.close * (side === 'long' ? 1 - half : 1 + half), c.time, 'signal')
    if (want && !side && (direction === want || direction === 'both')) {
      const price = c.close * (want === 'long' ? 1 + half : 1 - half)
      let size = tradeSize
      if (riskPct && sl) size = Math.min(size, (cash * riskPct) / sl)
      size = Math.min(size, cash)
      if (size > 0) {
        qty = size / price
        entry = price
        entryTime = c.time
        side = want
        cash -= size
      }
    }
    equity.push({ time: c.time, value: Math.round((cash + (side ? value(c.close) : 0)) * 100) / 100 })
  })
  const final = equity.length ? equity[equity.length - 1].value : capital
  let peak = capital
  let dd = 0
  for (const e of equity) {
    peak = Math.max(peak, e.value)
    dd = Math.max(dd, ((peak - e.value) / peak) * 100)
  }
  const wins = trades.filter((t) => t.pnl > 0)
  const gw = wins.reduce((s, t) => s + t.pnl, 0)
  const gl = -trades.filter((t) => t.pnl <= 0).reduce((s, t) => s + t.pnl, 0)
  const r2 = (v) => Math.round(v * 100) / 100
  return {
    start_capital: capital, final_equity: final, total_return_pct: r2((final / capital - 1) * 100),
    buy_hold_return_pct: candles.length ? r2((candles[candles.length - 1].close / candles[0].close - 1) * 100) : 0,
    trades: trades.length, win_rate_pct: trades.length ? Math.round((wins.length / trades.length) * 1000) / 10 : 0,
    profit_factor: gl ? r2(gw / gl) : null, max_drawdown_pct: r2(dd), open_position: !!side,
    trade_list: trades, equity_curve: equity, from: candles[0]?.time, to: candles[candles.length - 1]?.time,
  }
}
