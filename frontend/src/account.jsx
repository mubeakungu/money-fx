import { createContext, useContext, useEffect, useState } from 'react'
import { DEMO, api } from './api'

// Which account the app is showing: "demo" (simulated money fx account) or "real" (your OANDA account).
const AccountModeContext = createContext({ mode: 'demo', setMode: () => {}, real: null, oanda: null })
const KEY = 'moneyfx_mode'

export function AccountModeProvider({ children }) {
  const [oanda, setOanda] = useState(null) // OANDA status from the server, also when it is not set up
  const [mode, setModeState] = useState(() => {
    try { return localStorage.getItem(KEY) || 'demo' } catch { return 'demo' }
  })

  useEffect(() => {
    if (DEMO) return
    api('/bots/brokers').then((b) => setOanda(b.oanda)).catch(() => setOanda(null))
  }, [])

  const setMode = (m) => {
    setModeState(m)
    try { localStorage.setItem(KEY, m) } catch { /* storage blocked */ }
  }
  const real = oanda?.configured ? oanda : null // OANDA connection info when the real account is available
  const effective = real ? mode : 'demo'
  return <AccountModeContext.Provider value={{ mode: effective, setMode, real, oanda }}>{children}</AccountModeContext.Provider>
}

export const useAccountMode = () => useContext(AccountModeContext)
