import { DOC_TYPE_LABELS, SOURCE_LABELS } from "./constants";

export function SourceCard({ index, src, onOpen }) {
  const label = SOURCE_LABELS[src.source] || { text: src.source, color: "bg-slate-700 text-white" };
  const lu = src.last_updated ? new Date(src.last_updated) : null;
  const clickable = !!(onOpen && src.doc_id);
  const Tag = clickable ? "button" : "div";
  return (
    <Tag
      type={clickable ? "button" : undefined}
      onClick={clickable ? onOpen : undefined}
      className={
        "block w-full text-left bg-white border border-slate-200 p-3 group transition-colors " +
        (clickable
          ? "hover:border-slate-900 hover:bg-slate-50 cursor-pointer focus:outline-none focus:ring-2 focus:ring-slate-900"
          : "hover:border-slate-400")
      }
      data-testid={`source-card-${index}`}
      aria-label={clickable ? `Open source ${src.title}` : undefined}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500">[{String(index).padStart(2, "0")}]</div>
        <div className="font-mono text-[10px] uppercase tracking-wider text-emerald-700">
          {(src.similarity_score * 100).toFixed(0)}%
        </div>
      </div>
      <div className="font-semibold text-sm leading-tight text-slate-900 mb-1 line-clamp-2 group-hover:underline group-hover:decoration-slate-900 group-hover:underline-offset-2">{src.title}</div>
      {src.author && (
        <div className="text-[11px] text-slate-500 italic mb-2 truncate" data-testid={`source-author-${index}`}>by {src.author}</div>
      )}
      <div className="flex flex-wrap gap-1 mb-2">
        <span className={`text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 ${label.color}`}>{label.text}</span>
        <span className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 bg-slate-100 border border-slate-200 text-slate-700">
          {DOC_TYPE_LABELS[src.doc_type] || src.doc_type}
        </span>
        {src.jurisdiction && (
          <span className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 bg-blue-50 border border-blue-200 text-blue-800">
            {src.jurisdiction}
          </span>
        )}
      </div>
      <div className="text-xs text-slate-600 line-clamp-3 leading-snug mb-1.5">{src.chunk_text}</div>
      {lu && !isNaN(lu) && (
        <div className="font-mono text-[9px] uppercase tracking-wider text-slate-400">
          Updated {lu.toISOString().slice(0, 10)}
        </div>
      )}
      {clickable && (
        <div className="font-mono text-[9px] uppercase tracking-wider text-slate-500 mt-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
          ⌕ Click to open
        </div>
      )}
    </Tag>
  );
}

export function SourceInner({ src }) {
  const label = SOURCE_LABELS[src.source] || { text: src.source, color: "bg-slate-700 text-white" };
  const lu = src.last_updated ? new Date(src.last_updated) : null;
  return (
    <div>
      <div className="flex flex-wrap gap-1 mb-2">
        <span className={`text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 ${label.color}`}>{label.text}</span>
        <span className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 bg-slate-100 border border-slate-200 text-slate-700">
          {DOC_TYPE_LABELS[src.doc_type] || src.doc_type}
        </span>
        {src.jurisdiction && (
          <span className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 bg-blue-50 border border-blue-200 text-blue-800">
            {src.jurisdiction}
          </span>
        )}
        <span className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 bg-emerald-50 border border-emerald-200 text-emerald-700">
          {(src.similarity_score * 100).toFixed(0)}% match
        </span>
      </div>
      <div className="font-semibold text-sm text-slate-900 mb-1">{src.title}</div>
      {src.author && <div className="text-[11px] text-slate-500 italic mb-2">by {src.author}</div>}
      <div className="text-xs text-slate-600 leading-relaxed max-h-48 overflow-y-auto">{src.chunk_text}</div>
      {lu && !isNaN(lu) && (
        <div className="font-mono text-[9px] uppercase tracking-wider text-slate-400 mt-2">
          As of {lu.toISOString().slice(0, 10)}
        </div>
      )}
    </div>
  );
}
