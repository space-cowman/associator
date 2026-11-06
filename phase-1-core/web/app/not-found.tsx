import Link from "next/link";

/** The page shown for a wrong address. */
export default function NotFound() {
  return (
    <div className="shell" style={{ gridTemplateColumns: "1fr" }}>
      <div className="card empty"><div className="big">Page not found</div><Link href="/" className="hint">Back to all clusters</Link></div>
    </div>
  );
}
