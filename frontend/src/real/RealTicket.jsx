import { useEffect, useState } from 'react'
import { api } from '../api'
import { useAccountMode } from '../account'
import { num, usd } from '../format'
import { useQuotes } from '../quotes'

// Order ticket for the OANDA account. Every order takes two clicks: review, then confirm.
export default function RealTicket({ instrument, onPlaced }) {
  const { real } = useAccountMode()
  const { quotes } = useQuotes()
  const [side, setSide] = useState('buy')
  const [type, setType] = useState('market')
  const [units, setUnits] = useState('')
  const [limitPrice, setLimitPrice] = useState('')
  const [sl, setSl] = useState('')
  const [tp, setTp] = useState('')
  const [review, setReview] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const symbol = instrument?.symbol
  const q = quotes[symbol]

  useEffect(() => { setUnits(''); setLimitPrice(''); setReview(false); setResult(null) }, [symbol])
  useEffect(() => setReview(false), [side, type, units, limitPrice, sl, tp])

  if (!instrument) return <div className="panel ticket" />
  const price = type === 'limit' && limitPrice ? Number(limitPrice) : Number(side === 'buy' ? q?.ask : q?.bid)
  const notional = units && price ? Number(units) * price : 0
  const live = real?.environment === 'live'

  const submit = async (e) => {
    e.preventDefault()
    if (!review) return setReview(true)
    setBusy(true)
    setResult(null)
    try {
      const body = { symbol, side, type, units, stop_loss_pct: sl ? Number(sl) : null, take_profit_pct: tp ? Number(tp) : null }
      if (type === 'limit') body.limit_price = limitPrice
      const r = await api('/real/orders', { method: 'POST', body })
      setResult({ ok: true, msg: r.status === 'filled'
        ? `${side === 'buy' ? 'Bought' : 'Sold'} ${num(r.units)} ${symbol} at ${r.price} on OANDA`
        : `Limit order placed on OANDA: ${side} ${num(r.units)} ${symbol} at ${r.price}` })
      setUnits('')
      onPlaced?.()
    } catch (err) {
      setResult({ ok: false, msg: err.message })
    } finally {
      setBusy(false)
      setReview(false)
    }
  }

  return (
    <form className="panel ticket real" onSubmit={submit}>
      <div className="seg full">
        <button type="button" className={side === 'buy' ? 'active buy' : ''} onClick={() => setSide('buy')}>Buy<span className="mono xs">{q?.ask}</span></button>
        <button type="button" className={side === 'sell' ? 'active sell' : ''} onClick={() => setSide('sell')}>Sell<span className="mono xs">{q?.bid}</span></button>
      </div>
      <div className="seg full sm">
        {['market', 'limit'].map((t) => (
          <button type="button" key={t} className={type === t ? 'active' : ''} onClick={() => setType(t)}>{t[0].toUpperCase() + t.slice(1)}</button>
        ))}
      </div>
      {type === 'limit' && (
        <label>Limit price<input className="mono" inputMode="decimal" value={limitPrice} placeholder={q?.mid} onChange={(e) => setLimitPrice(e.target.value)} required /></label>
      )}
      <label>Units<input className="mono" inputMode="decimal" value={units} placeholder={`min ${instrument.min_qty}`} onChange={(e) => setUnits(e.target.value)} required /></label>
      <div className="row2">
        <label>Stop-loss %<input className="mono" inputMode="decimal" value={sl} placeholder="none" onChange={(e) => setSl(e.target.value)} /></label>
        <label>Take-profit %<input className="mono" inputMode="decimal" value={tp} placeholder="none" onChange={(e) => setTp(e.target.value)} /></label>
      </div>
      <dl className="kv">
        <dt>Position value</dt><dd className="mono">{usd(notional)}</dd>
        <dt>Account</dt><dd>OANDA {live ? 'live' : 'practice'}</dd>
      </dl>
      {side === 'sell' && <p className="muted xs">Selling with no open buy opens a short position.</p>}
      {review ? (
        <div className="confirm">
          <p>{live ? 'Real money: ' : ''}{side === 'buy' ? 'Buy' : 'Sell'} {num(units)} {symbol} {type === 'limit' ? `at ${limitPrice}` : 'at market'} on OANDA {live ? 'live' : 'practice'}?</p>
          <div className="actions">
            <button className={`btn ${side}`} disabled={busy}>{busy ? 'Sending…' : 'Confirm order'}</button>
            <button type="button" className="btn ghost" onClick={() => setReview(false)}>Cancel</button>
          </div>
        </div>
      ) : (
        <button className={`btn block ${side}`} disabled={!q}>Review {side === 'buy' ? 'buy' : 'sell'}</button>
      )}
      {result && <div className={`notice ${result.ok ? 'ok' : 'err'}`}>{result.msg}</div>}
    </form>
  )
}
