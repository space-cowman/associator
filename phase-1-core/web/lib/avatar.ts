// A small, unique, symmetric pattern made from the handle: anonymous, no uploads, no network.
const PALETTE = ["#e8590c", "#1c7ed6", "#2f9e44", "#ae3ec9", "#f08c00", "#0c8599", "#d6336c", "#5c7cfa"];

/** A number from a handle. */
function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** The avatar pattern for a handle. */
export function avatarCells(handle: string): { color: string; cells: boolean[] } {
  const h = hash(handle);
  const color = PALETTE[h % PALETTE.length];
  const cells: boolean[] = [];
  for (let row = 0; row < 5; row++) {
    const left = [0, 1, 2].map((col) => ((h >> (row * 3 + col + 3)) & 1) === 1);
    cells.push(left[0], left[1], left[2], left[1], left[0]);
  }
  return { color, cells };
}
