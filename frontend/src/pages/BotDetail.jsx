import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { dateTime, num, signClass, usd } from '../format'
import { BotCard, REASONS } from './Bots'

export default function BotDetail() {
  const { id } = useParams()
  const [d, setD] = useState(null)
  const [strategies, setStrategies] = useState([])
  const [error, setError] = useState(null)
  const load = () => api(`/bots/${id}`).then(setD).catch((e) => setError(e.message))

  useEffect(() => {
    api('/bots/strategies').then(setStrategies)
    load()
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [id])

  if (error) return <div className="center muted">{error}</div>
  if (!d) return <div className="center muted">Loading…</div>
  return (
    <div className="page">
      <div className="page-head">
        <h2><Link to="/bots" className="muted">Bots</Link> / {d.bot.name}</h2>
        {d.unrealized_pnl !== null && (
          <span className="muted">Open P&L <span className={`mono ${signClass(d.unrealized_pnl)}`}>{usd(d.unrealized_pnl, { signDisplay: 'exceptZero' })}</span></span>
        )}
      </div>
      <div className="detail-grid">
        <BotCard bot={d.bot} strategies={strategies} onChange={load} />
        <div className="panel">
          <h3>Trades</h3>
          {d.trades.length === 0 ? <p className="muted">No trades yet. The bot acts when a candle closes with a signal.</p> : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Time</th><th>Action</th><th>Why</th><th className="r">Qty</th><th className="r">Price</th><th className="r">P&L</th></tr></thead>
                <tbody>
                  {d.trades.map((t) => (
                    <tr key={t.id}>
                      <td className="muted">{dateTime(t.created_at)}</td>
                      <td className={t.action === 'open' ? 'up' : 'down'}>{t.action === 'open' ? 'BUY' : 'SELL'}</td>
                      <td>{REASONS[t.reason] ?? t.reason}</td>
                      <td className="r mono">{num(t.quantity)}</td>
                      <td className="r mono">{t.price}</td>
                      <td className={`r mono ${signClass(t.pnl)}`}>{t.pnl === null ? '' : usd(t.pnl, { signDisplay: 'exceptZero' })}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
      <div className="panel">
        <h3>Activity</h3>
        <ul className="log">
          {d.logs.map((l) => (
            <li key={l.id} className={l.level}><span className="muted mono xs">{dateTime(l.created_at)}</span> {l.message}</li>
          ))}
        </ul>
      </div>
    </div>
  )
}
