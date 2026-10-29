import { useState } from 'react'
import { api } from '../api'
import { dateTime, num, signClass, usd } from '../format'

const unixDate = (s) => (s ? dateTime(new Date(Number(s) * 1000).toISOString()) : '')

export function OpenTrades({ trades, onChange, compact }) {
  const [err, setErr] = useState(null)
  const [closing, setClosing] = useState(null)
  const close = async (id) => {
    if (closing !== id) return setClosing(id)
    setErr(null)
    try { await api(`/real/trades/${id}/close`, { method: 'POST' }) } catch (e) { setErr(e.message) }
    setClosing(null)
    onChange?.()
  }
  if (!trades.length) return <p className="muted">No open positions on OANDA.</p>
  return (
    <div className="table-wrap">
      {err && <div className="notice err">{err}</div>}
      <table>
        <thead>
          <tr><th>Market</th><th>Side</th><th className="r">Units</th><th className="r">Open price</th>
            {!compact && <th className="r">Stop-loss</th>}{!compact && <th className="r">Take-profit</th>}
            <th className="r">P&L</th><th /></tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr key={t.id}>
              <td><span className="sym">{t.symbol}</span>{t.bot && <div className="muted xs">bot: {t.bot}</div>}</td>
              <td className={t.side === 'buy' ? 'up' : 'down'}>{t.side === 'buy' ? 'LONG' : 'SHORT'}</td>
              <td className="r mono">{num(t.units)}</td>
              <td className="r mono">{t.open_price}</td>
              {!compact && <td className="r mono">{t.stop_loss ?? '—'}</td>}
              {!compact && <td className="r mono">{t.take_profit ?? '—'}</td>}
              <td className={`r mono ${signClass(t.unrealized_pnl)}`}>{usd(t.unrealized_pnl ?? 0, { signDisplay: 'exceptZero' })}</td>
              <td className="r">
                <button className="btn ghost sm" onClick={() => close(t.id)}>{closing === t.id ? 'Confirm close' : 'Close'}</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function ClosedTrades({ trades }) {
  if (!trades.length) return <p className="muted">No closed trades yet.</p>
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Closed</th><th>Market</th><th>Side</th><th className="r">Units</th><th className="r">Open</th><th className="r">Close</th><th className="r">P&L</th></tr></thead>
        <tbody>
          {trades.map((t) => (
            <tr key={t.id}>
              <td className="muted">{unixDate(t.closed_at)}</td>
              <td><span className="sym">{t.symbol}</span>{t.bot && <div className="muted xs">bot: {t.bot}</div>}</td>
              <td className={t.side === 'buy' ? 'up' : 'down'}>{t.side === 'buy' ? 'LONG' : 'SHORT'}</td>
              <td className="r mono">{num(t.units)}</td>
              <td className="r mono">{t.open_price}</td>
              <td className="r mono">{t.close_price ?? '—'}</td>
              <td className={`r mono ${signClass(t.realized_pnl)}`}>{usd(t.realized_pnl ?? 0, { signDisplay: 'exceptZero' })}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function PendingOrders({ orders, onChange }) {
  const [err, setErr] = useState(null)
  const cancel = async (id) => {
    setErr(null)
    try { await api(`/real/orders/${id}`, { method: 'DELETE' }) } catch (e) { setErr(e.message) }
    onChange?.()
  }
  if (!orders.length) return <p className="muted">No pending orders.</p>
  return (
    <div className="table-wrap">
      {err && <div className="notice err">{err}</div>}
      <table>
        <thead><tr><th>Placed</th><th>Market</th><th>Side</th><th>Type</th><th className="r">Units</th><th className="r">Price</th><th /></tr></thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.id}>
              <td className="muted">{unixDate(o.created_at)}</td>
              <td className="sym">{o.symbol}</td>
              <td className={o.side === 'buy' ? 'up' : 'down'}>{o.side.toUpperCase()}</td>
              <td>{o.type}</td>
              <td className="r mono">{num(o.units)}</td>
              <td className="r mono">{o.price}</td>
              <td className="r"><button className="btn ghost sm" onClick={() => cancel(o.id)}>Cancel</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
