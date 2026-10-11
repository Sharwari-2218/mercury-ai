// Mercury AI: routes + login.
//
// ┌──────────────────────────────────────────────────────────────────────────┐
// │ CHECK THESE 4 IMPORT LINES. They must point at YOUR existing page files. │
// │ If your files have other names or live in another folder (for example    │
// │ ./components/AskPage.jsx), change the paths below to match.             │
// │ If one is a "named" export (export function Ask), use { Ask } instead.   │
// └──────────────────────────────────────────────────────────────────────────┘
import Ask from './pages/Ask'
import Contribute from './pages/Contribute'
import Feed from './pages/Feed'
import Databloom from './components/Databloom'

import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './AuthContext'
import AppHeader from './components/AppHeader'
import ProtectedRoute from './components/ProtectedRoute'
import Admin from './pages/Admin'
import Login from './pages/Login'
import Signup from './pages/Signup'
import './mercury-theme.css'

// Header on top, the current page below. Only for signed-in users.
function SignedInLayout() {
  return (
    <ProtectedRoute>
      <div className="mercury relative min-h-screen bg-[#f5f3ef]">
        {/* navy band behind the header and the top of each page */}
        <div className="mercury-band absolute inset-x-0 top-0 h-[600px]" aria-hidden="true" />
        <div className="relative">
          <AppHeader />
          <Outlet />
        </div>
      </div>
    </ProtectedRoute>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Public pages */}
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />

          {/* Everything below needs a login. "/" (Ask) is the home page after sign-in. */}
          <Route element={<SignedInLayout />}>
            <Route path="/" element={<Ask />} />
            <Route path="/contribute" element={<Contribute />} />
            <Route path="/feed" element={<Feed />} />
            <Route path="/databloom" element={<Databloom />} />
            <Route
              path="/admin"
              element={
                <ProtectedRoute adminOnly>
                  <Admin />
                </ProtectedRoute>
              }
            />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
