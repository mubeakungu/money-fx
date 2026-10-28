import { CandlestickSeries, LineSeries, createChart } from 'lightweight-charts'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useAccountMode } from '../account'
import { lineData, rsi, sma } from '../indicators'
import { useQuotes } from '../quotes'
import { CANDLES, COLORS, addRsiPane, chartOptions, lineOptions } from './chartTheme'

const INTERVALS = { '1m': 60, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400 }
const STUDIES = {
  ma20: { label: 'MA 20', calc: (bars) => sma(bars.map((b) => b.close), 20), color: COLORS.fast },
  ma50: { label: 'MA 50', calc: (bars) => sma(bars.map((b) => b.close), 50), color: COLORS.slow },
  rsi: { label: 'RSI', calc: (bars) => rsi(bars.map((b) => b.close), 14) },
}
const STUDY_KEY = 'moneyfx_studies'

function savedStudies() {
  try { return JSON.parse(localStorage.getItem(STUDY_KEY)) ?? [] } catch { return [] }
}

export default function PriceChart({ instrument }) {
  const el = useRef(null)
  const series = useRef(null)
  const last = useRef(null)
  const bars = useRef([])
  const studySeries = useRef({})
  const [interval, setInterval_] = useState('1m')
  const [studies, setStudies] = useState(savedStudies)
  const { quotes } = useQuotes()
  const symbol = instrument?.symbol
  const real = useAccountMode().mode === 'real'

  useEffect(() => {
    if (!el.current || !instrument) return
    const chart = createChart(el.current, chartOptions())
    series.current = chart.addSeries(CandlestickSeries, {
      ...CANDLES, priceFormat: { type: 'price', precision: instrument.price_decimals, minMove: 10 ** -instrument.price_decimals },
    })
    studySeries.current = Object.fromEntries(studies.map((k) => [k, k === 'rsi'
      ? addRsiPane(chart, LineSeries)
      : chart.addSeries(LineSeries, lineOptions(STUDIES[k].color))]))
    let cancelled = false
    api(`${real ? '/real' : '/markets'}/candles/${symbol}?interval=${interval}&limit=300`).then((data) => {
      if (cancelled) return
      series.current.setData(data)
      bars.current = data.map((b) => ({ ...b }))
      for (const [k, s] of Object.entries(studySeries.current)) s.setData(lineData(data, STUDIES[k].calc(data)))
      last.current = { ...data[data.length - 1] }
      chart.timeScale().fitContent()
    })
    return () => {
      cancelled = true
      last.current = null
      series.current = null
      studySeries.current = {}
      chart.remove()
    }
  }, [symbol, interval, instrument, real, studies])

  const toggle = (k) => {
    const next = studies.includes(k) ? studies.filter((x) => x !== k) : [...studies, k]
    setStudies(next)
    try { localStorage.setItem(STUDY_KEY, JSON.stringify(next)) } catch { /* storage blocked */ }
  }

  // Fold each live tick into the current candle, or open a new one.
  const q = quotes[symbol]
  useEffect(() => {
    if (!q?.ts || !series.current || !last.current) return
    const price = Number(q.mid)
    const step = INTERVALS[interval]
    const t = Math.floor(q.ts / 1000 / step) * step
    const bar = last.current
    if (t > bar.time) {
      last.current = { time: t, open: bar.close, high: Math.max(bar.close, price), low: Math.min(bar.close, price), close: price }
    } else {
      bar.high = Math.max(bar.high, price)
      bar.low = Math.min(bar.low, price)
      bar.close = price
    }
    series.current.update({ ...last.current })
    // Keep the indicators in step with the forming candle
    const b = bars.current
    if (!b.length) return
    if (b[b.length - 1].time === last.current.time) b[b.length - 1] = { ...last.current }
    else b.push({ ...last.current })
    for (const [k, s] of Object.entries(studySeries.current)) {
      const v = STUDIES[k].calc(b).at(-1)
      if (v != null) s.update({ time: last.current.time, value: v })
    }
  }, [q, interval])

  return (
    <div className="panel chart-panel">
      <div className="chart-head">
        <div>
          <span className="sym lg">{symbol}</span> <span className="muted">{instrument?.name}</span>
          {q && <span className="mono price-big">{q.mid}</span>}
        </div>
        <div className="seg studies" role="group" aria-label="Indicators">
          {Object.entries(STUDIES).map(([k, st]) => (
            <button key={k} className={studies.includes(k) ? 'active' : ''} onClick={() => toggle(k)}>
              {st.color && <span className="dot" style={{ background: st.color }} />}{st.label}
            </button>
          ))}
        </div>
        <div className="seg">
          {Object.keys(INTERVALS).map((k) => (
            <button key={k} className={k === interval ? 'active' : ''} onClick={() => setInterval_(k)}>{k}</button>
          ))}
        </div>
      </div>
      <div className="chart" ref={el} />
    </div>
  )
}
