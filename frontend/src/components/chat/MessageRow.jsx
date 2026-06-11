import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { Badge } from "@/components/ui/badge";
import {
  Robot, User as UserIcon, Copy, ThumbsUp, ThumbsDown,
  Warning, CheckSquare, SealCheck, Trash,
} from "@phosphor-icons/react";
import MarkdownRenderer from "@/components/MarkdownRenderer";
import { SourceInner } from "./SourceCard";

export function MessageRow({ msg, onCopy, onFeedback, onFollowup, onAcknowledge, onDelete }) {
  if (msg.role === "user") {
    return (
      <div className="flex gap-3 group" data-testid="user-message">
        <div className="w-8 h-8 bg-blue-600 flex items-center justify-center shrink-0">
          <UserIcon size={16} weight="bold" className="text-white" />
        </div>
        <div className="flex-1 pt-1 min-w-0">
          <div className="flex items-center justify-between gap-2 mb-1">
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500">You</div>
            <button
              onClick={() => onDelete?.(msg.message_id)}
              data-testid={`delete-user-msg-${msg.message_id}`}
              className="p-0.5 text-slate-400 hover:text-rose-600 lg:opacity-0 lg:group-hover:opacity-100 transition-opacity"
              title="Delete this question and its reply"
              aria-label="Delete message"
            >
              <Trash size={12} weight="bold" />
            </button>
          </div>
          <div className="text-slate-800 whitespace-pre-wrap">{msg.content}</div>
          {msg.images?.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2" data-testid="user-msg-images">
              {msg.images.map((src, i) => (
                <a
                  key={`umi-${msg.message_id}-${i}`}
                  href={src}
                  target="_blank"
                  rel="noreferrer"
                  className="block border border-slate-300 hover:border-slate-500 transition-colors overflow-hidden"
                >
                  <img src={src} alt="attached" className="h-24 w-24 object-cover" draggable="false" />
                </a>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }
  return (
    <div className="flex gap-3" data-testid="assistant-message">
      <div className="w-8 h-8 bg-slate-900 flex items-center justify-center shrink-0">
        <Robot size={16} weight="bold" className="text-white" />
      </div>
      <div className="flex-1 pt-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500">CIDSA AI</div>
          {msg.is_high_risk && (
            <Badge data-testid="high-risk-badge" className="rounded-sm bg-rose-50 text-rose-800 border border-rose-300 hover:bg-rose-50 font-mono text-[10px] uppercase tracking-wider px-1.5 py-0">
              <Warning size={10} weight="bold" className="mr-0.5" />High Risk
            </Badge>
          )}
          {typeof msg.confidence_score === "number" && (
            <Badge data-testid="confidence-badge" className="rounded-sm bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-50 font-mono text-[10px] uppercase tracking-wider px-1.5 py-0">
              {(msg.confidence_score * 100).toFixed(0)}% match
            </Badge>
          )}
        </div>
        <MarkdownRenderer content={msg.content || ""} sources={msg.sources || []} />
        {msg._streaming && <span className="streaming-dot" data-testid="streaming-cursor"></span>}
        {msg.sources?.length > 0 && (
          <div className="mt-4 pt-3 border-t border-slate-200">
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-2">Citations</div>
            <div className="flex flex-wrap gap-1">
              {msg.sources.map((s, i) => (
                <HoverCard key={`${s.doc_id || "src"}-${i}`} openDelay={200}>
                  <HoverCardTrigger asChild>
                    <button
                      className="font-mono text-[10px] uppercase tracking-wider px-2 py-1 bg-slate-100 hover:bg-slate-900 hover:text-white border border-slate-200 transition-colors"
                      data-testid={`citation-${i}`}
                    >
                      [{i + 1}] {s.title.slice(0, 40)}{s.title.length > 40 ? "…" : ""}
                    </button>
                  </HoverCardTrigger>
                  <HoverCardContent className="w-96 p-4 rounded-sm border-slate-300 bg-white" side="top">
                    <SourceInner src={s} />
                  </HoverCardContent>
                </HoverCard>
              ))}
            </div>
          </div>
        )}
        {!msg._streaming && msg.content && (
          <div className="mt-3 flex items-center flex-wrap gap-1" data-testid="message-actions">
            <button
              onClick={() => onCopy?.(msg.content)}
              data-testid={`copy-msg-${msg.message_id}`}
              className="flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider px-2 py-1 border border-transparent hover:border-slate-200 hover:bg-slate-50 text-slate-500 hover:text-slate-800 transition-colors"
              title="Copy answer"
            >
              <Copy size={12} weight="bold" /> Copy
            </button>
            <button
              onClick={() => onFeedback?.(msg.message_id, "up")}
              data-testid={`thumbs-up-${msg.message_id}`}
              className={`flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider px-2 py-1 border transition-colors ${
                msg.feedback === "up"
                  ? "border-emerald-300 bg-emerald-50 text-emerald-700"
                  : "border-transparent hover:border-emerald-200 hover:bg-emerald-50 text-slate-500 hover:text-emerald-700"
              }`}
              title="Helpful"
            >
              <ThumbsUp size={12} weight={msg.feedback === "up" ? "fill" : "bold"} /> Helpful
            </button>
            <button
              onClick={() => onFeedback?.(msg.message_id, "down")}
              data-testid={`thumbs-down-${msg.message_id}`}
              className={`flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider px-2 py-1 border transition-colors ${
                msg.feedback === "down"
                  ? "border-rose-300 bg-rose-50 text-rose-700"
                  : "border-transparent hover:border-rose-200 hover:bg-rose-50 text-slate-500 hover:text-rose-700"
              }`}
              title="Flag for SME review"
            >
              <ThumbsDown size={12} weight={msg.feedback === "down" ? "fill" : "bold"} /> Flag
            </button>
            {msg.acknowledged_at ? (
              <span
                data-testid={`acknowledged-${msg.message_id}`}
                className="flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider px-2 py-1 border border-emerald-300 bg-emerald-50 text-emerald-800"
                title={`Acknowledged ${new Date(msg.acknowledged_at).toISOString().slice(0, 19).replace("T", " ")} UTC`}
              >
                <SealCheck size={12} weight="fill" /> Acknowledged
              </span>
            ) : (
              <button
                onClick={() => onAcknowledge?.(msg.message_id)}
                data-testid={`acknowledge-${msg.message_id}`}
                className={`flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider px-2 py-1 border transition-colors ${
                  msg.is_high_risk
                    ? "border-amber-400 bg-amber-50 text-amber-800 hover:bg-amber-100 animate-pulse"
                    : "border-transparent hover:border-blue-200 hover:bg-blue-50 text-slate-500 hover:text-blue-700"
                }`}
                title={msg.is_high_risk ? "High-risk procedure — acknowledgement strongly recommended for compliance" : "I understand and will follow this guidance"}
              >
                <CheckSquare size={12} weight="bold" /> {msg.is_high_risk ? "Acknowledge (required)" : "I understand"}
              </button>
            )}
            {!msg.acknowledged_at && (
              <button
                onClick={() => onDelete?.(msg.message_id)}
                data-testid={`delete-msg-${msg.message_id}`}
                className="flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider px-2 py-1 border border-transparent hover:border-rose-200 hover:bg-rose-50 text-slate-500 hover:text-rose-700 transition-colors ml-auto"
                title="Delete this Q&A pair"
              >
                <Trash size={12} weight="bold" /> Delete
              </button>
            )}
          </div>
        )}
        {!msg._streaming && msg.suggested_followups?.length > 0 && (
          <div className="mt-3" data-testid="followups">
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-2">Follow-up</div>
            <div className="flex flex-wrap gap-2">
              {msg.suggested_followups.map((q, i) => (
                <button
                  key={`fu-${i}-${(q || "").slice(0, 20)}`}
                  onClick={() => onFollowup?.(q)}
                  data-testid={`followup-${i}`}
                  className="text-left text-xs px-3 py-1.5 bg-white hover:bg-blue-50 hover:border-blue-300 text-slate-700 hover:text-blue-800 border border-slate-300 transition-colors"
                >
                  <span className="text-blue-600 mr-1">↗</span>{q}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
