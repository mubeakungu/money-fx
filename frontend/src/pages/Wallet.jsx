import { useAccountMode } from '../account'
import { RealWallet } from '../real/RealPages'
import { useEffect, useState } from 'react'
import { api } from '../api'
import { dateTime, signClass, usd } from '../format'

const METHODS = { card: 'Card', bank_transfer: 'Bank transfer', mobile_money: 'Mobile money', crypto: 'Crypto' }
const TYPES = { deposit: 'Deposit', withdrawal: 'Withdrawal', trade_buy: 'Buy', trade_sell: 'Sell' }

export default function Wallet() {
  return useAccountMode().mode === 'real' ? <RealWallet /> : <DemoWallet />
}

function DemoWallet() {
  const [wallet, setWallet] = useState(null)
  const [txns, setTxns] = useState([])
  const [mode, setMode] = useState('deposit')
  const [amount, setAmount] = useState('')
  const [method, setMethod] = useState('card')
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = () => {
    api('/wallet').then(setWallet)
    api('/wallet/transactions?limit=100').then(setTxns)
  }
  useEffect(load, [])

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setMsg(null)
    try {
      const t = await api(`/wallet/${mode === 'deposit' ? 'deposit' : 'withdraw'}`, { method: 'POST', body: { amount, method } })
      setMsg({ ok: true, text: `${mode === 'deposit' ? 'Deposited' : 'Withdrew'} ${usd(Math.abs(t.amount))} (ref ${t.reference})` })
      setAmount('')
      load()
    } catch (err) {
      setMsg({ ok: false, text: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <div className="page-head"><h2>Wallet</h2></div>
      <div className="wallet-grid">
        <div className="panel">
          <div className="muted xs">USD balance</div>
          <div className="card-value mono xl">{wallet ? usd(wallet.balance) : '—'}</div>
          {wallet && (
            <dl className="kv">
              <dt>Available</dt><dd className="mono">{usd(wallet.available)}</dd>
              <dt>Reserved for open orders</dt><dd className="mono">{usd(wallet.locked)}</dd>
            </dl>
          )}
        </div>
        <form className="panel" onSubmit={submit}>
          <div className="seg full">
            <button type="button" className={mode === 'deposit' ? 'active buy' : ''} onClick={() => setMode('deposit')}>Deposit</button>
            <button type="button" className={mode === 'withdraw' ? 'active sell' : ''} onClick={() => setMode('withdraw')}>Withdraw</button>
          </div>
          <label>Amount (USD)
            <input className="mono" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" required />
          </label>
          {mode === 'deposit' && (
            <div className="quick">
              {[100, 1000, 10000].map((v) => <button type="button" key={v} className="btn ghost sm" onClick={() => setAmount(String(v))}>{usd(v, { maximumFractionDigits: 0 })}</button>)}
            </div>
          )}
          <label>Method
            <select value={method} onChange={(e) => setMethod(e.target.value)}>
              {Object.entries(METHODS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <button className={`btn block ${mode === 'deposit' ? 'buy' : 'sell'}`} disabled={busy}>
            {busy ? 'Processing…' : mode === 'deposit' ? 'Deposit funds' : 'Withdraw funds'}
          </button>
          <p className="muted xs">Demo mode: payments are simulated and settle instantly.</p>
          {msg && <div className={`notice ${msg.ok ? 'ok' : 'err'}`}>{msg.text}</div>}
        </form>
      </div>
      <div className="panel">
        <h3>Transactions</h3>
        {txns.length === 0 ? <p className="muted">No transactions yet.</p> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Time</th><th>Type</th><th>Details</th><th className="r">Amount</th><th className="r">Balance</th></tr></thead>
              <tbody>
                {txns.map((t) => (
                  <tr key={t.id}>
                    <td className="muted">{dateTime(t.created_at)}</td>
                    <td>{TYPES[t.type]}</td>
                    <td className="muted">{t.method ? `${METHODS[t.method]} · ` : ''}{t.reference}</td>
                    <td className={`r mono ${signClass(t.amount)}`}>{usd(t.amount, { signDisplay: 'exceptZero' })}</td>
                    <td className="r mono">{usd(t.balance_after)}</td>
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
