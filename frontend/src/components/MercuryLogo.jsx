import { Link } from 'react-router-dom'

// The planet logo + "Mercury" + gold "AI" badge from the header.
export default function MercuryLogo({ to = '/' }) {
  return (
    <Link to={to} className="flex items-center gap-3 text-white" aria-label="Mercury AI home">
      <svg width="42" height="27" viewBox="0 0 38 24" aria-hidden="true">
        <ellipse cx="19" cy="12" rx="17" ry="6.5" transform="rotate(-18 19 12)" fill="none" stroke="#eab448" strokeWidth="2.4" />
        <circle cx="19" cy="12" r="8.5" fill="#eef0f7" />
        <path d="M12.5 15.5a8.5 8.5 0 0 0 13 0" fill="#c9cede" />
        <path d="M3 17.2C8 19 30 12 35.5 6.6" fill="none" stroke="#eab448" strokeWidth="2.4" strokeLinecap="round" />
      </svg>
      <span className="text-[25px] font-extrabold tracking-tight">Mercury</span>
      <span className="rounded-md bg-[#eab448] px-1.5 py-0.5 text-xs font-bold text-[#10173a]">AI</span>
    </Link>
  )
}
