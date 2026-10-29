// The money fx API, running inside the browser for the published demo. It mirrors the
// FastAPI routes the app calls, keeps state in memory (saved to this browser when it can),
// and runs the limit-order matcher and the bots on timers instead of a server.
import { BY_SYMBOL, INSTRUMENTS, candles, fixed, quote, roundTo } from './feed'
import { STRATEGIES, backtest, validate } from './strategies'

const KEY = 'moneyfx_demo_v1'
const INTERVALS = { '1m': 60, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400 }
const now = () => new Date().toISOString()
const qtyStr = (v, dp = 8) => String(roundTo(v, dp))
const money = (v) => fixed(v, 2)
const ceilCents = (v) => Math.ceil(Math.round(v * 1e6) / 1e4) / 100
const floorCents = (v) => Math.floor(Math.round(v * 1e6) / 1e4) / 100

export class DemoError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}
const fail = (status, msg) => { throw new DemoError(status, msg) }

function freshState() {
  return {
    seq: 1,
    user: { id: 1, email: 'demo@moneyfx.app', full_name: 'Demo Trader', country: 'KE', created_at: now(), account_id: 1, account_status: 'active' },
    wallet: { balance: 0, locked: 0 },
    txns: [], orders: [], positions: {}, bots: [], botTrades: [], botLogs: [],
  }
}

let S = load()

function load() {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* storage blocked: start fresh */ }
  return null
}
function save() {
  try { localStorage.setItem(KEY, JSON.stringify(S)) } catch { /* fine, the demo just won't persist */ }
}
const id = () => S.seq++

function txn(type, amount, extra = {}) {
  const t = { id: id(), type, amount: money(amount), balance_after: money(S.wallet.balance), method: null, reference: null, order_id: null, status: 'completed', created_at: now(), ...extra }
  S.txns.unshift(t)
  return t
}
const walletOut = () => ({ id: 1, currency: 'USD', balance: money(S.wallet.balance), locked: money(S.wallet.locked), available: money(S.wallet.balance - S.wallet.locked) })
const pos = (sym) => (S.positions[sym] ??= { quantity: 0, avg_price: 0, realized_pnl: 0 })
const openSellQty = (sym, exclude) => S.orders.filter((o) => o.symbol === sym && o.side === 'sell' && o.status === 'open' && o.id !== exclude).reduce((s, o) => s + Number(o.quantity), 0)

function deposit(amount, method) {
  S.wallet.balance += amount
  return txn('deposit', amount, { method, reference: `DEP-${Math.random().toString(36).slice(2, 12).toUpperCase()}` })
}

function fill(o, price) {
  const p = pos(o.symbol)
  const q = Number(o.quantity)
  const dp = BY_SYMBOL[o.symbol].price_decimals
  let amount
  if (o.side === 'buy') {
    const cost = ceilCents(price * q)
    S.wallet.locked -= o.reserved
    o.reserved = 0
    S.wallet.balance -= cost
    p.avg_price = (p.quantity * p.avg_price + q * price) / (p.quantity + q)
    p.quantity += q
    amount = -cost
  } else {
    const proceeds = floorCents(price * q)
    S.wallet.balance += proceeds
    p.realized_pnl += (price - p.avg_price) * q
    p.quantity = roundTo(p.quantity - q, 10)
    if (p.quantity <= 0) { p.quantity = 0; p.avg_price = 0 }
    amount = proceeds
  }
  o.status = 'filled'
  o.filled_price = fixed(price, dp)
  o.filled_at = now()
  txn(`trade_${o.side}`, amount, { order_id: o.id, reference: `${o.side.toUpperCase()} ${o.quantity} ${o.symbol} @ ${fixed(price, dp)}` })
}

function placeOrder({ symbol, side, type = 'market', quantity, limit_price }) {
  const inst = BY_SYMBOL[String(symbol).toUpperCase()] ?? fail(400, `Unknown instrument ${symbol}`)
  const q = Number(quantity)
  if (!(q > 0) || roundTo(q, inst.qty_decimals) !== q || q < inst.min_qty) {
    fail(400, `Quantity must be at least ${inst.min_qty} with at most ${inst.qty_decimals} decimal places`)
  }
  let limit = null
  if (type === 'limit') {
    if (!(Number(limit_price) > 0)) fail(400, 'Limit orders need a limit_price')
    limit = roundTo(Number(limit_price), inst.price_decimals)
  }
  const o = { id: id(), symbol: inst.symbol, side, type, quantity: qtyStr(q), limit_price: limit === null ? null : fixed(limit, inst.price_decimals),
    status: 'open', filled_price: null, reject_reason: null, created_at: now(), filled_at: null, reserved: 0 }
  S.orders.unshift(o)
  const qt = quote(inst.symbol)
  const avail = S.wallet.balance - S.wallet.locked
  const reject = (r) => { o.status = 'rejected'; o.reject_reason = r; return o }
  if (side === 'buy') {
    const need = ceilCents((type === 'market' ? qt.ask : limit) * q)
    if (need > avail + 1e-9) return reject(`Insufficient funds: need ${money(need)} USD, available ${money(avail)}`)
    if (type === 'market') fill(o, qt.ask)
    else {
      o.reserved = need
      S.wallet.locked += need
      if (qt.ask <= limit) fill(o, qt.ask)
    }
  } else {
    const free = pos(inst.symbol).quantity - openSellQty(inst.symbol, o.id)
    if (q > free + 1e-12) return reject(`Insufficient holdings: you can sell up to ${qtyStr(Math.max(free, 0))} ${inst.symbol}`)
    if (type === 'market' || qt.bid >= limit) fill(o, qt.bid)
  }
  return o
}

const orderOut = ({ reserved, ...o }) => o

function portfolio() {
  const positions = []
  let realized = 0
  const allocation = { cash: money(S.wallet.balance) }
  const alloc = { cash: S.wallet.balance }
  for (const [sym, p] of Object.entries(S.positions)) {
    realized += p.realized_pnl
    if (p.quantity <= 0) continue
    const inst = BY_SYMBOL[sym]
    const price = quote(sym).bid
    const value = price * p.quantity
    const cost = p.avg_price * p.quantity
    const pnl = value - cost
    positions.push({ symbol: sym, name: inst.name, asset_class: inst.asset_class, quantity: qtyStr(p.quantity),
      avg_price: String(roundTo(p.avg_price, inst.price_decimals + 2)), price: fixed(price, inst.price_decimals),
      market_value: money(value), unrealized_pnl: money(pnl), unrealized_pnl_pct: cost ? roundTo((pnl / cost) * 100, 2) : 0,
      realized_pnl: money(p.realized_pnl), _v: value })
    alloc[inst.asset_class] = (alloc[inst.asset_class] ?? 0) + value
  }
  for (const [k, v] of Object.entries(alloc)) allocation[k] = money(v)
  positions.sort((a, b) => b._v - a._v)
  const pv = positions.reduce((s, p) => s + p._v, 0)
  const net = S.txns.filter((t) => t.type === 'deposit' || t.type === 'withdrawal').reduce((s, t) => s + Number(t.amount), 0)
  return {
    cash: money(S.wallet.balance), cash_locked: money(S.wallet.locked), positions_value: money(pv),
    equity: money(S.wallet.balance + pv), unrealized_pnl: money(positions.reduce((s, p) => s + Number(p.unrealized_pnl), 0)),
    realized_pnl: money(realized), net_deposits: money(net), allocation,
    positions: positions.map(({ _v, ...p }) => p),
  }
}

// ---- bots ----
const botLog = (bot, message, level = 'info') => S.botLogs.unshift({ id: id(), bot_id: bot.id, level, message, created_at: now() })
const closedCandles = (bot, n = 300) => candles(bot.symbol, INTERVALS[bot.interval], n + 1).slice(0, -1)

const stopPrices = (bot, entry, side) => {
  const sign = side === 'short' ? -1 : 1
  return [bot.stop_loss_pct ? entry * (1 - (sign * bot.stop_loss_pct) / 100) : null,
    bot.take_profit_pct ? entry * (1 + (sign * bot.take_profit_pct) / 100) : null]
}

function todaysBotPnl() {
  const midnight = new Date()
  midnight.setUTCHours(0, 0, 0, 0)
  return S.botTrades.filter((t) => t.action === 'close' && new Date(t.created_at) >= midnight).reduce((s, t) => s + Number(t.pnl), 0)
}

function dailyLimitReached(bot) {
  const limit = Number(S.settings?.daily_loss_limit_usd)
  if (!limit) return false
  const pnl = todaysBotPnl()
  if (pnl > -limit) return false
  const today = new Date().toISOString().slice(0, 10)
  if (bot._limitLogged !== today) {
    bot._limitLogged = today
    botLog(bot, `Daily loss limit reached (bots lost ${(-pnl).toFixed(2)} of ${limit.toFixed(2)} USD today). No new trades until 00:00 UTC; open positions keep their stops.`, 'error')
  }
  return true
}

function botOpen(bot, side) {
  const inst = BY_SYMBOL[bot.symbol]
  const q = quote(bot.symbol)
  let size = Number(bot.trade_size_usd)
  if (bot.risk_pct && bot.stop_loss_pct) size = Math.min(size, (S.wallet.balance * bot.risk_pct) / bot.stop_loss_pct)
  const price = side === 'long' ? q.ask : q.bid
  const qty = Math.floor((size / price) * 10 ** inst.qty_decimals) / 10 ** inst.qty_decimals
  if (qty < inst.min_qty) throw new Error(`Trade size too small: minimum is ${inst.min_qty} ${bot.symbol}`)
  let fillPrice
  if (side === 'long') {
    const o = placeOrder({ symbol: bot.symbol, side: 'buy', quantity: qty })
    if (o.status !== 'filled') throw new Error(o.reject_reason)
    fillPrice = o.filled_price
  } else {
    // The paper account has no short positions, so a bot short reserves its full value as collateral
    const collateral = q.bid * qty
    if (S.wallet.balance - S.wallet.locked < collateral) throw new Error(`Insufficient funds: a ${collateral.toFixed(2)} USD short needs that much available cash`)
    S.wallet.locked += collateral
    fillPrice = fixed(q.bid, inst.price_decimals)
  }
  bot.position_qty = qtyStr(qty)
  bot.position_side = side
  bot.entry_price = fillPrice
  S.botTrades.unshift({ id: id(), bot_id: bot.id, action: 'open', side, reason: 'signal', quantity: bot.position_qty, price: fillPrice, pnl: null, created_at: now() })
  const [slp, tpp] = stopPrices(bot, Number(fillPrice), side)
  const stops = [slp && `stop-loss ${roundTo(slp, inst.price_decimals)}`, tpp && `take-profit ${roundTo(tpp, inst.price_decimals)}`].filter(Boolean).join(', ')
  botLog(bot, `${side === 'long' ? 'Bought' : 'Sold short'} ${bot.position_qty} ${bot.symbol} at ${fillPrice}${stops ? ` (${stops})` : ''}`)
}

function botClose(bot, reason) {
  const side = bot.position_side ?? 'long'
  const qty = Number(bot.position_qty)
  const entry = Number(bot.entry_price)
  let price, pnl
  if (side === 'long') {
    const o = placeOrder({ symbol: bot.symbol, side: 'sell', quantity: bot.position_qty })
    if (o.status !== 'filled') throw new Error(o.reject_reason)
    price = o.filled_price
    pnl = (Number(price) - entry) * qty
  } else {
    const ask = quote(bot.symbol).ask
    price = fixed(ask, BY_SYMBOL[bot.symbol].price_decimals)
    pnl = (entry - ask) * qty
    S.wallet.locked -= entry * qty
    S.wallet.balance += pnl
    txn('bot_short', pnl, { reference: `Bot ${bot.name}: short ${bot.position_qty} ${bot.symbol} closed` })
  }
  bot.realized_pnl = money(Number(bot.realized_pnl) + pnl)
  bot.trades_closed += 1
  if (pnl > 0) bot.wins += 1
  S.botTrades.unshift({ id: id(), bot_id: bot.id, action: 'close', side, reason, quantity: bot.position_qty, price, pnl: money(pnl), created_at: now() })
  const label = { signal: 'signal', stop_loss: 'stop-loss', take_profit: 'take-profit', manual: 'you closed it' }[reason]
  botLog(bot, `${side === 'long' ? 'Sold' : 'Bought back'} ${bot.position_qty} ${bot.symbol} at ${price} (${label}), P&L ${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}`)
  bot.position_qty = '0'
  bot.position_side = null
  bot.entry_price = null
}

function stepBot(bot) {
  if (Number(bot.position_qty) > 0) {
    const side = bot.position_side ?? 'long'
    const [slp, tpp] = stopPrices(bot, Number(bot.entry_price), side)
    const q = quote(bot.symbol)
    if (side === 'long') {
      if (slp && q.bid <= slp) botClose(bot, 'stop_loss')
      else if (tpp && q.bid >= tpp) botClose(bot, 'take_profit')
    } else if (slp && q.ask >= slp) botClose(bot, 'stop_loss')
    else if (tpp && q.ask <= tpp) botClose(bot, 'take_profit')
  }
  const c = closedCandles(bot)
  const last = c[c.length - 1].time
  if (bot.last_candle_time === null) {
    bot.last_candle_time = last
    botLog(bot, `Watching ${bot.symbol} on ${bot.interval} candles`)
    return
  }
  if (last <= bot.last_candle_time) return
  bot.last_candle_time = last
  const want = { buy: 'long', sell: 'short' }[STRATEGIES[bot.strategy].signals(c, bot.params).at(-1)]
  if (!want) return
  let side = Number(bot.position_qty) > 0 ? (bot.position_side ?? 'long') : null
  if (side && side !== want) {
    botClose(bot, 'signal')
    side = null
  }
  const direction = bot.direction ?? 'long'
  if (!side && (direction === want || direction === 'both') && !dailyLimitReached(bot)) botOpen(bot, want)
}

function tick() {
  let changed = false
  for (const o of S.orders) {
    if (o.status !== 'open') continue
    const q = quote(o.symbol)
    const lim = Number(o.limit_price)
    if (o.side === 'buy' && q.ask <= lim) { fill(o, q.ask); changed = true }
    else if (o.side === 'sell' && q.bid >= lim) { fill(o, q.bid); changed = true }
  }
  for (const bot of S.bots) {
    if (bot.status !== 'running') continue
    try {
      stepBot(bot)
      bot._errors = 0
    } catch (e) {
      bot._errors = (bot._errors ?? 0) + 1
      botLog(bot, e.message, 'error')
      if (bot._errors >= 5) {
        bot.status = 'error'
        bot.error = e.message
        botLog(bot, `Stopped after ${bot._errors} errors in a row`, 'error')
      }
    }
    changed = true
  }
  if (changed) save()
}

const settingsOut = () => ({ daily_loss_limit_usd: S.settings?.daily_loss_limit_usd ?? null, today_pnl_usd: money(todaysBotPnl()),
  telegram: { available: false, connected: false } })
const botOut = ({ _errors, _limitLogged, last_candle_time, ...b }) => b

function createBot(body) {
  const symbol = String(body.symbol).toUpperCase()
  if (!BY_SYMBOL[symbol]) fail(400, `Unknown instrument ${body.symbol}`)
  if (body.broker === 'oanda') fail(400, 'OANDA is not available in the demo. Deploy the full app to trade OANDA.')
  let params
  try { params = validate(body.strategy, body.params) } catch (e) { fail(400, e.message) }
  if (!(Number(body.trade_size_usd) > 0)) fail(400, 'Size per trade must be more than 0')
  if (body.risk_pct && !body.stop_loss_pct) fail(400, 'Risk-based sizing needs a stop-loss: the stop decides how much a trade can lose')
  return { symbol, params }
}

function seed() {
  S = freshState()
  deposit(10000, 'card')
  placeOrder({ symbol: 'BTCUSD', side: 'buy', quantity: 0.02 })
  placeOrder({ symbol: 'AAPL', side: 'buy', quantity: 8 })
  placeOrder({ symbol: 'EURUSD', side: 'buy', quantity: 1500 })
  placeOrder({ symbol: 'XAUUSD', side: 'buy', quantity: 0.4 })
  const bot = { id: id(), name: 'Gold trend (example)', symbol: 'XAUUSD', broker: 'paper', strategy: 'sma_cross', params: { fast: 3, slow: 8 },
    interval: '1m', trade_size_usd: '1000', stop_loss_pct: 0.3, take_profit_pct: 0.5, direction: 'both', risk_pct: null,
    status: 'running', error: null, position_qty: '0', position_side: null, entry_price: null, realized_pnl: '0.00', trades_closed: 0, wins: 0, created_at: now(), last_candle_time: null }
  S.bots.push(bot)
  botLog(bot, 'Created: Moving average crossover on XAUUSD 1m, buys and sells short, 1000 USD per trade, via paper trading')
  botLog(bot, 'Started')
  save()
}

if (!S) seed()
setInterval(tick, 2000)

export function resetDemo() {
  seed()
}

const ok = (v) => v

// Route table: [method, pattern, handler(match, body, query)]
const routes = [
  ['GET', /^\/auth\/me$/, () => S.user],
  ['PATCH', /^\/auth\/me$/, (_, b) => {
    if (b.full_name) S.user.full_name = b.full_name.trim()
    if (b.country !== undefined) S.user.country = b.country ? b.country.toUpperCase() : null
    save()
    return S.user
  }],
  ['POST', /^\/auth\/change-password$/, () => null],
  ['POST', /^\/auth\/(login|register)$/, () => ({ access_token: 'demo', token_type: 'bearer' })],
  ['GET', /^\/wallet$/, walletOut],
  ['POST', /^\/wallet\/deposit$/, (_, b) => {
    const a = Number(b.amount)
    if (!(a > 0)) fail(422, 'Amount must be greater than 0')
    if (a > 1e6) fail(400, 'Maximum single deposit is 1,000,000 USD')
    const t = deposit(roundTo(a, 2), b.method)
    save()
    return t
  }],
  ['POST', /^\/wallet\/withdraw$/, (_, b) => {
    const a = roundTo(Number(b.amount), 2)
    if (!(a > 0)) fail(422, 'Amount must be greater than 0')
    const avail = S.wallet.balance - S.wallet.locked
    if (a > avail + 1e-9) fail(400, `Insufficient available balance (${money(avail)} USD)`)
    S.wallet.balance -= a
    const t = txn('withdrawal', -a, { method: b.method, reference: `WDR-${Math.random().toString(36).slice(2, 12).toUpperCase()}` })
    save()
    return t
  }],
  ['GET', /^\/wallet\/transactions$/, (_, __, q) => S.txns.slice(0, Number(q.get('limit') ?? 50))],
  ['GET', /^\/markets\/instruments$/, () => INSTRUMENTS.map(({ base, vol, spread, ...i }) => ({ ...i, min_qty: String(i.min_qty) }))],
  ['GET', /^\/markets\/candles\/(\w+)$/, (m, _, q) => {
    const sym = m[1].toUpperCase()
    if (!BY_SYMBOL[sym]) fail(404, 'Unknown instrument')
    return candles(sym, INTERVALS[q.get('interval') ?? '1m'], Math.min(Number(q.get('limit') ?? 200), 1000))
  }],
  ['GET', /^\/orders$/, (_, __, q) => S.orders.filter((o) => !q.get('status') || o.status === q.get('status')).slice(0, Number(q.get('limit') ?? 100)).map(orderOut)],
  ['POST', /^\/orders$/, (_, b) => { const o = placeOrder(b); save(); return orderOut(o) }],
  ['DELETE', /^\/orders\/(\d+)$/, (m) => {
    const o = S.orders.find((x) => x.id === Number(m[1])) ?? fail(404, 'Order not found')
    if (o.status !== 'open') fail(400, 'Only open orders can be cancelled')
    S.wallet.locked -= o.reserved
    o.reserved = 0
    o.status = 'cancelled'
    save()
    return orderOut(o)
  }],
  ['GET', /^\/portfolio$/, portfolio],
  ['GET', /^\/bots\/strategies$/, () => Object.values(STRATEGIES).map(({ key, name, description, params }) => ({ key, name, description, params }))],
  ['GET', /^\/bots\/brokers$/, () => ({ paper: { configured: true }, oanda: { configured: false, allowed: false, environment: 'practice', symbols: [] } })],
  ['POST', /^\/bots\/backtest$/, (_, b) => {
    const { symbol, params } = createBot(b)
    const c = candles(symbol, INTERVALS[b.interval], Math.min(Number(b.bars) || 500, 5000) + 1).slice(0, -1)
    return { ...backtest(c, b.strategy, params, b.stop_loss_pct, b.take_profit_pct, Number(b.trade_size_usd), Number(b.capital) || 10000,
      BY_SYMBOL[symbol].spread, b.direction ?? 'long', b.risk_pct ?? null), data_source: 'money fx simulated feed' }
  }],
  ['GET', /^\/bots\/settings$/, settingsOut],
  ['GET', /^\/bots\/positions$/, () => S.bots.filter((b) => Number(b.position_qty) > 0).map((b) => {
    const side = b.position_side ?? 'long'
    const q = quote(b.symbol)
    const dp = BY_SYMBOL[b.symbol].price_decimals
    const price = side === 'long' ? q.bid : q.ask
    const entry = Number(b.entry_price)
    const [sl, tp] = stopPrices(b, entry, side)
    const opened = S.botTrades.find((t) => t.bot_id === b.id && t.action === 'open')
    return { bot_id: b.id, bot: b.name, broker: 'paper', symbol: b.symbol, side, quantity: b.position_qty, entry_price: b.entry_price,
      price: fixed(price, dp), unrealized_pnl: money((side === 'long' ? price - entry : entry - price) * Number(b.position_qty)),
      stop_loss: sl ? fixed(sl, dp) : null, take_profit: tp ? fixed(tp, dp) : null, status: b.status, opened_at: opened?.created_at ?? null, external_id: null }
  })],
  ['PUT', /^\/bots\/settings$/, (_, b) => {
    const v = b.daily_loss_limit_usd == null || b.daily_loss_limit_usd === '' ? null : Number(b.daily_loss_limit_usd)
    if (v !== null && !(v > 0)) fail(422, 'Daily loss limit must be more than 0')
    S.settings = { daily_loss_limit_usd: v === null ? null : String(v) }
    save()
    return settingsOut()
  }],
  ['GET', /^\/bots$/, () => [...S.bots].reverse().map(botOut)],
  ['POST', /^\/bots$/, (_, b) => {
    const { symbol, params } = createBot(b)
    const bot = { id: id(), name: (b.name || `${symbol} ${STRATEGIES[b.strategy].name}`).trim(), symbol, broker: 'paper', strategy: b.strategy, params,
      interval: b.interval, trade_size_usd: String(Number(b.trade_size_usd)), stop_loss_pct: b.stop_loss_pct ?? null, take_profit_pct: b.take_profit_pct ?? null,
      direction: b.direction ?? 'long', risk_pct: b.risk_pct ?? null, status: 'stopped', error: null, position_qty: '0', position_side: null, entry_price: null, realized_pnl: '0.00', trades_closed: 0, wins: 0, created_at: now(), last_candle_time: null }
    S.bots.push(bot)
    const trades = { long: 'buys only', short: 'sells short only', both: 'buys and sells short' }[bot.direction]
    const size = bot.risk_pct ? `risking ${bot.risk_pct}% of the balance per trade, at most ${bot.trade_size_usd} USD` : `${bot.trade_size_usd} USD per trade`
    botLog(bot, `Created: ${STRATEGIES[b.strategy].name} on ${symbol} ${b.interval}, ${trades}, ${size}, via paper trading`)
    save()
    return botOut(bot)
  }],
  ['GET', /^\/bots\/(\d+)$/, (m) => {
    const bot = S.bots.find((x) => x.id === Number(m[1])) ?? fail(404, 'Bot not found')
    const open = Number(bot.position_qty) > 0
    return {
      bot: botOut(bot),
      unrealized_pnl: open ? money((bot.position_side === 'short' ? Number(bot.entry_price) - quote(bot.symbol).ask
        : quote(bot.symbol).bid - Number(bot.entry_price)) * Number(bot.position_qty)) : null,
      trades: S.botTrades.filter((t) => t.bot_id === bot.id),
      logs: S.botLogs.filter((l) => l.bot_id === bot.id).slice(0, 200),
    }
  }],
  ['POST', /^\/bots\/(\d+)\/(start|stop|close-position)$/, (m) => {
    const bot = S.bots.find((x) => x.id === Number(m[1])) ?? fail(404, 'Bot not found')
    if (m[2] === 'start') {
      bot.status = 'running'
      bot.error = null
      bot.last_candle_time = null
      bot._errors = 0
      botLog(bot, 'Started')
    } else if (m[2] === 'stop') {
      bot.status = 'stopped'
      botLog(bot, Number(bot.position_qty) > 0 ? 'Stopped (open position kept)' : 'Stopped')
    } else {
      if (!(Number(bot.position_qty) > 0)) fail(400, 'This bot has no open position')
      try { botClose(bot, 'manual') } catch (e) { fail(400, e.message) }
    }
    save()
    return botOut(bot)
  }],
  ['DELETE', /^\/bots\/(\d+)$/, (m) => {
    const bot = S.bots.find((x) => x.id === Number(m[1])) ?? fail(404, 'Bot not found')
    if (bot.status === 'running' || Number(bot.position_qty) > 0) fail(400, 'Stop the bot and close its position before deleting it')
    S.bots = S.bots.filter((x) => x !== bot)
    S.botTrades = S.botTrades.filter((t) => t.bot_id !== bot.id)
    S.botLogs = S.botLogs.filter((l) => l.bot_id !== bot.id)
    save()
    return null
  }],
]

export async function handle(method, path, body) {
  const [p, qs] = path.split('?')
  const query = new URLSearchParams(qs ?? '')
  for (const [m, re, fn] of routes) {
    const match = m === method && p.match(re)
    if (match) return ok(structuredClone(fn(match, body ?? {}, query) ?? null))
  }
  fail(404, 'Not found')
}
