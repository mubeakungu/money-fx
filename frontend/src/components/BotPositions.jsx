import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { num, signClass, usd } from '../format'

/** Open trades held by your bots, with live P&L. Hidden when `hideEmpty` and there are none. */
export default function BotPositions({ broker = 'all', compact, hideEmpty }) {
  const [rows, setRows] = useState(null)
  const [closing, setClosing] = useState(null)
  const [err, setErr] = useState(null)
  const load = () => api(`/bots/positions?broker=${broker}`).then(setRows).catch(() => {})

  useEffect(() => {
    load()
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [broker])

  const close = async (id) => {
    if (closing !== id) return setClosing(id)
    setErr(null)
    try { await api(`/bots/${id}/close-position`, { method: 'POST' }) } catch (e) { setErr(e.message) }
    setClosing(null)
    load()
  }

  if (!rows || (hideEmpty && !rows.length)) return null
  const total = rows.reduce((s, r) => s + Number(r.unrealized_pnl ?? 0), 0)
  return (
    <div className="panel">
      <div className="row-between">
        <h3>Open bot trades</h3>
        {rows.length > 0 && <span className="muted">Open P&L <span className={`mono ${signClass(total)}`}>{usd(total, { signDisplay: 'exceptZero' })}</span></span>}
      </div>
      {err && <div className="notice err">{err}</div>}
      {rows.length === 0 ? <p className="muted">Your bots have no open trades right now. <Link to="/bots">Go to Bots</Link></p> : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Bot</th><th>Market</th><th>Side</th><th className="r">Qty</th><th className="r">Entry</th><th className="r">Now</th>
                {!compact && <th className="r">Stop-loss</th>}{!compact && <th className="r">Take-profit</th>}
                <th className="r">P&L</th><th /></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.bot_id}>
                  <td><Link to={`/bots/${r.bot_id}`}>{r.bot}</Link><div className="muted xs">{r.broker === 'oanda' ? 'OANDA' : 'Paper'}{r.status !== 'running' && ` · ${r.status}`}</div></td>
                  <td className="sym">{r.symbol}</td>
                  <td className={r.side === 'long' ? 'up' : 'down'}>{r.side === 'long' ? 'LONG' : 'SHORT'}</td>
                  <td className="r mono">{num(r.quantity)}</td>
                  <td className="r mono">{r.entry_price}</td>
                  <td className="r mono">{r.price ?? '—'}</td>
                  {!compact && <td className="r mono">{r.stop_loss ?? '—'}</td>}
                  {!compact && <td className="r mono">{r.take_profit ?? '—'}</td>}
                  <td className={`r mono ${signClass(r.unrealized_pnl)}`}>{r.unrealized_pnl === null ? '—' : usd(r.unrealized_pnl, { signDisplay: 'exceptZero' })}</td>
                  <td className="r"><button className="btn ghost sm" onClick={() => close(r.bot_id)}>{closing === r.bot_id ? 'Confirm close' : 'Close'}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
