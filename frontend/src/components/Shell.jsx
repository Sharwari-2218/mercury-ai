import Navbar from './NavBar';

// Page frame: blue ombre header (navbar + page intro), then content that overlaps it by 64px.
export default function Shell({ eyebrow, title, description, headerExtra, headerAside, children }) {
  return (
    <div className="min-h-screen bg-paper">
      <header className="bg-ombre text-[#F4F1EA]">
        <Navbar />
        <div className="border-t border-white/10">
          <div className="mx-auto flex max-w-[1240px] flex-wrap items-end justify-between gap-5 px-6 pb-26 pt-10">
            <div className="flex flex-col gap-4">
              <span className="text-xs font-bold uppercase tracking-[0.14em] text-amber">{eyebrow}</span>
              <h1 className="max-w-[640px] text-[38px] font-bold leading-tight tracking-[-0.03em] text-white">{title}</h1>
              <p className="max-w-[560px] text-base leading-relaxed text-mist">{description}</p>
              {headerExtra}
            </div>
            {headerAside}
          </div>
        </div>
      </header>
      <main className="relative mx-auto -mt-16 max-w-[1240px] px-6 pb-14">{children}</main>
    </div>
  );
}

export const card = 'rounded-[18px] border border-line bg-white shadow-[0_12px_32px_rgba(18,26,43,0.10)]';
