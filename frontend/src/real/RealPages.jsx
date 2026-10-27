import { useEffect, useState } from 'react'
import { api } from '../api'
import { useAccountMode } from '../account'
import { signClass, usd } from '../format'
import { ClosedTrades, OpenTrades, PendingOrders } from './RealTrades'

function usePoll(path, ms = 3000) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let stop = false
    const load = () => api(path).then((d) => { if (!stop) { setData(d); setError(null) } }).catch((e) => !stop && setError(e.message))
    load()
    const t = setInterval(load, ms)
    return () => { stop = true; clearInterval(t) }
  }, [path, ms, tick])
  return [data, error, () => setTick((n) => n + 1)]
}

function Card({ label, value, sub, cls = '' }) {
  return (
    <div className="panel card">
      <div className="muted xs">{label}</div>
      <div className={`card-value mono ${cls}`}>{value}</div>
      {sub && <div className="muted xs">{sub}</div>}
    </div>
  )
}

const money = (v, cur) => (cur === 'USD' || !cur ? usd(v ?? 0) : `${Number(v ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${cur}`)

function AccountCards({ a }) {
  if (!a) return null
  return (
    <div className="cards">
      <Card label="Balance" value={money(a.balance, a.currency)} sub={`OANDA ${a.environment} · ${a.id}`} />
      <Card label="Equity (NAV)" value={money(a.nav, a.currency)} />
      <Card label="Open P&L" value={money(a.unrealized_pnl, a.currency)} cls={signClass(a.unrealized_pnl)} />
      <Card label="Margin used" value={money(a.margin_used, a.currency)} sub={`${money(a.margin_available, a.currency)} available`} />
      <Card label="Open trades" value={a.open_trades ?? 0} sub={`${a.pending_orders ?? 0} pending orders`} />
    </div>
  )
}

export function RealPortfolio() {
  const [a, err] = usePoll('/real/account')
  const [open, , reloadOpen] = usePoll('/real/trades')
  const [closed, , reloadClosed] = usePoll('/real/trades?state=closed', 10000)
  const reload = () => { reloadOpen(); reloadClosed() }
  return (
    <div className="page">
      <div className="page-head"><h2>Portfolio · OANDA</h2></div>
      {err && <div className="notice err">{err}</div>}
      <AccountCards a={a} />
      <div className="panel"><h3>Open positions</h3>{open ? <OpenTrades trades={open} onChange={reload} /> : <p className="muted">Loading…</p>}</div>
      <div className="panel"><h3>Closed trades</h3>{closed ? <ClosedTrades trades={closed} /> : <p className="muted">Loading…</p>}</div>
    </div>
  )
}

export function RealOrders() {
  const [pending, err, reload] = usePoll('/real/orders')
  const [closed] = usePoll('/real/trades?state=closed', 10000)
  return (
    <div className="page">
      <div className="page-head"><h2>Orders · OANDA</h2></div>
      {err && <div className="notice err">{err}</div>}
      <div className="panel"><h3>Pending orders</h3>{pending ? <PendingOrders orders={pending} onChange={reload} /> : <p className="muted">Loading…</p>}</div>
      <div className="panel"><h3>Trade history</h3>{closed ? <ClosedTrades trades={closed} /> : <p className="muted">Loading…</p>}</div>
    </div>
  )
}

export function RealWallet() {
  const [a, err] = usePoll('/real/account', 5000)
  const { real } = useAccountMode()
  return (
    <div className="page">
      <div className="page-head"><h2>Wallet · OANDA</h2></div>
      {err && <div className="notice err">{err}</div>}
      <AccountCards a={a} />
      <div className="panel">
        <h3>Deposits and withdrawals</h3>
        <p className="muted">
          Money moves in and out of your real account through OANDA itself, so it stays protected by OANDA's checks.
          Use the OANDA website or app to fund or withdraw. Your {real?.environment === 'live' ? 'live' : 'practice'} balance updates here automatically.
        </p>
        <a className="btn ghost" href="https://www.oanda.com/" target="_blank" rel="noreferrer">Open OANDA</a>
      </div>
    </div>
  )
}
