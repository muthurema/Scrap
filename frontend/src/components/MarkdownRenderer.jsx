import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Renders assistant markdown, replacing [1], [2] citation markers with chips
 * that scroll to the corresponding source citation pill (rendered by parent).
 */
export default function MarkdownRenderer({ content, sources = [] }) {
  // Preprocess: replace [1], [2], etc with placeholder span
  // We inject HTML spans, but react-markdown won't render raw HTML by default.
  // Simpler: pass through markdown, transform inline [n] in text nodes via components.

  return (
    <div className="prose-ehs" data-testid="markdown-content">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p>{transformCitations(children, sources)}</p>,
          li: ({ children }) => <li>{transformCitations(children, sources)}</li>,
          // Tables
          table: ({ children }) => <div className="overflow-x-auto my-3"><table className="w-full border-collapse border border-slate-300 text-sm">{children}</table></div>,
          th: ({ children }) => <th className="border border-slate-300 bg-slate-100 px-2 py-1 text-left font-semibold">{children}</th>,
          td: ({ children }) => <td className="border border-slate-300 px-2 py-1">{children}</td>,
          a: ({ href, children }) => <a href={href} className="text-blue-600 underline underline-offset-2" target="_blank" rel="noreferrer">{children}</a>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

function transformCitations(children, sources) {
  if (!Array.isArray(children)) children = [children];
  return children.map((child, idx) => {
    if (typeof child !== "string") return child;
    const parts = child.split(/(\[\d+\])/g);
    return parts.map((p, i) => {
      const m = p.match(/^\[(\d+)\]$/);
      if (m) {
        const n = parseInt(m[1], 10);
        const exists = n >= 1 && n <= sources.length;
        return (
          <span
            key={`${idx}-${i}`}
            className={`citation-chip${exists ? "" : " opacity-60"}`}
            title={exists ? sources[n - 1].title : "Unknown citation"}
            data-testid={`inline-citation-${n}`}
          >
            {n}
          </span>
        );
      }
      return <span key={`${idx}-${i}`}>{p}</span>;
    });
  });
}
