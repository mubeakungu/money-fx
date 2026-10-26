import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import MarketList from '../components/MarketList'
import OrderTicket from '../components/OrderTicket'
import PriceChart from '../components/PriceChart'
import { OrdersTable } from './Orders'
import { useQuotes } from '../quotes'

export default function Trade() {
  const { symbol = 'EURUSD' } = useParams()
  const navigate = useNavigate()
  const { instruments } = useQuotes()
  const instrument = instruments.find((i) => i.symbol === symbol.toUpperCase())
  const [refreshKey, setRefreshKey] = useState(0)
  const [orders, setOrders] = useState([])

  useEffect(() => {
    api('/orders?limit=10').then(setOrders).catch(() => {})
  }, [refreshKey])

  return (
    <div className="trade-grid">
      <MarketList selected={instrument?.symbol} onSelect={(s) => navigate(`/trade/${s}`)} />
      <div className="trade-main">
        {instrument ? <PriceChart instrument={instrument} /> : <div className="panel chart-panel muted center">Loading markets…</div>}
        <div className="panel">
          <h3>Recent orders</h3>
          <OrdersTable orders={orders} onChange={() => setRefreshKey((k) => k + 1)} compact />
        </div>
      </div>
      <OrderTicket instrument={instrument} refreshKey={refreshKey} onPlaced={() => setRefreshKey((k) => k + 1)} />
    </div>
  )
}
