import { createContext, useContext, useEffect, useState } from 'react'
import { useAccountMode } from './account'
import { DEMO, api } from './api'

const QuotesContext = createContext({ quotes: {}, instruments: [], connected: false })

// One WebSocket for the whole app; every component reads the latest quote by symbol.
export function QuotesProvider({ children }) {
  const [quotes, setQuotes] = useState({})
  const [instruments, setInstruments] = useState([])
  const [connected, setConnected] = useState(false)
  const { mode } = useAccountMode()
  const real = mode === 'real'

  useEffect(() => {
    setInstruments([])
    setQuotes({})
    api(real ? '/real/instruments' : '/markets/instruments').then(setInstruments).catch(() => {})
  }, [real])

  // Real account: poll OANDA prices.
  useEffect(() => {
    if (!real) return
    let stop = false
    const poll = async () => {
      try {
        const rows = await api('/real/prices')
        if (!stop) {
          setQuotes(Object.fromEntries(rows.map((q) => [q.symbol, q])))
          setConnected(true)
        }
      } catch {
        if (!stop) setConnected(false)
      }
    }
    poll()
    const t = setInterval(poll, 2000)
    return () => { stop = true; clearInterval(t) }
  }, [real])

  useEffect(() => {
    if (!DEMO) return
    let timer
    import('./demo/feed').then(({ INSTRUMENTS, quoteJson }) => {
      const push = () => setQuotes(Object.fromEntries(INSTRUMENTS.map((i) => [i.symbol, quoteJson(i.symbol)])))
      push()
      setConnected(true)
      timer = setInterval(push, 1000)
    })
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    if (DEMO || real) return
    let ws
    let retry
    let closed = false
    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/api/markets/ws`)
      ws.onopen = () => setConnected(true)
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data)
        if (msg.type === 'quotes') setQuotes(Object.fromEntries(msg.data.map((q) => [q.symbol, q])))
      }
      ws.onclose = () => {
        setConnected(false)
        if (!closed) retry = setTimeout(connect, 2000)
      }
    }
    connect()
    return () => {
      closed = true
      clearTimeout(retry)
      ws?.close()
    }
  }, [real])

  return <QuotesContext.Provider value={{ quotes, instruments, connected }}>{children}</QuotesContext.Provider>
}

export const useQuotes = () => useContext(QuotesContext)
