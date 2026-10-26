import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth'
import Layout from './components/Layout'
import { QuotesProvider } from './quotes'
import Account from './pages/Account'
import { Login, Register } from './pages/Auth'
import Orders from './pages/Orders'
import Portfolio from './pages/Portfolio'
import Trade from './pages/Trade'
import Wallet from './pages/Wallet'

function Protected({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="center muted">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  return <QuotesProvider><Layout>{children}</Layout></QuotesProvider>
}

export default function App() {
  const { user } = useAuth()
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" /> : <Login />} />
      <Route path="/register" element={user ? <Navigate to="/wallet" /> : <Register />} />
      <Route path="/" element={<Protected><Trade /></Protected>} />
      <Route path="/trade/:symbol" element={<Protected><Trade /></Protected>} />
      <Route path="/portfolio" element={<Protected><Portfolio /></Protected>} />
      <Route path="/wallet" element={<Protected><Wallet /></Protected>} />
      <Route path="/orders" element={<Protected><Orders /></Protected>} />
      <Route path="/account" element={<Protected><Account /></Protected>} />
      <Route path="*" element={<Navigate to="/" />} />
    </Routes>
  )
}
