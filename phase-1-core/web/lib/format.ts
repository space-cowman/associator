/** How long ago, in words. */
export function timeAgo(iso: string): string {
  const s = Math.max(1, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h}h`;
  const d = Math.round(h / 24);
  if (d < 60) return `${d}d`;
  return new Date(iso).toLocaleDateString();
}

/** A short vote count. */
export function score(t: { up: number; down: number }): number {
  return t.up - t.down;
}

/** A word with the right plural. */
export function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}
