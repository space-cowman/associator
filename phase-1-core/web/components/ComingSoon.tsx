import { Shell } from "./Shell";

/** Placeholder for a destination that is designed but not built yet. */
export function ComingSoon({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Shell>
      <div className="card pad soon-card rise">
        <h1 className="page-title">{title}</h1>
        {children}
        <span className="pill">Coming soon</span>
      </div>
    </Shell>
  );
}
