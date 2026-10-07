import { useEffect, useRef, useState } from 'react';
import { useUser } from '../lib/user';
import { DEPARTMENTS } from '../lib/modes';

const EMPTY = { name: '', email: '', department: DEPARTMENTS[0] };
const field =
  'min-h-[46px] w-full rounded-[10px] border border-line-strong bg-cream px-3.5 text-[15px] text-ink outline-none focus:border-teal';

export default function AccountDialog({ open, onClose }) {
  const ref = useRef(null);
  const { user, setUser } = useUser();
  const [form, setForm] = useState(user ?? EMPTY);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      setForm(user ?? EMPTY);
      dialog.showModal();
    }
    if (!open && dialog.open) dialog.close();
  }, [open, user]);

  const update = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  function save(e) {
    e.preventDefault();
    setUser({ name: form.name.trim(), email: form.email.trim(), department: form.department });
    onClose();
  }

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      className="m-auto w-[min(420px,calc(100%-32px))] rounded-2xl border border-line bg-white p-0 text-ink shadow-2xl backdrop:bg-navy-950/60"
    >
      <form onSubmit={save} className="flex flex-col gap-4 p-6">
        <div>
          <h2 className="text-xl font-bold tracking-tight">{user ? 'Your profile' : 'Sign in'}</h2>
          <p className="mt-1 text-sm text-muted">Used for posts, votes and tag alerts. Stored in this browser only.</p>
        </div>
        <label className="flex flex-col gap-1.5 text-sm font-semibold">
          Name
          <input required value={form.name} onChange={update('name')} className={field} autoComplete="name" />
        </label>
        <label className="flex flex-col gap-1.5 text-sm font-semibold">
          Email
          <input required type="email" value={form.email} onChange={update('email')} className={field} autoComplete="email" />
        </label>
        <label className="flex flex-col gap-1.5 text-sm font-semibold">
          Department
          <select value={form.department} onChange={update('department')} className={field}>
            {DEPARTMENTS.map((d) => <option key={d}>{d}</option>)}
          </select>
        </label>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button type="submit" className="min-h-11 cursor-pointer rounded-[10px] bg-teal px-5 text-sm font-semibold text-white hover:bg-teal-dark">
            Save
          </button>
          <button type="button" onClick={onClose} className="min-h-11 cursor-pointer rounded-[10px] border border-line-strong bg-white px-4 text-sm font-medium text-body">
            Cancel
          </button>
          {user && (
            <button
              type="button"
              onClick={() => { setUser(null); onClose(); }}
              className="ml-auto min-h-11 cursor-pointer rounded-[10px] px-3 text-sm font-medium text-err hover:bg-err-bg"
            >
              Sign out
            </button>
          )}
        </div>
      </form>
    </dialog>
  );
}
