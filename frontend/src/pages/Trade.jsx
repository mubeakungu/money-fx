import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import MarketList from '../components/MarketList'
import OrderTicket from '../components/OrderTicket'
import PriceChart from '../components/PriceChart'
import { OrdersTable } from './Orders'
import { useQuotes } from '../quotes'
import { useAccountMode } from '../account'
import RealTicket from '../real/RealTicket'
import { OpenTrades } from '../real/RealTrades'
import BotPositions from '../components/BotPositions'

export default function Trade() {
  const { symbol = 'EURUSD' } = useParams()
  const navigate = useNavigate()
  const { instruments } = useQuotes()
  const instrument = instruments.find((i) => i.symbol === symbol.toUpperCase())
  const [refreshKey, setRefreshKey] = useState(0)
  const [orders, setOrders] = useState([])
  const real = useAccountMode().mode === 'real'

  useEffect(() => {
    if (instruments.length && !instrument) navigate(`/trade/${instruments[0].symbol}`, { replace: true })
  }, [instruments, instrument])

  useEffect(() => {
    const load = () => api(real ? '/real/trades' : '/orders?limit=10').then(setOrders).catch(() => setOrders([]))
    load()
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [refreshKey, real])

  return (
    <div className="trade-grid">
      <MarketList selected={instrument?.symbol} onSelect={(s) => navigate(`/trade/${s}`)} />
      <div className="trade-main">
        {instrument ? <PriceChart instrument={instrument} /> : <div className="panel chart-panel muted center">Loading markets…</div>}
        {!real && <BotPositions compact hideEmpty />}
        <div className="panel">
          <h3>{real ? 'Open positions on OANDA' : 'Recent orders'}</h3>
          {real
            ? <OpenTrades trades={orders} onChange={() => setRefreshKey((k) => k + 1)} compact />
            : <OrdersTable orders={orders} onChange={() => setRefreshKey((k) => k + 1)} compact />}
        </div>

      </div>
      {real
        ? <RealTicket key="real" instrument={instrument} onPlaced={() => setRefreshKey((k) => k + 1)} />
        : <OrderTicket instrument={instrument} refreshKey={refreshKey} onPlaced={() => setRefreshKey((k) => k + 1)} />}
    </div>
  )
}
