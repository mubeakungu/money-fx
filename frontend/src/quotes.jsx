import { createContext, useContext, useEffect, useState } from 'react'
import { DEMO, api } from './api'

const QuotesContext = createContext({ quotes: {}, instruments: [], connected: false })

// One WebSocket for the whole app; every component reads the latest quote by symbol.
export function QuotesProvider({ children }) {
  const [quotes, setQuotes] = useState({})
  const [instruments, setInstruments] = useState([])
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    api('/markets/instruments').then(setInstruments).catch(() => {})
  }, [])

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
    if (DEMO) return
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
  }, [])

  return <QuotesContext.Provider value={{ quotes, instruments, connected }}>{children}</QuotesContext.Provider>
}

export const useQuotes = () => useContext(QuotesContext)
