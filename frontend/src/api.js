// One place for every call to the backend.
// The access token lives only in this variable (memory), never in localStorage,
// so a malicious script can't read it from storage. On a page reload it's gone,
// and we get a fresh one from the httpOnly refresh cookie via /auth/refresh.

const API_BASE = import.meta.env.VITE_API_URL ?? '/api'

let accessToken = null
let refreshPromise = null // so 5 requests failing at once trigger only 1 refresh
let onSessionExpired = () => {}

export function setAccessToken(token) {
  accessToken = token
}

export function setSessionExpiredHandler(fn) {
  onSessionExpired = fn
}

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

async function readError(res) {
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail)) return body.detail.map((d) => d.msg).join(', ')
  } catch {
    /* not JSON */
  }
  return `Request failed (${res.status})`
}

export function refreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = fetch(`${API_BASE}/auth/refresh`, { method: 'POST', credentials: 'include' })
      .then(async (res) => {
        if (!res.ok) throw new ApiError(res.status, 'Session expired')
        const data = await res.json()
        accessToken = data.access_token
        return accessToken
      })
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

// Use this instead of fetch() everywhere in the app.
// `body` can be a plain object (sent as JSON), FormData or URLSearchParams.
export async function api(path, { method = 'GET', body, headers = {}, retry = true } = {}) {
  const opts = { method, credentials: 'include', headers: { ...headers } }
  if (body instanceof FormData || body instanceof URLSearchParams) {
    opts.body = body
  } else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  if (accessToken) opts.headers.Authorization = `Bearer ${accessToken}`

  const res = await fetch(`${API_BASE}${path}`, opts)

  // Access token expired: get a new one once, then repeat the request.
  if (res.status === 401 && retry && !path.startsWith('/auth/')) {
    try {
      await refreshAccessToken()
    } catch {
      accessToken = null
      onSessionExpired()
      throw new ApiError(401, 'Your session has expired. Please sign in again.')
    }
    return api(path, { method, body, headers, retry: false })
  }

  if (!res.ok) throw new ApiError(res.status, await readError(res))
  if (res.status === 204) return null
  return res.json()
}

export async function loginRequest(email, password) {
  // FastAPI's OAuth2 form expects the fields "username" and "password".
  const form = new URLSearchParams({ username: email, password })
  const data = await api('/auth/login', { method: 'POST', body: form, retry: false })
  accessToken = data.access_token
}

export async function logoutRequest() {
  try {
    await api('/auth/logout', { method: 'POST', retry: false })
  } finally {
    accessToken = null
  }
}
