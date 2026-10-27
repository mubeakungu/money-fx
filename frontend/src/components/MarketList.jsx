import { useState } from 'react'
import { ASSET_LABELS, pct, signClass } from '../format'
import { useQuotes } from '../quotes'

const CLASSES = ['all', 'forex', 'crypto', 'stock', 'commodity']

export default function MarketList({ selected, onSelect }) {
  const { instruments, quotes } = useQuotes()
  const [filter, setFilter] = useState('all')
  const classes = CLASSES.filter((c) => c === 'all' || instruments.some((i) => i.asset_class === c))
  const rows = instruments.filter((i) => filter === 'all' || i.asset_class === filter)
  const hasChange = Object.values(quotes).some((q) => q.change_24h_pct !== undefined)
  return (
    <div className="panel market-list">
      <div className="tabs">
        {classes.map((c) => (
          <button key={c} className={filter === c ? 'active' : ''} onClick={() => setFilter(c)}>
            {c === 'all' ? 'All' : ASSET_LABELS[c]}
          </button>
        ))}
      </div>
      <table>
        <thead>
          <tr><th>Market</th><th className="r">Bid</th><th className="r">Ask</th>{hasChange && <th className="r">24h</th>}</tr>
        </thead>
        <tbody>
          {rows.map((i) => {
            const q = quotes[i.symbol]
            return (
              <tr key={i.symbol} className={selected === i.symbol ? 'selected' : ''} onClick={() => onSelect(i.symbol)}>
                <td><div className="sym">{i.symbol}</div><div className="muted xs">{i.name}</div></td>
                <td className="r mono">{q?.bid ?? '—'}</td>
                <td className="r mono">{q?.ask ?? '—'}</td>
                {hasChange && <td className={`r mono ${signClass(q?.change_24h_pct)}`}>{q?.change_24h_pct !== undefined ? pct(q.change_24h_pct) : '—'}</td>}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
