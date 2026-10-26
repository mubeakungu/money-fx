import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { ASSET_LABELS, num, pct, signClass, usd } from '../format'

const COLORS = { cash: '#8a94a6', forex: '#4c8dff', crypto: '#f7931a', stock: '#16c784', commodity: '#e5b53b' }

export default function Portfolio() {
  const [p, setP] = useState(null)

  useEffect(() => {
    const load = () => api('/portfolio').then(setP).catch(() => {})
    load()
    const id = setInterval(load, 2000)
    return () => clearInterval(id)
  }, [])

  if (!p) return <div className="center muted">Loading portfolio…</div>

  const equity = Number(p.equity)
  const totalReturn = equity - Number(p.net_deposits)
  const totalReturnPct = Number(p.net_deposits) ? (totalReturn / Number(p.net_deposits)) * 100 : 0
  const alloc = Object.entries(p.allocation).filter(([, v]) => Number(v) > 0)

  return (
    <div className="page">
      <div className="page-head"><h2>Portfolio</h2></div>
      <div className="cards">
        <Card label="Total equity" value={usd(p.equity)} />
        <Card label="Cash" value={usd(p.cash)} sub={Number(p.cash_locked) ? `${usd(p.cash_locked)} reserved for orders` : null} />
        <Card label="Holdings value" value={usd(p.positions_value)} />
        <Card label="Unrealized P&L" value={usd(p.unrealized_pnl, { signDisplay: 'exceptZero' })} cls={signClass(p.unrealized_pnl)} />
        <Card label="Realized P&L" value={usd(p.realized_pnl, { signDisplay: 'exceptZero' })} cls={signClass(p.realized_pnl)} />
        <Card label="Total return" value={usd(totalReturn, { signDisplay: 'exceptZero' })} cls={signClass(totalReturn)}
          sub={`${pct(totalReturnPct)} on ${usd(p.net_deposits)} deposited`} />
      </div>

      {equity > 0 && (
        <div className="panel">
          <h3>Allocation</h3>
          <div className="alloc-bar">
            {alloc.map(([k, v]) => (
              <div key={k} style={{ width: `${(Number(v) / equity) * 100}%`, background: COLORS[k] }} title={`${ASSET_LABELS[k]} ${usd(v)}`} />
            ))}
          </div>
          <div className="legend">
            {alloc.map(([k, v]) => (
              <span key={k}><i style={{ background: COLORS[k] }} />{ASSET_LABELS[k]} {((Number(v) / equity) * 100).toFixed(1)}%</span>
            ))}
          </div>
        </div>
      )}

      <div className="panel">
        <h3>Holdings</h3>
        {p.positions.length === 0 ? (
          <p className="muted">You don't hold anything yet. <Link to="/">Place your first trade</Link>.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Market</th><th className="r">Quantity</th><th className="r">Avg price</th><th className="r">Price</th>
                  <th className="r">Value</th><th className="r">Unrealized P&L</th></tr>
              </thead>
              <tbody>
                {p.positions.map((x) => (
                  <tr key={x.symbol}>
                    <td><Link to={`/trade/${x.symbol}`} className="sym">{x.symbol}</Link><div className="muted xs">{ASSET_LABELS[x.asset_class]}</div></td>
                    <td className="r mono">{num(x.quantity)}</td>
                    <td className="r mono">{num(x.avg_price, undefined)}</td>
                    <td className="r mono">{x.price}</td>
                    <td className="r mono">{usd(x.market_value)}</td>
                    <td className={`r mono ${signClass(x.unrealized_pnl)}`}>
                      {usd(x.unrealized_pnl, { signDisplay: 'exceptZero' })} <span className="xs">({pct(x.unrealized_pnl_pct)})</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
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
