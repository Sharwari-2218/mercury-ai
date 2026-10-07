// Pill-style toggle group. tone="dark" sits on the blue header, tone="light" on white cards.
export default function Segmented({ label, options, value, onChange, tone = 'dark' }) {
  const wrap = tone === 'dark' ? 'border border-panel-line bg-panel/70' : 'bg-chip';
  const on = tone === 'dark' ? 'bg-paper text-navy-900' : 'bg-ombre-soft text-white';
  const off = tone === 'dark' ? 'text-[#C9D0DC] hover:text-white' : 'text-body hover:text-ink';

  return (
    <div role="group" aria-label={label} className={`flex w-fit max-w-full flex-wrap gap-1 rounded-xl p-1 ${wrap}`}>
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(o.value)}
            className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-[9px] px-5 text-sm font-semibold transition-colors ${active ? on : off}`}
          >
            {o.icon}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
