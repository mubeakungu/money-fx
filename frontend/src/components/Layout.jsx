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
  const { mode, setMode, real } = useAccountMode()
  const live = real?.environment === 'live'
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
          {real && (
            <div className="seg mode" role="group" aria-label="Account">
              <button className={mode === 'demo' ? 'active' : ''} onClick={() => setMode('demo')}>Demo</button>
              <button className={mode === 'real' ? `active real ${live ? 'live' : ''}` : ''} onClick={() => setMode('real')}>
                Real<span className="hide-sm">{live ? ' · live' : ' · practice'}</span>
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
