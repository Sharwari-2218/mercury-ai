import { NavLink } from 'react-router-dom'
import MercuryLogo from './MercuryLogo'
import UserMenu from './UserMenu'

// The dark top bar from the original Mercury UI: logo, Ask / Contribute /
// Databloom / Feed, search, notifications, and the account menu.

const icon = { width: 20, height: 20, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true }

const NAV = [
  { to: '/', label: 'Ask', end: true, svg: <svg {...icon}><path d="M4 5h16v11H8l-4 4z" /></svg> },
  { to: '/contribute', label: 'Contribute', svg: <svg {...icon}><path d="M12 16V4m0 0-4 4m4-4 4 4M5 20h14" /></svg> },
  { to: '/databloom', label: 'Databloom', svg: <svg {...icon}><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 13 9 5 9-5" /></svg> },
  { to: '/feed', label: 'Feed', svg: <svg {...icon}><path d="M4 6h16M4 12h11M4 18h16" /></svg> },
]

const navClass = ({ isActive }) =>
  `relative flex items-center gap-2 rounded-xl px-4 py-2.5 text-[19px] font-semibold transition ${
    isActive
      ? 'bg-white/10 text-white after:absolute after:inset-x-1 after:-bottom-[3px] after:h-[3px] after:rounded-full after:bg-[#eab448]'
      : 'text-white/70 hover:bg-white/5 hover:text-white'
  }`

// onSearch: pass your own search handler if you had one (e.g. open your Ctrl+K dialog).
export default function AppHeader({ onSearch, notifications = 0, onNotifications }) {
  return (
    <header className="mercury mercury-band border-b border-white/10">
      <div className="mx-auto flex max-w-[1540px] flex-wrap items-center gap-x-8 gap-y-2 px-5 py-4">
        <MercuryLogo />
        <nav className="flex flex-wrap items-center gap-1" aria-label="Main">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={navClass}>
              {n.svg}
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-4">
          <button
            onClick={onSearch}
            className="hidden items-center gap-3 rounded-xl bg-[#0d1533]/45 px-4 py-3 text-[17px] text-white/70 ring-1 ring-white/10 hover:text-white md:flex"
          >
            <svg {...icon}><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4-4" /></svg>
            Search
            <kbd className="mercury-mono rounded-md bg-[#0d1533]/70 ring-1 ring-white/15 px-1.5 py-0.5 text-xs text-white/80">Ctrl K</kbd>
          </button>
          <button onClick={onNotifications} aria-label="Notifications" className="relative rounded-full p-2 text-white/80 hover:text-white">
            <svg {...icon} width="22" height="22"><path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15z" /><path d="M10 20a2 2 0 0 0 4 0" /></svg>
            {notifications > 0 && <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-[#eab448]" />}
          </button>
          <UserMenu />
        </div>
      </div>
    </header>
  )
}
