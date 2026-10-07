import { useEffect, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../AuthContext'

const link = ({ isActive }) =>
  `flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium ${isActive ? 'bg-slate-100 text-slate-900' : 'text-slate-600 hover:text-slate-900'}`

// Number of sign-up requests waiting, for the badge on "Admin". Checks on every
// page change, every minute, and whenever the Admin page approves/rejects someone.
function usePendingCount(enabled) {
  const [count, setCount] = useState(0)
  const location = useLocation()

  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    const check = () =>
      api('/auth/requests')
        .then((r) => !cancelled && setCount(r.length))
        .catch(() => {})
    check()
    const timer = setInterval(check, 60_000)
    window.addEventListener('mercury:requests-changed', check)
    return () => {
      cancelled = true
      clearInterval(timer)
      window.removeEventListener('mercury:requests-changed', check)
    }
  }, [enabled, location.pathname])

  return enabled ? count : 0
}

export default function NavBar() {
  const { user, logout, isAdmin } = useAuth()
  const navigate = useNavigate()
  const pending = usePendingCount(isAdmin)

  async function handleLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-2 px-4 py-3">
        <span className="mr-4 font-semibold text-slate-900">Mercury AI</span>
        <nav className="flex flex-wrap gap-1">
          <NavLink to="/" end className={link}>Chat</NavLink>
          <NavLink to="/contribute" className={link}>Contribute</NavLink>
          <NavLink to="/feed" className={link}>Feed</NavLink>
          {isAdmin && (
            <NavLink to="/admin" className={link}>
              Admin
              {pending > 0 && (
                <span aria-label={`${pending} pending requests`} className="rounded-full bg-indigo-600 px-1.5 text-xs font-medium leading-5 text-white">
                  {pending}
                </span>
              )}
            </NavLink>
          )}
        </nav>
        <div className="ml-auto flex items-center gap-3">
          <span className="hidden text-right text-sm sm:block">
            <span className="block font-medium text-slate-900">{user.name}</span>
            <span className="block text-xs text-slate-500">{user.department}</span>
          </span>
          <button onClick={handleLogout} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50">
            Sign out
          </button>
        </div>
      </div>
    </header>
  )
}
