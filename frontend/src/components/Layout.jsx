import { NavLink } from 'react-router-dom'
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
          <button className="btn ghost sm" onClick={logout}>Log out</button>
        </div>
      </header>
      <main className="content">{children}</main>
    </div>
  )
}
