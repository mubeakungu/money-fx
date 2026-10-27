import { CandlestickSeries, ColorType, createChart } from 'lightweight-charts'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useAccountMode } from '../account'
import { useQuotes } from '../quotes'

const INTERVALS = { '1m': 60, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400 }

export default function PriceChart({ instrument }) {
  const el = useRef(null)
  const series = useRef(null)
  const last = useRef(null)
  const [interval, setInterval_] = useState('1m')
  const { quotes } = useQuotes()
  const symbol = instrument?.symbol
  const real = useAccountMode().mode === 'real'

  useEffect(() => {
    if (!el.current || !instrument) return
    const css = getComputedStyle(document.documentElement)
    const chart = createChart(el.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: css.getPropertyValue('--muted').trim() },
      grid: { vertLines: { color: css.getPropertyValue('--grid').trim() }, horzLines: { color: css.getPropertyValue('--grid').trim() } },
      timeScale: { timeVisible: true, secondsVisible: false, borderVisible: false },
      rightPriceScale: { borderVisible: false },
      crosshair: { mode: 0 },
    })
    series.current = chart.addSeries(CandlestickSeries, {
      upColor: '#16c784', downColor: '#ea3943', wickUpColor: '#16c784', wickDownColor: '#ea3943', borderVisible: false,
      priceFormat: { type: 'price', precision: instrument.price_decimals, minMove: 10 ** -instrument.price_decimals },
    })
    let cancelled = false
    api(`${real ? '/real' : '/markets'}/candles/${symbol}?interval=${interval}&limit=300`).then((bars) => {
      if (cancelled) return
      series.current.setData(bars)
      last.current = { ...bars[bars.length - 1] }
      chart.timeScale().fitContent()
    })
    return () => {
      cancelled = true
      last.current = null
      series.current = null
      chart.remove()
    }
  }, [symbol, interval, instrument, real])

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
  }, [q, interval])

  return (
    <div className="panel chart-panel">
      <div className="chart-head">
        <div>
          <span className="sym lg">{symbol}</span> <span className="muted">{instrument?.name}</span>
          {q && <span className="mono price-big">{q.mid}</span>}
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
