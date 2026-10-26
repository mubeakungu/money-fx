import { useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import { dateTime } from '../format'

export default function Account() {
  const { user, refresh } = useAuth()
  const [profile, setProfile] = useState({ full_name: user.full_name, country: user.country || '' })
  const [pw, setPw] = useState({ current_password: '', new_password: '' })
  const [msg, setMsg] = useState({})

  const saveProfile = async (e) => {
    e.preventDefault()
    try {
      await api('/auth/me', { method: 'PATCH', body: { full_name: profile.full_name, country: profile.country || null } })
      await refresh()
      setMsg({ profile: { ok: true, text: 'Profile saved' } })
    } catch (err) {
      setMsg({ profile: { ok: false, text: err.message } })
    }
  }

  const changePassword = async (e) => {
    e.preventDefault()
    try {
      await api('/auth/change-password', { method: 'POST', body: pw })
      setPw({ current_password: '', new_password: '' })
      setMsg({ pw: { ok: true, text: 'Password changed' } })
    } catch (err) {
      setMsg({ pw: { ok: false, text: err.message } })
    }
  }

  return (
    <div className="page narrow">
      <div className="page-head"><h2>Account</h2></div>
      <div className="panel">
        <h3>Account details</h3>
        <dl className="kv">
          <dt>Email</dt><dd>{user.email}</dd>
          <dt>Account number</dt><dd className="mono">MFX-{String(user.account_id).padStart(6, '0')}</dd>
          <dt>Status</dt><dd><span className="pill filled">{user.account_status}</span></dd>
          <dt>Base currency</dt><dd>USD</dd>
          <dt>Member since</dt><dd>{dateTime(user.created_at)}</dd>
        </dl>
      </div>
      <form className="panel" onSubmit={saveProfile}>
        <h3>Profile</h3>
        <label>Full name<input value={profile.full_name} onChange={(e) => setProfile({ ...profile, full_name: e.target.value })} required /></label>
        <label>Country (2-letter code)<input value={profile.country} maxLength={2} placeholder="KE" onChange={(e) => setProfile({ ...profile, country: e.target.value })} /></label>
        <button className="btn">Save profile</button>
        {msg.profile && <div className={`notice ${msg.profile.ok ? 'ok' : 'err'}`}>{msg.profile.text}</div>}
      </form>
      <form className="panel" onSubmit={changePassword}>
        <h3>Change password</h3>
        <label>Current password<input type="password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} required /></label>
        <label>New password<input type="password" minLength={8} value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} required /></label>
        <button className="btn">Change password</button>
        {msg.pw && <div className={`notice ${msg.pw.ok ? 'ok' : 'err'}`}>{msg.pw.text}</div>}
      </form>
    </div>
  )
}
