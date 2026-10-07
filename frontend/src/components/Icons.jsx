function Svg({ size = 18, strokeWidth = 1.8, className, children }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {children}
    </svg>
  );
}

export const ChatIcon = (p) => <Svg {...p}><path d="M4 5h16v11H9l-5 4z" /></Svg>;
export const UploadIcon = (p) => <Svg {...p}><path d="M12 16V4M7 9l5-5 5 5M4 20h16" /></Svg>;
export const LayersIcon = (p) => <Svg {...p}><path d="M12 3l9 5-9 5-9-5zM3 13l9 5 9-5" /></Svg>;
export const ListIcon = (p) => <Svg {...p}><path d="M4 6h16M4 12h16M4 18h10" /></Svg>;
export const SearchIcon = (p) => <Svg {...p}><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></Svg>;
export const BellIcon = (p) => <Svg {...p}><path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4zM10 21h4" /></Svg>;
export const ArrowUpIcon = (p) => <Svg {...p}><path d="M12 19V5M5 12l7-7 7 7" /></Svg>;
export const ArrowDownIcon = (p) => <Svg {...p}><path d="M12 5v14M5 12l7 7 7-7" /></Svg>;
export const ChevronUpIcon = (p) => <Svg {...p}><path d="M6 15l6-6 6 6" /></Svg>;
export const ChevronDownIcon = (p) => <Svg {...p}><path d="M6 9l6 6 6-6" /></Svg>;
export const CheckIcon = (p) => <Svg {...p}><path d="M5 12l5 5 9-10" /></Svg>;
export const XIcon = (p) => <Svg {...p}><path d="M6 6l12 12M18 6L6 18" /></Svg>;
export const FileIcon = (p) => <Svg {...p}><path d="M14 3H6v18h12V7zM14 3v4h4" /></Svg>;
export const CodeIcon = (p) => <Svg {...p}><path d="M8 7l-5 5 5 5M16 7l5 5-5 5" /></Svg>;
export const LinkIcon = (p) => (
  <Svg {...p}><path d="M10 14a4 4 0 0 0 6 0l3-3a4 4 0 0 0-6-6l-1 1M14 10a4 4 0 0 0-6 0l-3 3a4 4 0 0 0 6 6l1-1" /></Svg>
);
export const SparkIcon = (p) => (
  <Svg {...p}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M6 18l2.5-2.5M15.5 8.5L18 6" /></Svg>
);

export function Logo({ size = 30, ring = '#F2B544', planet = '#D9DEE7' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 30 30" aria-hidden="true">
      <ellipse cx="15" cy="15" rx="13.5" ry="5.5" fill="none" stroke={ring} strokeWidth="1.5" transform="rotate(-24 15 15)" />
      <circle cx="15" cy="15" r="7" fill={planet} />
      <circle cx="12.6" cy="12.6" r="2.2" fill="#FFFFFF" fillOpacity="0.75" />
    </svg>
  );
}
