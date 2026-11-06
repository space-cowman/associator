// Renders the post format (a small Markdown subset) as React elements.
import type { ReactNode } from "react";

const INLINE = /(`[^`\n]+`|\*\*[^*\n]+\*\*|~~[^~\n]+~~|\*[^*\n]+\*|_[^_\n]+_|\[[^\]\n]+\]\(https?:\/\/[^\s)]+\)|https?:\/\/[^\s<]+[^\s<.,;:!?)\]'"])/g;

/** Format bold, italic, code and links. */
function inline(text: string, key: string): ReactNode[] {
  return text.split(INLINE).map((part, i) => {
    const k = `${key}-${i}`;
    if (!part) return null;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) return <code key={k} className="ic">{part.slice(1, -1)}</code>;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) return <strong key={k}>{inline(part.slice(2, -2), k)}</strong>;
    if (part.startsWith("~~") && part.endsWith("~~") && part.length > 4) return <del key={k}>{inline(part.slice(2, -2), k)}</del>;
    if ((part.startsWith("*") && part.endsWith("*")) || (part.startsWith("_") && part.endsWith("_"))) {
      if (part.length > 2) return <em key={k}>{inline(part.slice(1, -1), k)}</em>;
    }
    const link = /^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/.exec(part);
    if (link) return <a key={k} href={link[2]} target="_blank" rel="noopener noreferrer nofollow ugc" className="link">{link[1]}</a>;
    if (/^https?:\/\//.test(part)) return <a key={k} href={part} target="_blank" rel="noopener noreferrer nofollow ugc" className="link">{part}</a>;
    return part;
  });
}

/** Split text into paragraphs, lists and code blocks. */
function paragraphs(text: string, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  const lines = text.split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const bullet = /^\s*[-*]\s+(.*)$/;
    const number = /^\s*\d+[.)]\s+(.*)$/;
    if (bullet.test(line) || number.test(line)) {
      const ordered = number.test(line);
      const re = ordered ? number : bullet;
      const items: ReactNode[] = [];
      while (i < lines.length && re.test(lines[i])) {
        items.push(<li key={`${key}-li-${i}`}>{inline(re.exec(lines[i])![1], `${key}-${i}`)}</li>);
        i++;
      }
      out.push(ordered ? <ol key={`${key}-ol-${i}`}>{items}</ol> : <ul key={`${key}-ul-${i}`}>{items}</ul>);
      continue;
    }
    if (line.trim() === "") {
      i++;
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() !== "" && !bullet.test(lines[i]) && !number.test(lines[i])) {
      para.push(lines[i]);
      i++;
    }
    out.push(
      <p key={`${key}-p-${i}`}>
        {para.flatMap((l, j) => (j ? [<br key={`${key}-br-${i}-${j}`} />, ...inline(l, `${key}-${i}-${j}`)] : inline(l, `${key}-${i}-${j}`)))}
      </p>,
    );
  }
  return out;
}

/** Formatted post text. */
export function RichText({ text, className = "" }: { text: string; className?: string }) {
  const parts = text.split(/```[^\n`]*\n?([\s\S]*?)```/g);
  return (
    <div className={`rich ${className}`}>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <pre key={i} className="code"><code>{part.replace(/\n$/, "")}</code></pre>
        ) : (
          paragraphs(part, `s${i}`)
        ),
      )}
    </div>
  );
}
