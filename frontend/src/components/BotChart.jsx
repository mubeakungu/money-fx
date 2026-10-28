import { CandlestickSeries, LineSeries, createChart, createSeriesMarkers } from 'lightweight-charts'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { epochSeconds } from '../format'
import { channel, lineData, rsi, sma } from '../indicators'
import { CANDLES, COLORS, addRsiPane, chartOptions, lineOptions } from './chartTheme'

const STEP = { '1m': 60, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400 }

/** The bot's market with what its strategy sees (averages, RSI or channel) and where it traded. */
export default function BotChart({ bot, trades }) {
  const el = useRef(null)
  const [candles, setCandles] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    const path = bot.broker === 'oanda' ? '/real/candles' : '/markets/candles'
    const load = () => api(`${path}/${bot.symbol}?interval=${bot.interval}&limit=300`)
      .then((c) => { if (alive) { setCandles(c); setError(null) } })
      .catch((e) => alive && setError(e.message))
    load()
    const t = setInterval(load, Math.min(STEP[bot.interval], 60) * 1000)
    return () => { alive = false; clearInterval(t) }
  }, [bot.symbol, bot.interval, bot.broker])

  const tradeKey = trades.map((t) => t.id).join(',')
  useEffect(() => {
    if (!el.current || !candles?.length) return
    const chart = createChart(el.current, chartOptions())
    const price = chart.addSeries(CandlestickSeries, CANDLES)
    price.setData(candles)
    const closes = candles.map((c) => c.close)
    const p = bot.params
    if (bot.strategy === 'sma_cross') {
      chart.addSeries(LineSeries, lineOptions(COLORS.fast)).setData(lineData(candles, sma(closes, p.fast)))
      chart.addSeries(LineSeries, lineOptions(COLORS.slow)).setData(lineData(candles, sma(closes, p.slow)))
    } else if (bot.strategy === 'breakout') {
      const ch = channel(candles, p.lookback)
      const opts = lineOptions(COLORS.channel, { lineStyle: 2 })
      chart.addSeries(LineSeries, opts).setData(lineData(candles, ch.upper))
      chart.addSeries(LineSeries, opts).setData(lineData(candles, ch.lower))
    } else if (bot.strategy === 'rsi') {
      addRsiPane(chart, LineSeries, p.oversold, p.overbought).setData(lineData(candles, rsi(closes, p.period)))
    }

    // A trade happens on the candle after the signal candle closes; pin it to the candle it falls in
    const step = STEP[bot.interval]
    const times = new Set(candles.map((c) => c.time))
    const markers = trades
      .map((t) => ({ t, time: Math.floor(epochSeconds(t.created_at) / step) * step }))
      .filter(({ time }) => times.has(time))
      .map(({ t, time }) => {
        const short = t.side === 'short'
        if (t.action === 'open') {
          return { time, position: short ? 'aboveBar' : 'belowBar', shape: short ? 'arrowDown' : 'arrowUp',
            color: '#4c8dff', text: short ? 'SHORT' : 'BUY' }
        }
        const pnl = Number(t.pnl)
        return { time, position: short ? 'belowBar' : 'aboveBar', shape: 'circle', color: pnl > 0 ? '#16c784' : '#ea3943',
          text: `${pnl > 0 ? '+' : ''}${pnl.toFixed(2)}` }
      })
      .sort((a, b) => a.time - b.time)
    createSeriesMarkers(price, markers)
    // Show the most recent candles; scroll or pinch to see further back
    chart.timeScale().setVisibleLogicalRange({ from: candles.length - 120, to: candles.length + 2 })
    return () => chart.remove()
  }, [candles, tradeKey, bot.strategy, JSON.stringify(bot.params), bot.interval])

  const legend = {
    sma_cross: [[COLORS.fast, `MA ${bot.params.fast}`], [COLORS.slow, `MA ${bot.params.slow}`]],
    breakout: [[COLORS.channel, `${bot.params.lookback}-candle high / low`]],
    rsi: [[COLORS.rsi, `RSI ${bot.params.period} (buy above ${bot.params.oversold}, sell below ${bot.params.overbought})`]],
  }[bot.strategy] ?? []

  return (
    <div className="panel">
      <div className="row-between">
        <h3>{bot.symbol} · {bot.interval} · what the bot sees</h3>
        <span className="muted xs legend">
          {legend.map(([c, l]) => <span key={l}><span className="dot" style={{ background: c }} />{l}</span>)}
          <span><span className="dot" style={{ background: '#4c8dff' }} />entries</span>
        </span>
      </div>
      {error ? <p className="muted">{error}</p> : <div className="chart bot-chart" ref={el} />}
    </div>
  )
}
