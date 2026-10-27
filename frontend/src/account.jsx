import { createContext, useContext, useEffect, useState } from 'react'
import { DEMO, api } from './api'

// Which account the app is showing: "demo" (simulated money fx account) or "real" (your OANDA account).
const AccountModeContext = createContext({ mode: 'demo', setMode: () => {}, real: null })
const KEY = 'moneyfx_mode'

export function AccountModeProvider({ children }) {
  const [real, setReal] = useState(null) // OANDA connection info when the real account is available
  const [mode, setModeState] = useState(() => {
    try { return localStorage.getItem(KEY) || 'demo' } catch { return 'demo' }
  })

  useEffect(() => {
    if (DEMO) return
    api('/bots/brokers').then((b) => setReal(b.oanda.configured ? b.oanda : null)).catch(() => setReal(null))
  }, [])

  const setMode = (m) => {
    setModeState(m)
    try { localStorage.setItem(KEY, m) } catch { /* storage blocked */ }
  }
  const effective = real ? mode : 'demo'
  return <AccountModeContext.Provider value={{ mode: effective, setMode, real }}>{children}</AccountModeContext.Provider>
}

export const useAccountMode = () => useContext(AccountModeContext)
