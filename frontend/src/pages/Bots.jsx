import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import EquityChart from '../components/EquityChart'
import { num, pct, signClass, usd } from '../format'
import { useQuotes } from '../quotes'

const INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d']
const REASONS = { signal: 'Signal', stop_loss: 'Stop-loss', take_profit: 'Take-profit', manual: 'Manual', closed_on_oanda: 'Closed on OANDA' }

export function BrokerBanner({ brokers }) {
  if (!brokers) return null
  const o = brokers.oanda
  if (!o.allowed) return <div className="panel banner">Bots run in paper mode on simulated prices.</div>
  if (!o.configured) {
    return (
      <div className="panel banner">
        <strong>OANDA not connected.</strong> Bots run in paper mode on simulated prices. To trade your OANDA account, set{' '}
        <code>OANDA_API_TOKEN</code>, <code>OANDA_ACCOUNT_ID</code> and <code>OANDA_ENV=practice</code> on the server and restart it (see README).
      </div>
    )
  }
  if (o.error) return <div className="panel banner err"><strong>OANDA error:</strong> {o.error}</div>
  return (
    <div className="panel banner ok">
      <strong>OANDA {o.environment === 'live' ? 'LIVE' : 'practice'} connected</strong>
      {o.account && <> · account {o.account.id} · balance {num(o.account.balance, 2)} {o.account.currency} · NAV {num(o.account.NAV, 2)}</>}
      {o.environment === 'live' && <span className="pill rejected" style={{ marginLeft: 8 }}>real money</span>}
    </div>
  )
}

function BotForm({ strategies, brokers, onBacktest, onCreated }) {
  const { instruments } = useQuotes()
  const [f, setF] = useState({
    name: '', broker: 'paper', symbol: 'EURUSD', strategy: 'sma_cross', interval: '5m',
    trade_size_usd: '1000', stop_loss_pct: '1', take_profit_pct: '2', bars: '1000',
  })
  const [params, setParams] = useState({})
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  const strat = strategies.find((s) => s.key === f.strategy)
  const symbols = f.broker === 'oanda' ? instruments.filter((i) => brokers?.oanda.symbols.includes(i.symbol)) : instruments

  useEffect(() => {
    if (strat) setParams(Object.fromEntries(strat.params.map((p) => [p.name, String(p.default)])))
  }, [strat])
  useEffect(() => {
    if (symbols.length && !symbols.some((i) => i.symbol === f.symbol)) setF((x) => ({ ...x, symbol: symbols[0].symbol }))
  }, [f.broker, symbols.length])

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const body = () => ({
    ...f,
    name: f.name || `${f.symbol} ${strat?.name ?? ''}`.trim(),
    params: Object.fromEntries(Object.entries(params).map(([k, v]) => [k, Number(v)])),
    stop_loss_pct: f.stop_loss_pct ? Number(f.stop_loss_pct) : null,
    take_profit_pct: f.take_profit_pct ? Number(f.take_profit_pct) : null,
    bars: Number(f.bars),
  })
  const run = async (kind) => {
    setBusy(kind)
    setError(null)
    try {
      if (kind === 'backtest') onBacktest(await api('/bots/backtest', { method: 'POST', body: body() }), body())
      else onCreated(await api('/bots', { method: 'POST', body: body() }))
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <form className="panel bot-form" onSubmit={(e) => { e.preventDefault(); run('backtest') }}>
      <h3>New bot</h3>
      <div className="form-grid">
        <label>Name<input value={f.name} placeholder="optional" onChange={set('name')} /></label>
        <label>Trade on
          <select value={f.broker} onChange={set('broker')}>
            <option value="paper">Paper (simulated)</option>
            <option value="oanda" disabled={!brokers?.oanda.configured}>OANDA {brokers?.oanda.configured ? `(${brokers.oanda.environment})` : '(not connected)'}</option>
          </select>
        </label>
        <label>Market
          <select value={f.symbol} onChange={set('symbol')}>
            {symbols.map((i) => <option key={i.symbol} value={i.symbol}>{i.symbol} · {i.name}</option>)}
          </select>
        </label>
        <label>Candle size
          <select value={f.interval} onChange={set('interval')}>{INTERVALS.map((i) => <option key={i}>{i}</option>)}</select>
        </label>
        <label className="span2">Strategy
          <select value={f.strategy} onChange={set('strategy')}>
            {strategies.map((s) => <option key={s.key} value={s.key}>{s.name}</option>)}
          </select>
          {strat && <span className="hint">{strat.description}</span>}
        </label>
        {strat?.params.map((p) => (
          <label key={p.name}>{p.label}
            <input className="mono" inputMode="decimal" value={params[p.name] ?? ''} onChange={(e) => setParams({ ...params, [p.name]: e.target.value })} />
          </label>
        ))}
        <label>Size per trade (USD)<input className="mono" inputMode="decimal" value={f.trade_size_usd} onChange={set('trade_size_usd')} required /></label>
        <label>Stop-loss %<input className="mono" inputMode="decimal" value={f.stop_loss_pct} placeholder="none" onChange={set('stop_loss_pct')} /></label>
        <label>Take-profit %<input className="mono" inputMode="decimal" value={f.take_profit_pct} placeholder="none" onChange={set('take_profit_pct')} /></label>
        <label>Backtest candles<input className="mono" inputMode="numeric" value={f.bars} onChange={set('bars')} /></label>
      </div>
      <div className="actions">
        <button className="btn ghost" disabled={!!busy}>{busy === 'backtest' ? 'Testing…' : 'Run backtest'}</button>
        <button type="button" className="btn" disabled={!!busy} onClick={() => run('create')}>{busy === 'create' ? 'Creating…' : 'Create bot'}</button>
      </div>
      {error && <div className="notice err">{error}</div>}
    </form>
  )
}

function BacktestResult({ r, cfg }) {
  const beat = r.total_return_pct > r.buy_hold_return_pct
  return (
    <div className="panel">
      <div className="row-between">
        <h3>Backtest · {cfg.symbol} {cfg.interval} · {r.trades} trades</h3>
        <span className="muted xs">{new Date(r.from * 1000).toLocaleString()} → {new Date(r.to * 1000).toLocaleString()} · {r.data_source}</span>
      </div>
      <div className="cards">
        <Stat label="Return" value={pct(r.total_return_pct)} cls={signClass(r.total_return_pct)} sub={`${usd(r.start_capital)} → ${usd(r.final_equity)}`} />
        <Stat label="Buy & hold" value={pct(r.buy_hold_return_pct)} cls={signClass(r.buy_hold_return_pct)} sub={beat ? 'Strategy did better' : 'Strategy did worse'} />
        <Stat label="Win rate" value={`${r.win_rate_pct}%`} />
        <Stat label="Profit factor" value={r.profit_factor ?? '—'} sub="gross wins ÷ gross losses" />
        <Stat label="Max drawdown" value={`-${r.max_drawdown_pct}%`} cls="down" />
      </div>
      <EquityChart curve={r.equity_curve} trades={r.trade_list} />
      {r.trades === 0 && <p className="muted">No trades in this period. Try a smaller candle size, more candles, or different settings.</p>}
      <p className="muted xs">Past results do not guarantee future returns. Backtests ignore slippage and assume fills at the candle close.</p>
    </div>
  )
}

function Stat({ label, value, sub, cls = '' }) {
  return (
    <div className="card">
      <div className="muted xs">{label}</div>
      <div className={`card-value mono ${cls}`}>{value}</div>
      {sub && <div className="muted xs">{sub}</div>}
    </div>
  )
}

export function BotCard({ bot, strategies, onChange }) {
  const strat = strategies.find((s) => s.key === bot.strategy)
  const [confirming, setConfirming] = useState(false)
  const [err, setErr] = useState(null)
  const act = async (path, method = 'POST') => {
    setErr(null)
    try { await api(`/bots/${bot.id}${path}`, { method }) } catch (e) { setErr(e.message) }
    setConfirming(false)
    onChange()
  }
  const winRate = bot.trades_closed ? Math.round((bot.wins / bot.trades_closed) * 100) : null
  return (
    <div className="panel bot-card">
      <div className="row-between">
        <Link to={`/bots/${bot.id}`} className="sym">{bot.name}</Link>
        <span className={`pill ${bot.status === 'running' ? 'filled' : bot.status === 'error' ? 'rejected' : ''}`}>{bot.status}</span>
      </div>
      <div className="muted xs">
        {bot.symbol} · {bot.interval} · {strat?.name} ({Object.values(bot.params).join('/')}) · {bot.broker === 'oanda' ? 'OANDA' : 'Paper'}
      </div>
      <dl className="kv">
        <dt>Position</dt><dd className="mono">{Number(bot.position_qty) ? `${num(bot.position_qty)} @ ${bot.entry_price}` : 'Flat'}</dd>
        <dt>Realized P&L</dt><dd className={`mono ${signClass(bot.realized_pnl)}`}>{usd(bot.realized_pnl, { signDisplay: 'exceptZero' })}</dd>
        <dt>Closed trades</dt><dd className="mono">{bot.trades_closed}{winRate !== null && ` · ${winRate}% wins`}</dd>
        <dt>Risk</dt><dd className="mono">{usd(bot.trade_size_usd, { maximumFractionDigits: 0 })} · SL {bot.stop_loss_pct ?? '—'}% · TP {bot.take_profit_pct ?? '—'}%</dd>
      </dl>
      {(err || bot.error) && <div className="notice err">{err || bot.error}</div>}
      <div className="actions">
        {bot.status === 'running'
          ? <button className="btn ghost sm" onClick={() => act('/stop')}>Stop</button>
          : <button className="btn sm" onClick={() => act('/start')}>Start</button>}
        {Number(bot.position_qty) > 0 && <button className="btn ghost sm" onClick={() => act('/close-position')}>Close position</button>}
        <Link className="btn ghost sm" to={`/bots/${bot.id}`}>Activity</Link>
        {bot.status !== 'running' && !Number(bot.position_qty) && (confirming
          ? <button className="btn ghost sm danger" onClick={() => act('', 'DELETE')}>Confirm delete</button>
          : <button className="btn ghost sm danger" onClick={() => setConfirming(true)}>Delete</button>)}
      </div>
    </div>
  )
}

export default function Bots() {
  const [strategies, setStrategies] = useState([])
  const [brokers, setBrokers] = useState(null)
  const [bots, setBots] = useState([])
  const [result, setResult] = useState(null)
  const load = () => api('/bots').then(setBots)

  useEffect(() => {
    api('/bots/strategies').then(setStrategies)
    api('/bots/brokers').then(setBrokers)
    load()
    const id = setInterval(load, 3000)
    return () => clearInterval(id)
  }, [])

  const total = useMemo(() => bots.reduce((s, b) => s + Number(b.realized_pnl), 0), [bots])

  return (
    <div className="page">
      <div className="page-head">
        <h2>Trading bots</h2>
        {bots.length > 0 && <span className="muted">Bots realized P&L <span className={`mono ${signClass(total)}`}>{usd(total, { signDisplay: 'exceptZero' })}</span></span>}
      </div>
      <BrokerBanner brokers={brokers} />
      {bots.length > 0 && <div className="bot-grid">{bots.map((b) => <BotCard key={b.id} bot={b} strategies={strategies} onChange={load} />)}</div>}
      {strategies.length > 0 && (
        <BotForm strategies={strategies} brokers={brokers} onBacktest={(r, cfg) => setResult({ r, cfg })}
          onCreated={() => { load(); window.scrollTo({ top: 0, behavior: 'smooth' }) }} />
      )}
      {result && <BacktestResult {...result} />}
    </div>
  )
}

export { REASONS }
