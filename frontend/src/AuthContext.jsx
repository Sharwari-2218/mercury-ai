import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, loginRequest, logoutRequest, refreshAccessToken, setAccessToken, setSessionExpiredHandler } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null) // { id, name, email, department, role, allowed_types }
  const [loading, setLoading] = useState(true) // true while we check the cookie on page load

  // On page load: if the refresh cookie is still valid, the user stays logged in.
  useEffect(() => {
    let cancelled = false
    refreshAccessToken()
      .then(() => api('/auth/me'))
      .then((me) => !cancelled && setUser(me))
      .catch(() => !cancelled && setUser(null))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    setSessionExpiredHandler(() => setUser(null))
  }, [])

  const login = useCallback(async (email, password) => {
    await loginRequest(email, password)
    const me = await api('/auth/me')
    setUser(me)
    return me
  }, [])

  const logout = useCallback(async () => {
    try {
      await logoutRequest()
    } finally {
      setAccessToken(null)
      setUser(null)
    }
  }, [])

  // Convenience for hiding UI. The backend still enforces the real rule.
  const can = useCallback((type) => !!user?.allowed_types?.includes(type), [user])

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, can, isAdmin: user?.role === 'admin' }}>
      {children}
    </AuthContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
