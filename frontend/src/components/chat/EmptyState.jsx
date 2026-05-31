import { Sparkle } from "@phosphor-icons/react";
import { SUGGESTIONS } from "./constants";

export function EmptyState({ onPick }) {
  return (
    <div className="py-8 sm:py-12" data-testid="empty-state">
      <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-500 mb-3">AI co-pilot</div>
      <h1 className="text-3xl sm:text-4xl lg:text-5xl font-black tracking-tighter text-slate-900 mb-3 leading-[1.05]">
        What EHS question is on your mind?
      </h1>
      <p className="text-slate-600 text-sm sm:text-base mb-8 sm:mb-10 max-w-2xl">
        Ask anything about your safety procedures, permits, HAZOPs, incidents, OSHA standards, ISO requirements or chemical SDS data. I'll search your knowledge base and cite the source.
      </p>

      <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-500 mb-3">Try one of these</div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-px bg-slate-200">
        {SUGGESTIONS.map((q, i) => (
          <button
            key={i}
            onClick={() => onPick(q)}
            data-testid={`suggestion-${i}`}
            className="text-left bg-white p-3 sm:p-4 hover:bg-blue-50 hover:text-blue-900 transition-colors group flex items-start gap-3"
          >
            <Sparkle size={14} weight="bold" className="text-blue-600 mt-1 shrink-0" />
            <span className="text-sm font-medium leading-snug">{q}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
