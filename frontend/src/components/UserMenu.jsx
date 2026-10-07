import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../AuthContext'

// Number of sign-up requests waiting (admins only). Re-checks on every page change,
// every minute, and whenever the Admin page approves or rejects someone.
export function usePendingCount(enabled) {
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

function initials(name = '') {
  const parts = name.replace(/[^\p{L}\s]/gu, ' ').trim().split(/\s+/).filter(Boolean)
  return ((parts[0]?.[0] || '') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase() || '?'
}

// The round avatar on the right of the header (replaces the old "?" circle).
// Click it for: name + department, Admin page (admins), Sign out.
export default function UserMenu() {
  const { user, logout, isAdmin } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const pending = usePendingCount(isAdmin)
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  // Close when clicking outside, pressing Escape, or changing page.
  useEffect(() => {
    if (!open) return
    const onClick = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false)
    const onKey = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setOpen(false), [location.pathname])

  if (!user) return null

  async function handleLogout() {
    setOpen(false)
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account menu for ${user.name}`}
        className="relative flex h-12 w-12 items-center justify-center rounded-full bg-[#f5f3ef] text-sm font-bold text-[#10173a] ring-2 ring-transparent transition hover:ring-[#eab448]/70"
      >
        {initials(user.name)}
        {pending > 0 && (
          <span
            aria-label={`${pending} pending requests`}
            className="absolute -right-1 -top-1 flex h-5 min-w-[20px] items-center justify-center rounded-full bg-[#eab448] px-1 text-[11px] font-bold text-[#10173a] ring-2 ring-[#10194a]"
          >
            {pending}
          </span>
        )}
      </button>

      {open && (
        <div role="menu" className="absolute right-0 z-50 mt-3 w-64 overflow-hidden rounded-2xl bg-white text-[#10173a] shadow-[0_20px_50px_-12px_rgba(13,21,51,0.45)] ring-1 ring-black/5">
          <div className="border-b border-[#efebe5] px-4 py-3">
            <div className="truncate font-semibold">{user.name}</div>
            <div className="truncate text-sm text-[#6b6a73]">{user.email}</div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <span className="rounded-full bg-[#f5f3ef] px-2 py-0.5 text-xs font-semibold capitalize">{user.department}</span>
              {isAdmin && <span className="rounded-full bg-[#eab448]/20 px-2 py-0.5 text-xs font-semibold text-[#8a6416]">Admin</span>}
            </div>
          </div>
          <div className="p-1.5">
            {isAdmin && (
              <Link
                to="/admin"
                role="menuitem"
                className="flex items-center justify-between rounded-xl px-3 py-2 text-sm font-medium hover:bg-[#f5f3ef]"
              >
                Admin: access &amp; permissions
                {pending > 0 && <span className="rounded-full bg-[#172b60] px-2 py-0.5 text-xs font-bold text-white">{pending}</span>}
              </Link>
            )}
            <button
              onClick={handleLogout}
              role="menuitem"
              className="w-full rounded-xl px-3 py-2 text-left text-sm font-medium text-[#b42318] hover:bg-[#fef3f2]"
            >
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
