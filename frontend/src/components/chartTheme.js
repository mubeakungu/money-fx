import { ColorType } from 'lightweight-charts'

export const CANDLES = { upColor: '#16c784', downColor: '#ea3943', wickUpColor: '#16c784', wickDownColor: '#ea3943', borderVisible: false }
export const COLORS = { fast: '#f5b041', slow: '#a78bfa', rsi: '#4c8dff', channel: '#8b95a7' }

export function chartOptions() {
  const css = getComputedStyle(document.documentElement)
  return {
    autoSize: true,
    layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: css.getPropertyValue('--muted').trim(),
      panes: { separatorColor: css.getPropertyValue('--border').trim() } },
    grid: { vertLines: { color: css.getPropertyValue('--grid').trim() }, horzLines: { color: css.getPropertyValue('--grid').trim() } },
    timeScale: { timeVisible: true, secondsVisible: false, borderVisible: false },
    rightPriceScale: { borderVisible: false },
    crosshair: { mode: 0 },
  }
}

const LINE = { lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }

export const lineOptions = (color, extra = {}) => ({ ...LINE, color, ...extra })

/** An RSI line in its own pane under the price, with the two threshold levels marked. */
export function addRsiPane(chart, LineSeries, lower = 30, upper = 70) {
  const s = chart.addSeries(LineSeries, lineOptions(COLORS.rsi, { lastValueVisible: true, priceFormat: { type: 'price', precision: 1, minMove: 0.1 } }), 1)
  for (const level of [lower, upper]) s.createPriceLine({ price: level, color: COLORS.channel, lineStyle: 2, lineWidth: 1, axisLabelVisible: true, title: '' })
  chart.panes()[1]?.setHeight(110)
  return s
}
