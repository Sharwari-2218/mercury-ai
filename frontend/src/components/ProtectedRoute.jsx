import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../AuthContext'

// Wrap any page that needs login. adminOnly / requireType hide pages the user
// can't use. This is for a nicer UI only; the backend is what actually blocks access.
export default function ProtectedRoute({ children, adminOnly = false, requireType }) {
  const { user, loading, isAdmin, can } = useAuth()
  const location = useLocation()

  if (loading) {
    return <div className="mercury flex min-h-screen items-center justify-center bg-[#f5f3ef] text-sm text-[#6b6a73]">Loading…</div>
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  if ((adminOnly && !isAdmin) || (requireType && !can(requireType))) {
    return (
      <div className="mx-auto max-w-md p-10 text-center">
        <h1 className="text-xl font-bold text-[#10173a]">No access</h1>
        <p className="mt-2 text-[15px] text-[#4a4a55]">
          Your department doesn't have access to this page. Ask an administrator if you need it.
        </p>
      </div>
    )
  }
  return children
}
