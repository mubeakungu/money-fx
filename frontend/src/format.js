export const usd = (v, opts = {}) =>
  Number(v).toLocaleString('en-US', { style: 'currency', currency: 'USD', ...opts })

export const num = (v, dp) =>
  Number(v).toLocaleString('en-US', { minimumFractionDigits: dp ?? 0, maximumFractionDigits: dp ?? 8 })

export const pct = (v) => `${v > 0 ? '+' : ''}${Number(v).toFixed(2)}%`

export const signClass = (v) => (Number(v) > 0 ? 'up' : Number(v) < 0 ? 'down' : '')

// The API sends UTC times, sometimes without a zone suffix
const utc = (iso) => new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z')
export const dateTime = (iso) => utc(iso).toLocaleString()
export const epochSeconds = (iso) => utc(iso).getTime() / 1000

export const ASSET_LABELS = { forex: 'Forex', crypto: 'Crypto', stock: 'Stocks', commodity: 'Commodities', cash: 'Cash' }
