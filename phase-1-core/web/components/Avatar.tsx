import { avatarCells } from "@/lib/avatar";

/** A person's generated avatar. */
export function Avatar({ handle, size = 22 }: { handle: string | null; size?: number }) {
  if (!handle) return <span className="avatar" style={{ width: size, height: size, background: "var(--line)" }} />;
  const { color, cells } = avatarCells(handle);
  return (
    <svg className="avatar" width={size} height={size} viewBox="0 0 5 5" aria-hidden="true" shapeRendering="crispEdges">
      <rect width="5" height="5" fill={color} opacity="0.16" />
      {cells.map((on, i) => (on ? <rect key={i} x={i % 5} y={Math.floor(i / 5)} width="1" height="1" fill={color} /> : null))}
    </svg>
  );
}
