import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { DEMO } from '../api'
import { useAccountMode } from '../account'
import { useAuth } from '../auth'
import { useQuotes } from '../quotes'

const NAV = [
  ['/', 'Trade'],
  ['/bots', 'Bots'],
  ['/portfolio', 'Portfolio'],
  ['/wallet', 'Wallet'],
  ['/orders', 'Orders'],
  ['/account', 'Account'],
]

async function resetDemo() {
  const { resetDemo: reset } = await import('../demo/server')
  reset()
  window.location.reload()
}

export default function Layout({ children }) {
  const { user, logout } = useAuth()
  const { connected } = useQuotes()
  const { mode, setMode, real, oanda } = useAccountMode()
  const [whyNoReal, setWhyNoReal] = useState(false)
  const live = real?.environment === 'live'
  const pickReal = () => (real ? setMode('real') : setWhyNoReal((v) => !v))
  return (
    <div className={`shell ${mode === 'real' ? 'is-real' : ''} ${mode === 'real' && live ? 'is-live' : ''}`}>
      <header className="topbar">
        <div className="brand"><span className="logo">fx</span> money fx</div>
        <nav>
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => (isActive ? 'active' : '')}>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="topbar-right">
          {!DEMO && oanda && (
            <div className="seg mode" role="group" aria-label="Account">
              <button className={mode === 'demo' ? 'active' : ''} onClick={() => { setMode('demo'); setWhyNoReal(false) }}>Demo</button>
              <button className={mode === 'real' ? `active real ${live ? 'live' : ''}` : real ? '' : 'off'} onClick={pickReal}
                title={real ? undefined : 'Real account not connected'}>
                Real<span className="hide-sm">{real ? (live ? ' · live' : ' · practice') : ' · not connected'}</span>
              </button>
            </div>
          )}
          <span className={`live ${connected ? 'on' : ''}`} title={connected ? 'Live prices connected' : 'Reconnecting…'}>
            ● <span className="hide-sm">{connected ? 'Live' : 'Offline'}</span>
          </span>
          <span className="muted hide-sm">{user.full_name}</span>
          {DEMO
            ? <button className="btn ghost sm" onClick={resetDemo}>Reset demo</button>
            : <button className="btn ghost sm" onClick={logout}>Log out</button>}
        </div>
      </header>
      {DEMO && (
        <div className="demo-bar">
          Demo with simulated prices and $10,000 of fake money. Your trades and bots stay in this browser.{' '}
          <a href="https://github.com/mubeakungu/money-fx" target="_blank" rel="noreferrer">Get the full app with OANDA trading</a>
        </div>
      )}
      {mode === 'demo' && whyNoReal && !real && oanda && (
        <div className="real-bar">
          {oanda.allowed
            ? 'Real account is not connected yet. In Render, open Environment and set OANDA_API_TOKEN and OANDA_ACCOUNT_ID, then redeploy.'
            : `Real account is off for ${user.email}. In Render, open Environment, add this exact email to OANDA_OWNER_EMAILS and set OANDA_API_TOKEN and OANDA_ACCOUNT_ID, then redeploy and log in again.`}
          {' '}<button className="link" onClick={() => setWhyNoReal(false)}>Dismiss</button>
        </div>
      )}
      {mode === 'real' && (
        <div className={`real-bar ${live ? 'live' : ''}`}>
          {live
            ? 'Real account: orders here trade real money on your OANDA live account.'
            : 'Real account: orders go to your OANDA practice account (OANDA\'s virtual money, real prices).'}
        </div>
      )}
      <main className="content">{children}</main>
    </div>
  )
}
