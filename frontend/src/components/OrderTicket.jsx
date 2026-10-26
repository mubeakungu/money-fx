import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { num, usd } from '../format'
import { useQuotes } from '../quotes'

export default function OrderTicket({ instrument, onPlaced, refreshKey }) {
  const { quotes } = useQuotes()
  const [side, setSide] = useState('buy')
  const [type, setType] = useState('market')
  const [quantity, setQuantity] = useState('')
  const [limitPrice, setLimitPrice] = useState('')
  const [wallet, setWallet] = useState(null)
  const [holding, setHolding] = useState('0')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const symbol = instrument?.symbol
  const q = quotes[symbol]

  useEffect(() => {
    api('/wallet').then(setWallet).catch(() => {})
    api('/portfolio').then((p) => setHolding(p.positions.find((x) => x.symbol === symbol)?.quantity ?? '0')).catch(() => {})
  }, [symbol, refreshKey])

  useEffect(() => {
    setQuantity('')
    setLimitPrice('')
    setResult(null)
  }, [symbol])

  if (!instrument) return <div className="panel ticket" />

  const price = type === 'limit' && limitPrice ? Number(limitPrice) : Number(side === 'buy' ? q?.ask : q?.bid)
  const estimate = quantity && price ? Number(quantity) * price : 0
  const step = 10 ** -instrument.qty_decimals
  const maxQty = side === 'buy'
    ? wallet && price ? Math.floor((Number(wallet.available) / price) / step) * step : 0
    : Number(holding)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setResult(null)
    try {
      const body = { symbol, side, type, quantity }
      if (type === 'limit') body.limit_price = limitPrice
      const o = await api('/orders', { method: 'POST', body })
      if (o.status === 'filled') setResult({ ok: true, msg: `${side === 'buy' ? 'Bought' : 'Sold'} ${num(o.quantity)} ${symbol} at ${o.filled_price}` })
      else if (o.status === 'open') setResult({ ok: true, msg: `Limit order placed: ${side} ${num(o.quantity)} ${symbol} at ${o.limit_price}` })
      else setResult({ ok: false, msg: o.reject_reason })
      if (o.status !== 'rejected') setQuantity('')
      onPlaced?.()
    } catch (err) {
      setResult({ ok: false, msg: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="panel ticket" onSubmit={submit}>
      <div className="seg full">
        <button type="button" className={side === 'buy' ? 'active buy' : ''} onClick={() => setSide('buy')}>
          Buy<span className="mono xs">{q?.ask}</span>
        </button>
        <button type="button" className={side === 'sell' ? 'active sell' : ''} onClick={() => setSide('sell')}>
          Sell<span className="mono xs">{q?.bid}</span>
        </button>
      </div>
      <div className="seg full sm">
        {['market', 'limit'].map((t) => (
          <button type="button" key={t} className={type === t ? 'active' : ''} onClick={() => setType(t)}>
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>
      {type === 'limit' && (
        <label>Limit price (USD)
          <input className="mono" inputMode="decimal" value={limitPrice} placeholder={q?.mid}
            onChange={(e) => setLimitPrice(e.target.value)} required />
        </label>
      )}
      <label>
        <span className="row-between">Quantity
          <button type="button" className="link xs" onClick={() => setQuantity(maxQty > 0 ? maxQty.toFixed(instrument.qty_decimals) : '')}>
            Max {num(maxQty, instrument.qty_decimals)}
          </button>
        </span>
        <input className="mono" inputMode="decimal" value={quantity} placeholder={`min ${instrument.min_qty}`}
          onChange={(e) => setQuantity(e.target.value)} required />
      </label>
      <dl className="kv">
        <dt>{side === 'buy' ? 'Est. cost' : 'Est. proceeds'}</dt><dd className="mono">{usd(estimate)}</dd>
        <dt>Cash available</dt><dd className="mono">{wallet ? usd(wallet.available) : '—'}</dd>
        <dt>You hold</dt><dd className="mono">{num(holding)} {symbol}</dd>
      </dl>
      <button className={`btn block ${side}`} disabled={busy || !q}>
        {busy ? 'Placing…' : `${side === 'buy' ? 'Buy' : 'Sell'} ${symbol}`}
      </button>
      {result && <div className={`notice ${result.ok ? 'ok' : 'err'}`}>{result.msg}</div>}
      {wallet && Number(wallet.balance) === 0 && (
        <div className="notice">Your wallet is empty. <Link to="/wallet">Deposit funds</Link> to start trading.</div>
      )}
    </form>
  )
}
