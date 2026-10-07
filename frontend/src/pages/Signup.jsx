import { useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../AuthContext'
import AuthLayout, { Field, Notice, fieldClass, primaryButtonClass } from '../components/AuthLayout'
import { linkClass } from '../theme'

const EMPTY = { name: '', email: '', department: '', reason: '', password: '', confirm: '' }

export default function Signup() {
  const { user, loading } = useAuth()
  const [form, setForm] = useState(EMPTY)
  const [options, setOptions] = useState({ departments: [], allowed_domains: [] })
  const [optionsError, setOptionsError] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [sentTo, setSentTo] = useState(null) // email the request was sent for

  useEffect(() => {
    api('/auth/signup-options', { retry: false })
      .then(setOptions)
      .catch(() => setOptionsError('Could not load the department list. Please refresh the page.'))
  }, [])

  if (!loading && user) return <Navigate to="/" replace />

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })
  const domains = options.allowed_domains
  const domainHint = domains.length ? `Use your company email (${domains.map((d) => '@' + d).join(' or ')}).` : undefined

  function validate() {
    const email = form.email.trim().toLowerCase()
    if (domains.length && !domains.includes(email.split('@').pop())) return `Please use your company email (${domains.map((d) => '@' + d).join(' or ')}).`
    if (!form.department) return 'Please choose your department.'
    if (form.password.length < 10) return 'Password must be at least 10 characters.'
    if (form.password !== form.confirm) return "The two passwords don't match."
    return ''
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const problem = validate()
    setError(problem)
    if (problem) return
    setSubmitting(true)
    try {
      await api('/auth/signup', {
        method: 'POST',
        retry: false,
        body: {
          name: form.name.trim(),
          email: form.email.trim(),
          department: form.department,
          reason: form.reason.trim() || null,
          password: form.password,
        },
      })
      setSentTo(form.email.trim())
      setForm(EMPTY)
    } catch (err) {
      setError(err.status === 429 ? 'Too many attempts. Please wait a while and try again.' : err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const backToLogin = (
    <>
      Already have an account?{' '}
      <Link to="/login" className={linkClass}>
        Sign in
      </Link>
    </>
  )

  if (sentTo) {
    return (
      <AuthLayout eyebrow="Almost there" title="Request sent" subtitle="An administrator will review it shortly." footer={backToLogin}>
        <div className="space-y-5 text-center text-[15px] leading-relaxed text-[#4a4a55]">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-[#eab448]/20 text-xl font-bold text-[#8a6416]" aria-hidden>
            ✓
          </div>
          <p>
            We'll email <span className="font-semibold text-[#10173a]">{sentTo}</span> once your access is approved. After
            that, sign in with the password you just chose.
          </p>
          <Link
            to="/login"
            state={{ email: sentTo, justSignedUp: true }}
            className={`${primaryButtonClass} block text-center`}
          >
            Go to sign in
          </Link>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout eyebrow="Join Mercury" title="Request access" subtitle="An administrator approves every new account." footer={backToLogin}>
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {optionsError && <Notice>{optionsError}</Notice>}
        {error && <Notice>{error}</Notice>}

        <Field id="name" label="Full name">
          <input id="name" autoComplete="name" required maxLength={100} value={form.name} onChange={set('name')} className={fieldClass} />
        </Field>

        <Field id="email" label="Work email" hint={domainHint}>
          <input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={form.email}
            onChange={set('email')}
            className={fieldClass}
            placeholder="you@company.com"
          />
        </Field>

        <Field id="department" label="Department" hint="The admin confirms this before you get access.">
          <select id="department" required value={form.department} onChange={set('department')} className={fieldClass}>
            <option value="" disabled>
              Choose your department
            </option>
            {options.departments.map((d) => (
              <option key={d} value={d}>
                {d.charAt(0).toUpperCase() + d.slice(1)}
              </option>
            ))}
          </select>
        </Field>

        <Field id="reason" label={<>Why do you need access? <span className="font-normal text-[#9a9890]">(optional)</span></>}>
          <textarea
            id="reason"
            rows={2}
            maxLength={500}
            value={form.reason}
            onChange={set('reason')}
            className={`${fieldClass} resize-none`}
            placeholder="e.g. I joined the HR team this week"
          />
        </Field>

        <Field id="password" label="Password" hint="At least 10 characters.">
          <input
            id="password"
            type="password"
            autoComplete="new-password"
            required
            minLength={10}
            value={form.password}
            onChange={set('password')}
            className={fieldClass}
          />
        </Field>

        <Field id="confirm" label="Confirm password">
          <input
            id="confirm"
            type="password"
            autoComplete="new-password"
            required
            value={form.confirm}
            onChange={set('confirm')}
            className={fieldClass}
          />
        </Field>

        <button type="submit" disabled={submitting || !!optionsError} className={primaryButtonClass}>
          {submitting ? 'Sending request…' : 'Request access'}
        </button>
      </form>
    </AuthLayout>
  )
}
