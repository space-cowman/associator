// Small inline icons (no icon font, no network).
type P = { size?: number };
/** Shared icon settings. */
const base = (size: number) => ({
  width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
  strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true,
});

/** Search icon. */
export const SearchIcon = ({ size = 16 }: P) => (<svg {...base(size)}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>);
/** Up vote icon. */
export const UpIcon = ({ size = 18 }: P) => (<svg {...base(size)}><path d="M12 5 5 13h4v6h6v-6h4z" /></svg>);
/** Down vote icon. */
export const DownIcon = ({ size = 18 }: P) => (<svg {...base(size)}><path d="M12 19 5 11h4V5h6v6h4z" /></svg>);
/** Reply icon. */
export const ReplyIcon = ({ size = 16 }: P) => (<svg {...base(size)}><path d="M21 12a8 8 0 0 1-11.5 7.2L4 20l1-4.6A8 8 0 1 1 21 12z" /></svg>);
/** Inbox icon. */
export const InboxIcon = ({ size = 19 }: P) => (<svg {...base(size)}><path d="M3 13h5l2 3h4l2-3h5" /><path d="M5 5h14l2 8v6H3v-6z" /></svg>);
/** Light theme icon. */
export const SunIcon = ({ size = 18 }: P) => (<svg {...base(size)}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>);
/** Dark theme icon. */
export const MoonIcon = ({ size = 18 }: P) => (<svg {...base(size)}><path d="M21 13A9 9 0 1 1 11 3a7 7 0 0 0 10 10z" /></svg>);
/** Menu icon. */
export const MenuIcon = ({ size = 20 }: P) => (<svg {...base(size)}><path d="M4 6h16M4 12h16M4 18h16" /></svg>);
/** Check icon. */
export const CheckIcon = ({ size = 15 }: P) => (<svg {...base(size)}><path d="m5 12 5 5 9-10" /></svg>);
/** AI icon. */
export const BotIcon = ({ size = 13 }: P) => (<svg {...base(size)}><rect x="5" y="8" width="14" height="11" rx="3" /><path d="M12 4v4M9 13h.01M15 13h.01" /></svg>);
/** Copy icon. */
export const CopyIcon = ({ size = 14 }: P) => (<svg {...base(size)}><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3" /></svg>);
/** Plus icon. */
export const PlusIcon = ({ size = 16 }: P) => (<svg {...base(size)}><path d="M12 5v14M5 12h14" /></svg>);
/** Home icon. */
export const HomeIcon = ({ size = 17 }: P) => (<svg {...base(size)}><path d="m3 11 9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" /></svg>);
/** Spark icon. */
export const SparkIcon = ({ size = 15 }: P) => (<svg {...base(size)}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6" /></svg>);
/** Warning icon. */
export const WarnIcon = ({ size = 14 }: P) => (<svg {...base(size)}><path d="M12 3 2 20h20z" /><path d="M12 10v4M12 17h.01" /></svg>);
/** Info icon. */
export const InfoIcon = ({ size = 19 }: P) => (<svg {...base(size)}><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></svg>);
/** More icon. */
export const MoreIcon = ({ size = 19 }: P) => (<svg {...base(size)}><circle cx="6" cy="12" r="1.3" fill="currentColor" /><circle cx="12" cy="12" r="1.3" fill="currentColor" /><circle cx="18" cy="12" r="1.3" fill="currentColor" /></svg>);
/** Back icon. */
export const BackIcon = ({ size = 20 }: P) => (<svg {...base(size)}><path d="m15 5-7 7 7 7" /></svg>);
/** Close icon. */
export const CloseIcon = ({ size = 18 }: P) => (<svg {...base(size)}><path d="M6 6l12 12M18 6 6 18" /></svg>);
/** Lock icon. */
export const LockIcon = ({ size = 11 }: P) => (<svg {...base(size)}><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></svg>);
/** Send icon. */
export const SendIcon = ({ size = 17 }: P) => (<svg {...base(size)} strokeWidth={2.4}><path d="M12 19V5M6 11l6-6 6 6" /></svg>);
/** Attach icon. */
export const PaperclipIcon = ({ size = 17 }: P) => (<svg {...base(size)}><path d="m20 11-8.5 8.5a5 5 0 0 1-7-7L13 4a3.5 3.5 0 0 1 5 5l-8.5 8.5a2 2 0 0 1-3-3L14 7" /></svg>);
/** Report icon. */
export const FlagIcon = ({ size = 15 }: P) => (<svg {...base(size)}><path d="M5 21V4M5 4h11l-2 4 2 4H5" /></svg>);
