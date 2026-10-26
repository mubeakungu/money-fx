export const usd = (v, opts = {}) =>
  Number(v).toLocaleString('en-US', { style: 'currency', currency: 'USD', ...opts })

export const num = (v, dp) =>
  Number(v).toLocaleString('en-US', { minimumFractionDigits: dp ?? 0, maximumFractionDigits: dp ?? 8 })

export const pct = (v) => `${v > 0 ? '+' : ''}${Number(v).toFixed(2)}%`

export const signClass = (v) => (Number(v) > 0 ? 'up' : Number(v) < 0 ? 'down' : '')

export const dateTime = (iso) =>
  new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z').toLocaleString()

export const ASSET_LABELS = { forex: 'Forex', crypto: 'Crypto', stock: 'Stocks', commodity: 'Commodities', cash: 'Cash' }
