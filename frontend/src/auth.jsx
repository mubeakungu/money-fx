import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, getToken, setToken } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(!!getToken())

  const refresh = useCallback(async () => {
    if (!getToken()) return setUser(null)
    try {
      setUser(await api('/auth/me'))
    } catch {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const onLogout = () => setUser(null)
    window.addEventListener('moneyfx:logout', onLogout)
    return () => window.removeEventListener('moneyfx:logout', onLogout)
  }, [refresh])

  const login = async (email, password) => {
    const { access_token } = await api('/auth/login', { method: 'POST', body: { email, password } })
    setToken(access_token)
    await refresh()
  }

  const register = async (form) => {
    const { access_token } = await api('/auth/register', { method: 'POST', body: form })
    setToken(access_token)
    await refresh()
  }

  const logout = () => {
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
