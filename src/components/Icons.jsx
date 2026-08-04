const paths = {
  overview: <><path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v10h13V10M9 20v-6h6v6"/></>,
  research: <><circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5M8 13l2-2 2 1 3-4"/></>,
  search: <><circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/></>,
  portfolio: <><rect x="3" y="6" width="18" height="14" rx="3"/><path d="M8 6V4h8v2M3 11h18M8 15h3"/></>,
  watchlist: <path d="M12 20s-7-4.35-7-10a4 4 0 0 1 7-2.65A4 4 0 0 1 19 10c0 5.65-7 10-7 10Z"/>,
  more: <><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/></>,
  market: <><path d="M4 19V9M10 19V5M16 19v-7M22 19V3"/><path d="M2 19h21"/></>,
  finances: <><circle cx="12" cy="12" r="9"/><path d="M12 7v10M9.5 15c0 1.1 1.1 2 2.5 2s2.5-.8 2.5-2c0-2.5-5-1.5-5-4 0-1.2 1.1-2 2.5-2s2.5.9 2.5 2"/></>,
  method: <><path d="M5 4h14v16H5z"/><path d="M8 8h8M8 12h8M8 16h5"/></>,
  bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/></>,
  arrow: <><path d="M5 12h14M14 7l5 5-5 5"/></>,
  chevron: <path d="m9 6 6 6-6 6"/>,
  plus: <path d="M12 5v14M5 12h14"/>,
  moon: <path d="M20 15.5A8 8 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z"/>,
  sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41"/></>,
  logout: <><path d="M10 5H5v14h5M14 8l4 4-4 4M18 12H9"/></>,
  close: <path d="m6 6 12 12M18 6 6 18"/>,
  sync: <><path d="M20 7h-5V2"/><path d="M20 7a8 8 0 1 0 1 8"/></>,
  download: <><path d="M12 3v12M7 10l5 5 5-5"/><path d="M5 21h14"/></>,
  user: <><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56V21h-4v-.09A1.7 1.7 0 0 0 8.94 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.57 15 1.7 1.7 0 0 0 3 14H3v-4h.09A1.7 1.7 0 0 0 4.6 8.94a1.7 1.7 0 0 0-.34-1.88L4.2 7l2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.57 1.7 1.7 0 0 0 10 3h4v.09A1.7 1.7 0 0 0 15.06 4.6a1.7 1.7 0 0 0 1.88-.34L17 4.2 19.83 7l-.06.06A1.7 1.7 0 0 0 19.43 9 1.7 1.7 0 0 0 21 10h.09v4H21a1.7 1.7 0 0 0-1.6 1Z"/></>,
  eye: <><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="2.5"/></>,
  'eye-off': <><path d="m3 3 18 18M10.6 6.2A11 11 0 0 1 12 6c6.5 0 10 6 10 6a17 17 0 0 1-2 2.6M6.5 6.5C3.6 8.3 2 12 2 12s3.5 6 10 6c1.5 0 2.8-.3 4-.8M10 10a2.8 2.8 0 0 0 4 4"/></>,
  grip: <><circle cx="9" cy="7" r=".7"/><circle cx="15" cy="7" r=".7"/><circle cx="9" cy="12" r=".7"/><circle cx="15" cy="12" r=".7"/><circle cx="9" cy="17" r=".7"/><circle cx="15" cy="17" r=".7"/></>,
  up: <path d="m6 15 6-6 6 6"/>,
  down: <path d="m6 9 6 6 6-6"/>,
  accessibility: <><circle cx="12" cy="4" r="2"/><path d="M4 8h16M12 6v15M8 21l4-8 4 8"/></>,
  glossary: <><path d="M6 4h11a2 2 0 0 1 2 2v14H8a2 2 0 0 1-2-2z"/><path d="M6 4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2"/><path d="M9 8h7M9 11.5h7"/></>,
}

export default function Icon({ name, size = 20, className = '', ...props }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"
      strokeLinejoin="round" aria-hidden="true" focusable="false" {...props}>
      {paths[name] || paths.more}
    </svg>
  )
}
