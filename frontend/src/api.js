const TOKEN_KEY = 'moneyfx_token'

// The published demo build (VITE_DEMO=1) has no server: requests go to an in-browser copy of the API.
export const DEMO = import.meta.env.VITE_DEMO === '1'
const demoServer = DEMO ? import('./demo/server') : null

export const getToken = () => {
  if (DEMO) return 'demo'
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}
export const setToken = (t) => {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) } catch { /* storage blocked */ }
}

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

export async function api(path, { method = 'GET', body } = {}) {
  if (DEMO) {
    try {
      return await (await demoServer).handle(method, path, body)
    } catch (e) {
      throw new ApiError(e.status ?? 400, e.message)
    }
  }
  const headers = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(`/api${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined })
  if (res.status === 401 && token) {
    setToken(null)
    window.dispatchEvent(new Event('moneyfx:logout'))
  }
  if (res.status === 204) return null
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    const detail = data?.detail
    const msg = Array.isArray(detail) ? detail.map((d) => d.msg).join(', ') : detail || res.statusText
    throw new ApiError(res.status, msg)
  }
  return data
}
