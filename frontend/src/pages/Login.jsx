import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../AuthContext'
import AuthLayout, { Field, Notice, fieldClass, primaryButtonClass } from '../components/AuthLayout'
import { linkClass } from '../theme'

export default function Login() {
  const { user, login, loading } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState(location.state?.email || '')
  const [password, setPassword] = useState('')
  const [notice, setNotice] = useState(null) // { tone, text }
  const [submitting, setSubmitting] = useState(false)

  const goTo = location.state?.from || '/'

  if (!loading && user) return <Navigate to={goTo} replace />

  async function handleSubmit(e) {
    e.preventDefault()
    setNotice(null)
    setSubmitting(true)
    try {
      await login(email.trim(), password)
      navigate(goTo, { replace: true })
    } catch (err) {
      if (err.status === 401) setNotice({ tone: 'error', text: 'Incorrect email or password.' })
      // 403 = correct password but the account is pending, rejected or disabled.
      // The backend sends a clear explanation; show it as a notice, not an error.
      else if (err.status === 403) setNotice({ tone: 'info', text: err.message })
      else setNotice({ tone: 'error', text: err.message || 'Could not sign in. Please try again.' })
      setPassword('')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout
      eyebrow="Company knowledge assistant"
      title="Welcome back"
      subtitle="Sign in to ask your company anything."
      footer={
        <>
          New here?{' '}
          <Link to="/signup" className={linkClass}>
            Request access
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {location.state?.justSignedUp && !notice && (
          <Notice tone="success">Request sent. You can sign in once an administrator approves it.</Notice>
        )}
        {notice && <Notice tone={notice.tone}>{notice.text}</Notice>}

        <Field id="email" label="Work email">
          <input
            id="email"
            type="email"
            autoComplete="username"
            required
            autoFocus={!email}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={fieldClass}
            placeholder="you@company.com"
          />
        </Field>

        <Field id="password" label="Password">
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            autoFocus={!!email}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={fieldClass}
          />
        </Field>

        <button type="submit" disabled={submitting} className={primaryButtonClass}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </AuthLayout>
  )
}
