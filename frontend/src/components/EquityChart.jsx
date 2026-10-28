import { AreaSeries, ColorType, createChart, createSeriesMarkers } from 'lightweight-charts'
import { useEffect, useRef } from 'react'

export default function EquityChart({ curve, trades = [], height = 260 }) {
  const el = useRef(null)
  useEffect(() => {
    if (!el.current || !curve?.length) return
    const css = getComputedStyle(document.documentElement)
    const up = curve[curve.length - 1].value >= curve[0].value
    const color = up ? '#16c784' : '#ea3943'
    const chart = createChart(el.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: css.getPropertyValue('--muted').trim() },
      grid: { vertLines: { visible: false }, horzLines: { color: css.getPropertyValue('--grid').trim() } },
      timeScale: { timeVisible: true, borderVisible: false },
      rightPriceScale: { borderVisible: false },
    })
    const series = chart.addSeries(AreaSeries, {
      lineColor: color, topColor: up ? 'rgba(22,199,132,.25)' : 'rgba(234,57,67,.25)', bottomColor: 'transparent', lineWidth: 2,
    })
    series.setData(curve)
    // Entries in blue (up = buy, down = short), exits coloured by profit
    createSeriesMarkers(series, trades.flatMap((t) => {
      const short = t.side === 'short'
      return [
        { time: t.entry_time, position: short ? 'aboveBar' : 'belowBar', color: '#4c8dff', shape: short ? 'arrowDown' : 'arrowUp', size: 0.6 },
        { time: t.exit_time, position: short ? 'belowBar' : 'aboveBar', color: t.pnl > 0 ? '#16c784' : '#ea3943', shape: short ? 'arrowUp' : 'arrowDown', size: 0.6 },
      ]
    }).sort((a, b) => a.time - b.time))
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [curve, trades])
  return <div ref={el} style={{ height }} />
}
