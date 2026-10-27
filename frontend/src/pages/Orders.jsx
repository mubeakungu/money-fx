import { useEffect, useState } from 'react'
import { api } from '../api'
import { dateTime, num } from '../format'

export function OrdersTable({ orders, onChange, compact }) {
  const [err, setErr] = useState(null)
  const cancel = async (id) => {
    setErr(null)
    await api(`/orders/${id}`, { method: 'DELETE' }).catch((e) => setErr(e.message))
    onChange?.()
  }
  if (!orders.length) return <p className="muted">No orders yet.</p>
  return (
    <div className="table-wrap">
      {err && <div className="notice err">{err}</div>}
      <table>
        <thead>
          <tr>
            {!compact && <th>Time</th>}
            <th>Market</th><th>Side</th><th>Type</th><th className="r">Qty</th>
            <th className="r">Price</th><th>Status</th><th />
          </tr>
        </thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.id}>
              {!compact && <td className="muted">{dateTime(o.created_at)}</td>}
              <td className="sym">{o.symbol}</td>
              <td className={o.side === 'buy' ? 'up' : 'down'}>{o.side.toUpperCase()}</td>
              <td>{o.type}</td>
              <td className="r mono">{num(o.quantity)}</td>
              <td className="r mono">{o.filled_price ?? o.limit_price ?? '—'}</td>
              <td><span className={`pill ${o.status}`} title={o.reject_reason || ''}>{o.status}</span></td>
              <td className="r">{o.status === 'open' && <button className="btn ghost sm" onClick={() => cancel(o.id)}>Cancel</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Orders() {
  const [orders, setOrders] = useState([])
  const [status, setStatus] = useState('')
  const load = () => api(`/orders?limit=200${status ? `&status=${status}` : ''}`).then(setOrders)

  useEffect(() => {
    load()
    const id = setInterval(load, 3000) // resting limit orders can fill in the background
    return () => clearInterval(id)
  }, [status])

  return (
    <div className="page">
      <div className="page-head">
        <h2>Orders</h2>
        <div className="seg">
          {['', 'open', 'filled', 'cancelled', 'rejected'].map((s) => (
            <button key={s} className={status === s ? 'active' : ''} onClick={() => setStatus(s)}>{s || 'All'}</button>
          ))}
        </div>
      </div>
      <div className="panel"><OrdersTable orders={orders} onChange={load} /></div>
    </div>
  )
}
