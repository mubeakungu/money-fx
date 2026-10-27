import { NavLink } from 'react-router-dom'
import { DEMO } from '../api'
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
  return (
    <div className="shell">
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
      <main className="content">{children}</main>
    </div>
  )
}
