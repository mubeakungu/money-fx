import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth'

function AuthCard({ title, children, footer }) {
  return (
    <div className="auth-page">
      <div className="panel auth-card">
        <div className="brand lg"><span className="logo">fx</span> money fx</div>
        <p className="muted">Forex, crypto, stocks and commodities in one account.</p>
        <h2>{title}</h2>
        {children}
        <p className="muted xs center">{footer}</p>
      </div>
    </div>
  )
}

export function Login() {
  const { login } = useAuth()
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try { await login(form.email, form.password) } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  return (
    <AuthCard title="Log in" footer={<>New here? <Link to="/register">Create an account</Link></>}>
      <form onSubmit={submit}>
        <label>Email<input type="email" autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required /></label>
        <label>Password<input type="password" autoComplete="current-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required /></label>
        <button className="btn block" disabled={busy}>{busy ? 'Logging in…' : 'Log in'}</button>
        {error && <div className="notice err">{error}</div>}
      </form>
    </AuthCard>
  )
}

export function Register() {
  const { register } = useAuth()
  const [form, setForm] = useState({ full_name: '', email: '', password: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try { await register(form) } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  return (
    <AuthCard title="Create your account" footer={<>Already have an account? <Link to="/login">Log in</Link></>}>
      <form onSubmit={submit}>
        <label>Full name<input autoComplete="name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required /></label>
        <label>Email<input type="email" autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required /></label>
        <label>Password<input type="password" autoComplete="new-password" minLength={8} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required /></label>
        <button className="btn block" disabled={busy}>{busy ? 'Creating…' : 'Sign up'}</button>
        {error && <div className="notice err">{error}</div>}
      </form>
    </AuthCard>
  )
}
