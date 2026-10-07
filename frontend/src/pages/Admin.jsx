import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { useAuth } from '../AuthContext'
import { cardClass, eyebrowClass, fieldClass, secondaryButtonClass, smallPrimaryButtonClass } from '../theme'
import '../mercury-theme.css'

const TYPES = [
  { id: 'doc', label: 'Documents' },
  { id: 'wiki', label: 'Wikis' },
  { id: 'code', label: 'Code (GitTalk)' },
]

const input = fieldClass

function Card({ title, subtitle, children }) {
  return (
    <section className={`${cardClass} p-6 sm:p-8`}>
      <h2 className="text-lg font-bold tracking-tight text-[#10173a]">{title}</h2>
      {subtitle && <p className="mt-1 text-sm text-[#6b6a73]">{subtitle}</p>}
      <div className="mt-4">{children}</div>
    </section>
  )
}

function Message({ msg }) {
  if (!msg) return null
  const style = msg.ok ? 'border-[#a6e3c0] bg-[#effbf4] text-[#146c3c]' : 'border-[#fecdca] bg-[#fef3f2] text-[#b42318]'
  return <div role="status" className={`rounded-xl border px-4 py-2.5 text-sm ${style}`}>{msg.text}</div>
}

function CreateUserForm({ departments, onCreated }) {
  const empty = { name: '', email: '', password: '', department: '', role: 'member' }
  const [form, setForm] = useState(empty)
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  async function submit(e) {
    e.preventDefault()
    setMsg(null)
    setBusy(true)
    try {
      const u = await api('/auth/users', { method: 'POST', body: { ...form, department: form.department || departments[0] } })
      setMsg({ ok: true, text: `Created ${u.name} (${u.department}). Share the password with them privately.` })
      setForm(empty)
      onCreated()
    } catch (err) {
      setMsg({ ok: false, text: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <Message msg={msg} />
      <div className="grid gap-3 sm:grid-cols-2">
        <input className={input} placeholder="Full name" required value={form.name} onChange={set('name')} />
        <input className={input} type="email" placeholder="Email" required value={form.email} onChange={set('email')} />
        <input
          className={input}
          type="password"
          autoComplete="new-password"
          placeholder="Temporary password (10+ characters)"
          required
          minLength={10}
          value={form.password}
          onChange={set('password')}
        />
        <select className={input} value={form.department || departments[0] || ''} onChange={set('department')} required>
          {departments.length === 0 && <option value="">Add a department first</option>}
          {departments.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
      </div>
      <label className="flex items-center gap-2 text-sm text-[#2b2b36]">
        <input
          type="checkbox"
          checked={form.role === 'admin'}
          onChange={(e) => setForm({ ...form, role: e.target.checked ? 'admin' : 'member' })}
        />
        Make this user an administrator (can see everything and manage users)
      </label>
      <button
        type="submit"
        disabled={busy || departments.length === 0}
        className={smallPrimaryButtonClass}
      >
        {busy ? 'Creating…' : 'Create user'}
      </button>
    </form>
  )
}

function timeAgo(iso) {
  if (!iso) return ''
  // The backend stores UTC; add "Z" if the timestamp has no timezone so the browser reads it as UTC.
  const then = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + 'Z')
  const mins = Math.round((Date.now() - then.getTime()) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours} h ago`
  return then.toLocaleDateString()
}

function RequestRow({ req, departments, onDone }) {
  // The admin can change the department and role before approving.
  const [department, setDepartment] = useState(departments.includes(req.department) ? req.department : departments[0] || '')
  const [makeAdmin, setMakeAdmin] = useState(false)
  const [busy, setBusy] = useState(null) // 'approve' | 'reject'
  const [error, setError] = useState('')

  async function act(action) {
    if (action === 'reject' && !window.confirm(`Reject the request from ${req.name}?`)) return
    setBusy(action)
    setError('')
    try {
      const body = action === 'approve' ? { department, role: makeAdmin ? 'admin' : 'member' } : undefined
      await api(`/auth/requests/${req.id}/${action}`, { method: 'POST', body })
      onDone(action === 'approve' ? `Approved ${req.name} as ${department}.` : `Rejected the request from ${req.name}.`)
    } catch (err) {
      setError(err.message)
      setBusy(null)
    }
  }

  const changed = department !== req.department

  return (
    <li className="rounded-2xl border border-[#e7e3dc] bg-[#fcfbf9] p-4">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
        <div>
          <div className="font-medium text-[#10173a]">{req.name}</div>
          <div className="text-sm text-[#6b6a73]">{req.email}</div>
        </div>
        <div className="text-xs text-[#6b6a73]">
          Asked for <span className="font-medium text-[#2b2b36]">{req.department}</span> · {timeAgo(req.created_at)}
        </div>
      </div>
      {req.reason && <p className="mt-3 rounded-xl bg-[#f5f3ef] px-3 py-2 text-sm text-[#2b2b36]">“{req.reason}”</p>}
      {error && (
        <div className="mt-3">
          <Message msg={{ ok: false, text: error }} />
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-[#2b2b36]">
          Department
          <select
            value={department}
            onChange={(e) => setDepartment(e.target.value)}
            className="rounded-xl border border-[#d4d0c6] bg-[#f9f7f3] px-3 py-2 text-sm text-[#10173a] outline-none focus:border-[#172b60] focus:ring-4 focus:ring-[#172b60]/10"
          >
            {departments.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-[#2b2b36]">
          <input type="checkbox" checked={makeAdmin} onChange={(e) => setMakeAdmin(e.target.checked)} className="accent-[#172b60]" />
          Admin
        </label>
        {changed && <span className="text-xs font-semibold text-[#8a6416]">Changed from {req.department}</span>}
        <div className="ml-auto flex gap-2">
          <button
            onClick={() => act('reject')}
            disabled={!!busy}
            className={secondaryButtonClass}
          >
            {busy === 'reject' ? 'Rejecting…' : 'Reject'}
          </button>
          <button
            onClick={() => act('approve')}
            disabled={!!busy || !department}
            className={smallPrimaryButtonClass}
          >
            {busy === 'approve' ? 'Approving…' : 'Approve'}
          </button>
        </div>
      </div>
    </li>
  )
}

function PendingRequests({ requests, departments, onChange }) {
  const [msg, setMsg] = useState(null)

  function done(text) {
    setMsg({ ok: true, text })
    onChange()
  }

  return (
    <div className="space-y-3">
      <Message msg={msg} />
      {requests.length === 0 ? (
        <p className="text-sm text-[#6b6a73]">No requests waiting. New sign-ups will appear here.</p>
      ) : (
        <ul className="space-y-3">
          {requests.map((r) => (
            <RequestRow key={r.id} req={r} departments={departments} onDone={done} />
          ))}
        </ul>
      )}
    </div>
  )
}

const STATUS_STYLE = {
  active: 'text-[#146c3c]',
  disabled: 'text-[#9a9890]',
  rejected: 'text-[#b42318]',
}

function UsersTable({ users, onChange }) {
  const { user: me } = useAuth()
  const [error, setError] = useState('')

  async function toggle(u) {
    setError('')
    try {
      await api(`/auth/users/${u.id}/${u.status === 'active' ? 'deactivate' : 'activate'}`, { method: 'POST' })
      onChange()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <>
      {error && <Message msg={{ ok: false, text: error }} />}
      <div className="-mx-6 overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-[#e7e3dc] text-left text-xs font-bold uppercase tracking-[0.1em] text-[#8a8893]">
              <th className="px-6 py-2 font-medium">Name</th>
              <th className="px-3 py-2 font-medium">Department</th>
              <th className="px-3 py-2 font-medium">Can see</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-6 py-2" />
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-b border-[#f0ede7] last:border-0">
                <td className="px-6 py-3">
                  <div className="font-medium text-[#10173a]">
                    {u.name}
                    {u.role === 'admin' && (
                      <span className="ml-2 rounded-full bg-[#eab448]/20 px-2 py-0.5 text-xs font-semibold text-[#8a6416]">admin</span>
                    )}
                  </div>
                  <div className="text-[#6b6a73]">{u.email}</div>
                </td>
                <td className="px-3 py-3 text-[#2b2b36]">{u.department}</td>
                <td className="px-3 py-3 text-[#2b2b36]">{u.allowed_types.join(', ') || 'nothing'}</td>
                <td className="px-3 py-3">
                  <span className={`capitalize ${STATUS_STYLE[u.status] || 'text-[#6b6a73]'}`}>{u.status}</span>
                </td>
                <td className="px-6 py-3 text-right">
                  {u.id !== me.id && (u.status === 'active' || u.status === 'disabled') && (
                    <button onClick={() => toggle(u)} className="text-sm font-semibold text-[#172b60] hover:underline">
                      {u.status === 'active' ? 'Disable' : 'Enable'}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

function PoliciesEditor({ policies, onChange }) {
  const [newDept, setNewDept] = useState('')
  const [msg, setMsg] = useState(null)

  async function save(department, allowed_types) {
    setMsg(null)
    try {
      await api('/auth/policies', { method: 'PUT', body: { department, allowed_types } })
      onChange()
      return true
    } catch (err) {
      setMsg({ ok: false, text: err.message })
      return false
    }
  }

  function toggleType(p, type) {
    const next = p.allowed_types.includes(type) ? p.allowed_types.filter((t) => t !== type) : [...p.allowed_types, type]
    save(p.department, next)
  }

  async function addDept(e) {
    e.preventDefault()
    const name = newDept.trim().toLowerCase()
    if (!name) return
    if (await save(name, ['doc'])) {
      setNewDept('')
      setMsg({ ok: true, text: `Added "${name}" with access to documents. Tick more boxes to give it more.` })
    }
  }

  return (
    <div className="space-y-4">
      <Message msg={msg} />
      <div className="-mx-6 overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-[#e7e3dc] text-left text-xs font-bold uppercase tracking-[0.1em] text-[#8a8893]">
              <th className="px-6 py-2 font-medium">Department</th>
              {TYPES.map((t) => (
                <th key={t.id} className="px-3 py-2 text-center font-medium">{t.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {policies.map((p) => (
              <tr key={p.department} className="border-b border-[#f0ede7] last:border-0">
                <td className="px-6 py-3 font-medium text-[#10173a]">{p.department}</td>
                {TYPES.map((t) => (
                  <td key={t.id} className="px-3 py-3 text-center">
                    <input
                      type="checkbox"
                      aria-label={`${p.department} can see ${t.label}`}
                      checked={p.allowed_types.includes(t.id)}
                      onChange={() => toggleType(p, t.id)}
                      className="h-4 w-4 accent-[#172b60]"
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <form onSubmit={addDept} className="flex gap-2">
        <input
          className={input}
          placeholder="New department, e.g. finance"
          pattern="[A-Za-z0-9_\-]+"
          title="Letters, numbers, - and _ only"
          value={newDept}
          onChange={(e) => setNewDept(e.target.value)}
        />
        <button type="submit" className={`shrink-0 ${secondaryButtonClass}`}>
          Add department
        </button>
      </form>
    </div>
  )
}

export default function Admin() {
  const [users, setUsers] = useState([])
  const [requests, setRequests] = useState([])
  const [policies, setPolicies] = useState([])
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const [u, r, p] = await Promise.all([api('/auth/users'), api('/auth/requests'), api('/auth/policies')])
      setUsers(u)
      setRequests(r)
      setPolicies(p)
      window.dispatchEvent(new Event('mercury:requests-changed')) // updates the badge in the nav bar
    } catch (err) {
      setError(err.message)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const departments = policies.map((p) => p.department)

  return (
    <div className="mercury min-h-screen bg-[#f5f3ef] text-[#10173a]">
      <div className="mercury-band px-5 pb-40 pt-12">
        <div className="mx-auto max-w-[1500px]">
          <p className={eyebrowClass}>Administration</p>
          <h1 className="mt-3 text-[40px] font-extrabold leading-tight tracking-[-0.03em] text-white sm:text-[52px]">Manage access</h1>
          <p className="mt-3 max-w-2xl text-[18px] leading-relaxed text-white/75">
            Approve new people and decide what each department can search.
          </p>
        </div>
      </div>
      <div className="-mt-32 space-y-6 px-5 pb-16">
      <div className="mx-auto max-w-[1500px]"><div className="max-w-[1150px] space-y-6">
      {error && <Message msg={{ ok: false, text: error }} />}

      <Card
        title={
          <span className="flex items-center gap-2">
            Access requests
            {requests.length > 0 && (
              <span className="rounded-full bg-[#eab448] px-2.5 py-0.5 text-xs font-bold text-[#10173a]">{requests.length}</span>
            )}
          </span>
        }
        subtitle="People who signed up and are waiting. You can change their department before approving."
      >
        <PendingRequests requests={requests} departments={departments} onChange={load} />
      </Card>

      <Card title="Department permissions" subtitle="Changes apply on the user's next request. Admins always see everything.">
        <PoliciesEditor policies={policies} onChange={load} />
      </Card>

      <Card title="Add a user directly" subtitle="Skips the request step. Useful for adding several people at once.">
        <CreateUserForm departments={departments} onCreated={load} />
      </Card>

      <Card title={`Users (${users.length})`}>
        <UsersTable users={users} onChange={load} />
      </Card>
      </div></div>
      </div>
    </div>
  )
}
