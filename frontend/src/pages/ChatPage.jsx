import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { Separator } from "@/components/ui/separator";
import { toast } from "sonner";
import {
  PaperPlaneTilt, Plus, ChatCircle, ShieldCheck, SignOut, Trash,
  Books, GearSix, FileText, Robot, User as UserIcon, Sparkle,
  Copy, ThumbsUp, ThumbsDown, Warning, CalendarBlank, CheckSquare, SealCheck,
} from "@phosphor-icons/react";
import MarkdownRenderer from "@/components/MarkdownRenderer";
import { createTypewriter } from "@/lib/typewriter";

const SUGGESTIONS = [
  "What are the OSHA requirements for confined space entry?",
  "Walk me through a hot work permit procedure.",
  "Explain the lockout/tagout 6-step procedure.",
  "How do I conduct a Job Safety Analysis?",
  "What goes into a proper incident root cause analysis?",
];

const DOC_TYPE_LABELS = {
  sop: "SOP", incident_report: "Incident", risk_assessment: "Risk / HAZOP",
  regulatory: "Regulatory", training: "Training", permit: "Permit",
  policy: "Policy", msds: "MSDS / SDS", general: "General",
};

const SOURCE_LABELS = {
  superadmin: { text: "Company", color: "bg-blue-600 text-white" },
  turnstile_dms: { text: "Turnstile DMS", color: "bg-indigo-600 text-white" },
  base_corpus: { text: "Base Corpus", color: "bg-slate-700 text-white" },
  client_web: { text: "Client Web", color: "bg-emerald-600 text-white" },
  platform_web: { text: "Platform Web", color: "bg-amber-500 text-slate-900" },
};

export default function ChatPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const [sessions, setSessions] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [activeSources, setActiveSources] = useState([]);
  const messagesEndRef = useRef(null);

  const loadSessions = async () => {
    try {
      const { data } = await api.get("/chat/sessions");
      setSessions(data);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => { loadSessions(); }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const loadSession = async (sid) => {
    setCurrentSessionId(sid);
    try {
      const { data } = await api.get(`/chat/sessions/${sid}/messages`);
      setMessages(data);
      const last = [...data].reverse().find((m) => m.role === "assistant");
      setActiveSources(last?.sources || []);
    } catch (e) {
      toast.error("Failed to load session");
    }
  };

  const startNew = () => {
    setCurrentSessionId(null);
    setMessages([]);
    setActiveSources([]);
    setInput("");
  };

  const send = async (content) => {
    const text = (content ?? input).trim();
    if (!text || sending) return;
    setSending(true);
    setActiveSources([]);

    const tempUserId = "user-" + Date.now();
    let tempAsstId = "asst-" + Date.now();
    const tempUserMsg = {
      message_id: tempUserId,
      session_id: currentSessionId || "new",
      role: "user", content: text, sources: [], confidence_score: null,
      created_at: new Date().toISOString(),
    };
    const tempAsstMsg = {
      message_id: tempAsstId,
      session_id: currentSessionId || "new",
      role: "assistant", content: "", sources: [], confidence_score: null,
      created_at: new Date().toISOString(),
      _streaming: true,
    };
    setMessages((m) => [...m, tempUserMsg, tempAsstMsg]);
    setInput("");

    const token = localStorage.getItem("ehs_token");
    const url = `${process.env.REACT_APP_BACKEND_URL}/api/chat/stream`;
    let buffer = "";
    let streamedText = "";
    let streamedSources = [];
    let confidence = null;
    let newSessionId = currentSessionId;

    // Typewriter — gracefully drains backend bursts at ~60 chars/sec
    const typewriter = createTypewriter({
      rate: 80,
      maxBurst: 5,
      onUpdate: (text) => {
        setMessages((prev) => prev.map((m) =>
          m.message_id === tempAsstId ? { ...m, content: text } : m,
        ));
      },
    });

    try {
      const resp = await fetch(url, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json",
          "Accept": "text/event-stream",
        },
        body: JSON.stringify({ content: text, session_id: currentSessionId }),
      });
      if (!resp.ok || !resp.body) {
        const err = await resp.text();
        throw new Error(err || `HTTP ${resp.status}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();

      const handleEvent = (eventType, dataStr) => {
        let data;
        try { data = JSON.parse(dataStr); } catch { data = dataStr; }
        if (eventType === "session") {
          newSessionId = data.session_id;
          setCurrentSessionId(data.session_id);
          // Swap the temp assistant message_id with the server-issued one so feedback POSTs hit the real id
          if (data.message_id) {
            setMessages((prev) => prev.map((m) =>
              m.message_id === tempAsstId ? { ...m, message_id: data.message_id } : m,
            ));
            tempAsstId = data.message_id;
          }
        } else if (eventType === "sources") {
          streamedSources = data;
          setActiveSources(data);
          setMessages((prev) => prev.map((m) =>
            m.message_id === tempAsstId ? { ...m, sources: data } : m,
          ));
        } else if (eventType === "token") {
          const t = typeof data === "string" ? data : String(data);
          typewriter.append(t);
        } else if (eventType === "done") {
          confidence = data?.confidence_score ?? null;
          typewriter.forceComplete();
          setMessages((prev) => prev.map((m) =>
            m.message_id === tempAsstId
              ? {
                  ...m,
                  content: data?.final_text || typewriter.getRevealed(),
                  confidence_score: confidence,
                  is_high_risk: !!data?.is_high_risk,
                  suggested_followups: data?.suggested_followups || [],
                  _streaming: false,
                }
              : m,
          ));
        } else if (eventType === "error") {
          throw new Error(data?.message || "Stream error");
        }
      };

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";
        for (const blk of events) {
          if (!blk.trim()) continue;
          const lines = blk.split("\n");
          let eventType = "message";
          let dataLines = [];
          for (const ln of lines) {
            if (ln.startsWith("event:")) eventType = ln.slice(6).trim();
            else if (ln.startsWith("data:")) dataLines.push(ln.slice(5).trim());
          }
          if (dataLines.length) handleEvent(eventType, dataLines.join("\n"));
        }
      }
      loadSessions();
    } catch (e) {
      toast.error(e?.message || "Chat failed");
      setMessages((prev) => prev.filter((m) => m.message_id !== tempAsstId && m.message_id !== tempUserId));
    } finally {
      try { await typewriter.flush(); } catch {}
      typewriter.dispose();
      setSending(false);
    }
  };

  const deleteSession = async (sid, e) => {
    e.stopPropagation();
    if (!confirm("Delete this session?")) return;
    try {
      await api.delete(`/chat/sessions/${sid}`);
      if (sid === currentSessionId) startNew();
      loadSessions();
    } catch {
      toast.error("Delete failed");
    }
  };

  const submitFeedback = async (messageId, rating) => {
    try {
      await api.post(`/feedback/${messageId}`, { rating });
      setMessages((prev) => prev.map((m) =>
        m.message_id === messageId ? { ...m, feedback: rating } : m,
      ));
      toast.success(rating === "up" ? "Thanks for the feedback" : "Flagged — your safety team will review");
    } catch (e) {
      toast.error("Couldn't save feedback");
    }
  };

  const copyMessage = (text) => {
    navigator.clipboard.writeText(text || "")
      .then(() => toast.success("Copied"))
      .catch(() => toast.error("Copy failed"));
  };

  const acknowledgeMessage = async (messageId) => {
    try {
      const { data } = await api.post("/acknowledgements/", { message_id: messageId });
      setMessages((prev) => prev.map((m) =>
        m.message_id === messageId ? { ...m, acknowledged_at: data.acknowledged_at || new Date().toISOString() } : m,
      ));
      toast.success(data.already ? "Already acknowledged" : "Acknowledgement recorded — entered in compliance audit trail");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't record acknowledgement");
    }
  };

  const isEmpty = messages.length === 0;

  return (
    <div className="h-screen flex bg-slate-50 text-slate-900">
      {/* SIDEBAR */}
      <aside className="w-[260px] border-r border-slate-200 bg-white flex flex-col" data-testid="chat-sidebar">
        <div className="p-4 border-b border-slate-200">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-7 h-7 bg-slate-900 flex items-center justify-center">
              <ShieldCheck size={16} weight="bold" className="text-white" />
            </div>
            <div className="font-bold tracking-tight text-slate-900">EHS Intelligence</div>
          </div>
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500">Turnstile360 RAG</div>
        </div>

        <div className="p-3">
          <Button
            onClick={startNew}
            data-testid="new-chat-btn"
            className="w-full rounded-sm bg-slate-900 hover:bg-slate-800 text-white font-semibold tracking-tight h-10"
          >
            <Plus size={16} weight="bold" />
            <span className="ml-2">NEW CHAT</span>
          </Button>
        </div>

        <div className="px-3 pb-1">
          <div className="font-mono text-[10px] uppercase tracking-[0.25em] text-slate-500 px-1">Recent</div>
        </div>
        <ScrollArea className="flex-1 px-2">
          <div className="space-y-px pb-2">
            {sessions.length === 0 && (
              <div className="px-3 py-4 text-xs text-slate-500 font-mono">// No conversations yet</div>
            )}
            {sessions.map((s) => (
              <div
                key={s.id}
                role="button"
                tabIndex={0}
                onClick={() => loadSession(s.id)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); loadSession(s.id); } }}
                data-testid={`session-${s.id}`}
                className={`w-full text-left px-3 py-2 border border-transparent hover:border-slate-200 hover:bg-slate-50 group transition-colors cursor-pointer ${
                  currentSessionId === s.id ? "bg-slate-100 border-slate-200" : ""
                }`}
              >
                <div className="flex items-center gap-2">
                  <ChatCircle size={14} className="text-slate-400 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate text-slate-800">{s.title || "Untitled"}</div>
                    <div className="font-mono text-[10px] text-slate-400 uppercase tracking-wider">
                      {s.message_count} msgs
                    </div>
                  </div>
                  <button
                    onClick={(e) => deleteSession(s.id, e)}
                    className="opacity-0 group-hover:opacity-100 hover:text-rose-600 transition-opacity"
                    data-testid={`delete-session-${s.id}`}
                  >
                    <Trash size={13} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </ScrollArea>

        <div className="border-t border-slate-200 p-3 space-y-1">
          {user?.role === "superadmin" && (
            <button
              onClick={() => navigate("/admin/stats")}
              data-testid="goto-admin-btn"
              className="w-full flex items-center gap-2 px-3 py-2 hover:bg-slate-50 border border-transparent hover:border-slate-200 text-sm transition-colors"
            >
              <GearSix size={14} className="text-slate-600" />
              <span className="font-medium">Admin Panel</span>
            </button>
          )}
          <div className="flex items-center gap-2 px-3 py-2">
            <div className="w-7 h-7 bg-slate-100 border border-slate-200 flex items-center justify-center">
              <UserIcon size={14} weight="bold" className="text-slate-600" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium truncate">{user?.full_name || user?.email}</div>
              <div className="font-mono text-[9px] text-slate-500 uppercase tracking-wider">{user?.role}</div>
            </div>
            <button
              onClick={() => { logout(); navigate("/login"); }}
              data-testid="logout-btn"
              className="text-slate-400 hover:text-rose-600 transition-colors"
              title="Sign out"
            >
              <SignOut size={15} />
            </button>
          </div>
        </div>
      </aside>

      {/* MAIN */}
      <main className="flex-1 flex flex-col min-w-0">
        <header className="h-14 border-b border-slate-200 bg-white px-6 flex items-center justify-between" data-testid="chat-header">
          <div className="flex items-center gap-3">
            <div className="font-mono text-[10px] uppercase tracking-[0.25em] text-slate-500">// Session</div>
            <div className="text-sm font-medium text-slate-800 truncate max-w-md">
              {sessions.find((s) => s.id === currentSessionId)?.title || "New conversation"}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge className="rounded-sm bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-50 font-mono text-[10px] uppercase tracking-wider" data-testid="online-badge">
              <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full mr-1.5 inline-block"></span>
              Claude Sonnet 4.6
            </Badge>
          </div>
        </header>

        <div className="flex-1 flex min-h-0">
          {/* CONVERSATION */}
          <div className="flex-1 flex flex-col min-w-0">
            <ScrollArea className="flex-1">
              <div className="max-w-3xl mx-auto px-6 py-8">
                {isEmpty ? (
                  <EmptyState onPick={(q) => send(q)} />
                ) : (
                  <div className="space-y-6">
                    {messages.map((m) => (
                      <MessageRow
                        key={m.message_id}
                        msg={m}
                        onCopy={copyMessage}
                        onFeedback={submitFeedback}
                        onFollowup={(q) => send(q)}
                        onAcknowledge={acknowledgeMessage}
                      />
                    ))}
                    {sending && messages.length > 0 && messages[messages.length - 1]?.role === "assistant" && !messages[messages.length - 1]?.content && !messages[messages.length - 1]?.sources?.length && (
                      <div className="flex gap-3 -mt-3" data-testid="thinking-indicator">
                        <div className="w-8 h-8 bg-slate-900 flex items-center justify-center shrink-0 opacity-0">
                          <Robot size={16} weight="bold" className="text-white" />
                        </div>
                        <div className="font-mono text-xs uppercase tracking-[0.2em] text-slate-500">
                          SEARCHING CORPUS<span className="streaming-dot ml-1"></span>
                        </div>
                      </div>
                    )}
                    <div ref={messagesEndRef} />
                  </div>
                )}
              </div>
            </ScrollArea>

            <div className="border-t border-slate-200 bg-white">
              <div className="max-w-3xl mx-auto p-4">
                <form
                  onSubmit={(e) => { e.preventDefault(); send(); }}
                  className="relative border border-slate-300 focus-within:border-blue-600 focus-within:ring-2 focus-within:ring-blue-100 transition-all rounded-sm bg-white"
                  data-testid="chat-form"
                >
                  <Textarea
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
                    }}
                    placeholder="Ask about confined space, LOTO, ISO 45001, HAZOP, incident RCA..."
                    rows={2}
                    data-testid="chat-input"
                    className="resize-none border-0 focus-visible:ring-0 rounded-sm bg-transparent text-slate-900 placeholder:text-slate-400 px-4 py-3 pr-14 max-h-40"
                  />
                  <Button
                    type="submit"
                    disabled={!input.trim() || sending}
                    data-testid="send-message-btn"
                    className="absolute bottom-2 right-2 h-9 w-9 p-0 rounded-sm bg-blue-600 hover:bg-blue-700 text-white"
                  >
                    <PaperPlaneTilt size={16} weight="fill" />
                  </Button>
                </form>
                <div className="mt-2 font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400 text-center">
                  Enter to send · Shift+Enter for newline · <span className="text-amber-700">AI-generated — not a substitute for professional EHS advice. Verify before acting.</span>
                </div>
              </div>
            </div>
          </div>

          {/* SOURCES PANEL */}
          <aside className="w-[320px] border-l border-slate-200 bg-slate-50 hidden xl:flex flex-col" data-testid="sources-panel">
            <div className="h-14 border-b border-slate-200 bg-white px-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Books size={16} className="text-slate-700" weight="bold" />
                <div className="font-bold tracking-tight text-sm">RETRIEVED SOURCES</div>
              </div>
              <div className="font-mono text-[10px] text-slate-500 uppercase tracking-wider">{activeSources.length}</div>
            </div>
            <ScrollArea className="flex-1">
              <div className="p-3 space-y-2">
                {activeSources.length === 0 ? (
                  <div className="text-xs text-slate-500 font-mono p-3">// Sources will appear after you ask a question</div>
                ) : (
                  activeSources.map((s, i) => <SourceCard key={i} index={i + 1} src={s} />)
                )}
              </div>
            </ScrollArea>
          </aside>
        </div>
      </main>
    </div>
  );
}

function EmptyState({ onPick }) {
  return (
    <div className="py-12" data-testid="empty-state">
      <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-500 mb-3">// AI co-pilot</div>
      <h1 className="text-4xl font-black tracking-tighter text-slate-900 mb-3 leading-none">
        What EHS question is on your mind?
      </h1>
      <p className="text-slate-600 text-base mb-10 max-w-2xl">
        Ask anything about your safety procedures, permits, HAZOPs, incidents, OSHA standards, ISO requirements or chemical SDS data. I'll search your knowledge base and cite the source.
      </p>

      <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-500 mb-3">// Try one of these</div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-px bg-slate-200">
        {SUGGESTIONS.map((q, i) => (
          <button
            key={i}
            onClick={() => onPick(q)}
            data-testid={`suggestion-${i}`}
            className="text-left bg-white p-4 hover:bg-blue-50 hover:text-blue-900 transition-colors group flex items-start gap-3"
          >
            <Sparkle size={14} weight="bold" className="text-blue-600 mt-1 shrink-0" />
            <span className="text-sm font-medium leading-snug">{q}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function MessageRow({ msg, onCopy, onFeedback, onFollowup, onAcknowledge }) {
  if (msg.role === "user") {
    return (
      <div className="flex gap-3" data-testid="user-message">
        <div className="w-8 h-8 bg-blue-600 flex items-center justify-center shrink-0">
          <UserIcon size={16} weight="bold" className="text-white" />
        </div>
        <div className="flex-1 pt-1 min-w-0">
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-1">You</div>
          <div className="text-slate-800 whitespace-pre-wrap">{msg.content}</div>
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
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500">EHS AI</div>
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
                <HoverCard key={i} openDelay={200}>
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
          <div className="mt-3 flex items-center gap-1" data-testid="message-actions">
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
          </div>
        )}
        {!msg._streaming && msg.suggested_followups?.length > 0 && (
          <div className="mt-3" data-testid="followups">
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-2">Follow-up</div>
            <div className="flex flex-wrap gap-2">
              {msg.suggested_followups.map((q, i) => (
                <button
                  key={i}
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

function SourceCard({ index, src }) {
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

function SourceInner({ src }) {
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
