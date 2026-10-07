// Shared frame for Login and Sign-up, in the Mercury style: navy band with a gold
// label and big white headline, and a white card that overlaps onto the cream page.
import '../mercury-theme.css'
import MercuryLogo from './MercuryLogo'
import { eyebrowClass } from '../theme'

export { fieldClass, primaryButtonClass } from '../theme'

export function Field({ id, label, hint, children }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-[15px] font-semibold text-[#10173a]">
        {label}
      </label>
      {children}
      {hint && <p className="mt-1.5 text-[13px] text-[#6b6a73]">{hint}</p>}
    </div>
  )
}

// tone: "error" (red), "info" (gold, e.g. waiting for approval), "success" (green)
export function Notice({ tone = 'error', children }) {
  const styles = {
    error: 'border-[#fecdca] bg-[#fef3f2] text-[#b42318]',
    info: 'border-[#eab448]/40 bg-[#fdf6e7] text-[#7a5410]',
    success: 'border-[#a6e3c0] bg-[#effbf4] text-[#146c3c]',
  }
  return (
    <div role={tone === 'error' ? 'alert' : 'status'} className={`rounded-xl border px-4 py-3 text-sm leading-relaxed ${styles[tone]}`}>
      {children}
    </div>
  )
}

export default function AuthLayout({ eyebrow, title, subtitle, children, footer }) {
  return (
    <div className="mercury min-h-screen bg-[#f5f3ef] text-[#10173a]">
      <div className="mercury-band px-5 pb-40 pt-6 sm:pb-44">
        <div className="mx-auto max-w-[1500px]">
          <MercuryLogo to="/login" />
        </div>
        <div className="mx-auto mt-12 max-w-[480px] text-center sm:mt-16">
          {eyebrow && <p className={eyebrowClass}>{eyebrow}</p>}
          <h1 className="mt-3 text-[34px] font-extrabold leading-tight tracking-[-0.03em] text-white sm:text-[44px]">{title}</h1>
          {subtitle && <p className="mt-3 text-[17px] leading-relaxed text-white/75">{subtitle}</p>}
        </div>
      </div>
      <div className="relative -mt-32 px-4 pb-12 sm:-mt-36">
        <div className="mx-auto max-w-[480px]">
          <div className="rounded-[28px] bg-white p-6 shadow-[0_10px_40px_-12px_rgba(13,21,51,0.25)] sm:p-8">{children}</div>
          {footer && <div className="mt-6 text-center text-[15px] text-[#4a4a55]">{footer}</div>}
        </div>
      </div>
    </div>
  )
}
