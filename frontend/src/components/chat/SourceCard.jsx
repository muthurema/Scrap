import { DOC_TYPE_LABELS, SOURCE_LABELS } from "./constants";

export function SourceCard({ index, src }) {
  const label = SOURCE_LABELS[src.source] || { text: src.source, color: "bg-slate-700 text-white" };
  const lu = src.last_updated ? new Date(src.last_updated) : null;
  return (
    <div className="bg-white border border-slate-200 hover:border-slate-400 transition-colors p-3 group" data-testid={`source-card-${index}`}>
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500">[{String(index).padStart(2, "0")}]</div>
        <div className="font-mono text-[10px] uppercase tracking-wider text-emerald-700">
          {(src.similarity_score * 100).toFixed(0)}%
        </div>
      </div>
      <div className="font-semibold text-sm leading-tight text-slate-900 mb-2 line-clamp-2">{src.title}</div>
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
    </div>
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
      <div className="font-semibold text-sm text-slate-900 mb-2">{src.title}</div>
      <div className="text-xs text-slate-600 leading-relaxed max-h-48 overflow-y-auto">{src.chunk_text}</div>
      {lu && !isNaN(lu) && (
        <div className="font-mono text-[9px] uppercase tracking-wider text-slate-400 mt-2">
          As of {lu.toISOString().slice(0, 10)}
        </div>
      )}
    </div>
  );
}
