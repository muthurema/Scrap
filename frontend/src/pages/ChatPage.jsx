import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Books, List, PaperPlaneTilt, Paperclip, Robot, Trash, X as XIcon } from "@phosphor-icons/react";
import { toast } from "sonner";
import { createTypewriter } from "@/lib/typewriter";
import { authStore } from "@/lib/auth-store";

import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { ChatSidebar } from "@/components/chat/ChatSidebar";
import { EmptyState } from "@/components/chat/EmptyState";
import { MessageRow } from "@/components/chat/MessageRow";
import { SourceCard } from "@/components/chat/SourceCard";

export default function ChatPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const [sessions, setSessions] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [activeSources, setActiveSources] = useState([]);
  const [activeExternalCount, setActiveExternalCount] = useState(0);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [attachments, setAttachments] = useState([]); // [{name, dataUrl, size, mime}]
  const [docPreview, setDocPreview] = useState(null); // {src, doc?: full document metadata}
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);

  const MAX_IMAGES = 3;
  const MAX_BYTES = 5 * 1024 * 1024;
  const ALLOWED_MIME = ["image/jpeg", "image/png", "image/webp"];

  const onPickFiles = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    const remaining = MAX_IMAGES - attachments.length;
    if (files.length > remaining) {
      toast.error(`You can attach up to ${MAX_IMAGES} images per message`);
    }
    const accepted = [];
    for (const f of files.slice(0, remaining)) {
      if (!ALLOWED_MIME.includes(f.type)) {
        toast.error(`${f.name}: only JPEG, PNG, WEBP allowed`);
        continue;
      }
      if (f.size > MAX_BYTES) {
        toast.error(`${f.name}: max 5 MB per image`);
        continue;
      }
      const dataUrl = await new Promise((res, rej) => {
        const r = new FileReader();
        r.onload = () => res(r.result);
        r.onerror = rej;
        r.readAsDataURL(f);
      });
      accepted.push({ name: f.name, dataUrl, size: f.size, mime: f.type });
    }
    setAttachments((cur) => [...cur, ...accepted]);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const removeAttachment = (idx) =>
    setAttachments((cur) => cur.filter((_, i) => i !== idx));

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
    setMobileSidebarOpen(false);
    try {
      const { data } = await api.get(`/chat/sessions/${sid}/messages`);
      setMessages(data);
      const last = [...data].reverse().find((m) => m.role === "assistant");
      setActiveSources(last?.sources || []);
      setActiveExternalCount(last?.external_count || 0);
    } catch (e) {
      toast.error("Failed to load session");
    }
  };

  const startNew = () => {
    setCurrentSessionId(null);
    setMessages([]);
    setActiveSources([]);
    setActiveExternalCount(0);
    setInput("");
    setMobileSidebarOpen(false);
  };

  const send = async (content) => {
    const text = (content ?? input).trim();
    const imagesToSend = attachments.slice(0, MAX_IMAGES);
    if ((!text && imagesToSend.length === 0) || sending) return;
    setSending(true);
    setActiveSources([]);
    setActiveExternalCount(0);

    const tempUserId = "user-" + Date.now();
    let tempAsstId = "asst-" + Date.now();
    const tempUserMsg = {
      message_id: tempUserId,
      session_id: currentSessionId || "new",
      role: "user", content: text, sources: [], confidence_score: null,
      created_at: new Date().toISOString(),
      images: imagesToSend.map((a) => a.dataUrl),
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
    setAttachments([]);

    const token = authStore.getToken();
    const url = `${process.env.REACT_APP_BACKEND_URL || ""}/api/chat/stream`;
    let buffer = "";
    // Track the session id locally — setCurrentSessionId is async so the
    // closure below can't read the freshly-set state. The `session` SSE
    // event sets this; we read it in `done` for the lazy followups call.
    let liveSessionId = currentSessionId;
    const currentSessionIdLocal = () => liveSessionId;

    const typewriter = createTypewriter({
      rate: 80, maxBurst: 5,
      onUpdate: (txt) => {
        setMessages((prev) => prev.map((m) =>
          m.message_id === tempAsstId ? { ...m, content: txt } : m,
        ));
      },
    });

    try {
      const resp = await fetch(url, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          content: text || "(see attached image)",
          session_id: currentSessionId,
          images: imagesToSend.length ? imagesToSend.map((a) => a.dataUrl) : undefined,
        }),
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
          setCurrentSessionId(data.session_id);
          liveSessionId = data.session_id;
          if (data.message_id) {
            setMessages((prev) => prev.map((m) =>
              m.message_id === tempAsstId ? { ...m, message_id: data.message_id } : m,
            ));
            tempAsstId = data.message_id;
          }
        } else if (eventType === "sources") {
          // New payload shape: { sources: [...company-only...], external_count: N }
          // Fall back to the legacy shape (just an array) for backward compat
          // with any in-flight stream that started on the old backend.
          const sourcesList = Array.isArray(data) ? data : (data?.sources || []);
          const externalCount = Array.isArray(data) ? 0 : (data?.external_count || 0);
          setActiveSources(sourcesList);
          setActiveExternalCount(externalCount);
          setMessages((prev) => prev.map((m) =>
            m.message_id === tempAsstId
              ? { ...m, sources: sourcesList, external_count: externalCount }
              : m,
          ));
        } else if (eventType === "token") {
          typewriter.append(typeof data === "string" ? data : String(data));
        } else if (eventType === "done") {
          typewriter.forceComplete();
          setMessages((prev) => prev.map((m) =>
            m.message_id === tempAsstId
              ? {
                  ...m,
                  content: data?.final_text || typewriter.getRevealed(),
                  confidence_score: data?.confidence_score ?? null,
                  is_high_risk: !!data?.is_high_risk,
                  suggested_followups: data?.suggested_followups || [],
                  followups_pending: !!data?.followups_pending,
                  _streaming: false,
                }
              : m,
          ));
          // Lazy followups: kick off non-blockingly so the user can already
          // read the answer. When the server responds (~5-10s) we patch the
          // message in-place with the suggestions.
          if (data?.followups_pending && currentSessionIdLocal()) {
            const sid = currentSessionIdLocal();
            const targetMsgId = tempAsstId;
            api.post(`/chat/sessions/${sid}/followups`).then(({ data: fu }) => {
              setMessages((prev) => prev.map((m) =>
                m.message_id === targetMsgId
                  ? { ...m, suggested_followups: fu?.followups || [], followups_pending: false }
                  : m,
              ));
            }).catch(() => {
              // Silent fail — followups are a nice-to-have
              setMessages((prev) => prev.map((m) =>
                m.message_id === targetMsgId ? { ...m, followups_pending: false } : m,
              ));
            });
          }
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
          const dataLines = [];
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
      try { await typewriter.flush(); } catch (e) { console.warn("[chat] typewriter flush:", e?.message); }
      typewriter.dispose();
      setSending(false);
    }
  };

  const deleteSession = async (sid, e) => {
    e?.stopPropagation();
    if (!confirm("Delete this chat and all its messages?")) return;
    try {
      await api.delete(`/chat/sessions/${sid}`);
      if (sid === currentSessionId) startNew();
      loadSessions();
      toast.success("Chat deleted");
    } catch {
      toast.error("Delete failed");
    }
  };

  const clearAllSessions = async () => {
    if (!confirm("Delete ALL your chats? This cannot be undone.")) return;
    try {
      const { data } = await api.delete("/chat/sessions");
      startNew();
      loadSessions();
      toast.success(`Cleared ${data.deleted_sessions} chat${data.deleted_sessions === 1 ? "" : "s"}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Clear all failed");
    }
  };

  const deleteCurrentSession = async () => {
    if (!currentSessionId) { startNew(); return; }
    await deleteSession(currentSessionId);
  };

  const deleteMessage = async (messageId) => {
    if (!confirm("Delete this message (and its paired reply)?")) return;
    try {
      await api.delete(`/chat/messages/${messageId}`);
      const { data } = await api.get(`/chat/sessions/${currentSessionId}/messages`);
      setMessages(data);
      const last = [...data].reverse().find((m) => m.role === "assistant");
      setActiveSources(last?.sources || []);
      setActiveExternalCount(last?.external_count || 0);
      loadSessions();
      toast.success("Message deleted");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Delete failed");
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

  // Open a source pill → fetch full doc metadata and show a preview modal
  // with a "Open original file" link that streams from the secure
  // /documents/{id}/download endpoint.
  const openDocPreview = async (src) => {
    if (!src?.doc_id) return;
    setDocPreview({ src, doc: null, loading: true });
    try {
      const { data } = await api.get(`/documents/${src.doc_id}`);
      setDocPreview({ src, doc: data, loading: false });
    } catch (e) {
      setDocPreview({ src, doc: null, loading: false, error: e?.response?.data?.detail || "Couldn't load document" });
    }
  };

  // Build a download URL that includes the bearer token via query param-free
  // axios — we use the api instance so cookies/headers stay consistent. The
  // user sees this as a normal hyperlink, but axios attaches auth on click.
  const downloadDocBlob = async (docId, filename) => {
    try {
      const resp = await api.get(`/documents/${docId}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(resp.data);
      window.open(url, "_blank", "noopener");
      // Revoke after a delay to give the browser time to open it
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Download failed");
    }
  };

  const isEmpty = messages.length === 0;
  const sendingPlaceholderVisible = sending && messages.length > 0 &&
    messages[messages.length - 1]?.role === "assistant" &&
    !messages[messages.length - 1]?.content &&
    !messages[messages.length - 1]?.sources?.length;

  return (
    <div className="h-[100dvh] flex bg-slate-50 text-slate-900 overflow-hidden">
      <ChatSidebar
        sessions={sessions}
        currentSessionId={currentSessionId}
        user={user}
        mobileOpen={mobileSidebarOpen}
        onClose={() => setMobileSidebarOpen(false)}
        onStartNew={startNew}
        onLoadSession={loadSession}
        onDeleteSession={deleteSession}
        onClearAll={clearAllSessions}
        onLogout={() => { logout(); navigate("/login"); }}
      />

      <main className="flex-1 flex flex-col min-w-0">
        <header className="h-14 border-b border-slate-200 bg-white px-4 sm:px-6 flex items-center justify-between gap-3" data-testid="chat-header">
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={() => setMobileSidebarOpen(true)}
              data-testid="open-sidebar-btn"
              className="lg:hidden -ml-1 p-1.5 text-slate-700 hover:bg-slate-100 transition-colors"
              aria-label="Open menu"
            >
              <List size={20} weight="bold" />
            </button>
            <div className="hidden sm:block font-mono text-[10px] uppercase tracking-[0.25em] text-slate-500 shrink-0">Session</div>
            <div className="text-sm font-medium text-slate-800 truncate">
              {sessions.find((s) => s.id === currentSessionId)?.title || "New conversation"}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {currentSessionId && messages.length > 0 && (
              <button
                onClick={deleteCurrentSession}
                data-testid="delete-current-chat-btn"
                className="p-1.5 text-slate-500 hover:text-rose-700 hover:bg-rose-50 border border-transparent hover:border-rose-200 transition-colors"
                title="Delete this chat"
                aria-label="Delete this chat"
              >
                <Trash size={15} weight="bold" />
              </button>
            )}
            <Badge className="rounded-sm bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-50 font-mono text-[10px] uppercase tracking-wider" data-testid="online-badge">
              <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full mr-1.5 inline-block"></span>
              <span className="hidden sm:inline">Claude Sonnet 4.6</span>
              <span className="sm:hidden">Online</span>
            </Badge>
          </div>
        </header>

        <div className="flex-1 flex min-h-0">
          <div className="flex-1 flex flex-col min-w-0">
            <ScrollArea className="flex-1">
              <div className="max-w-3xl mx-auto px-4 sm:px-6 py-6 sm:py-8">
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
                        onDelete={deleteMessage}
                      />
                    ))}
                    {sendingPlaceholderVisible && (
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
              <div className="max-w-3xl mx-auto p-3 sm:p-4">
                {attachments.length > 0 && (
                  <div className="flex gap-2 mb-2 flex-wrap" data-testid="attachment-preview">
                    {attachments.map((a, i) => (
                      <div
                        key={`att-${i}`}
                        className="relative group border border-slate-300 bg-white rounded-sm overflow-hidden"
                      >
                        <img
                          src={a.dataUrl}
                          alt={a.name}
                          className="h-20 w-20 object-cover"
                          draggable="false"
                        />
                        <button
                          type="button"
                          onClick={() => removeAttachment(i)}
                          data-testid={`remove-attachment-${i}`}
                          className="absolute top-0.5 right-0.5 p-0.5 bg-slate-900/70 hover:bg-rose-600 text-white transition-colors"
                          aria-label="Remove attachment"
                          title="Remove"
                        >
                          <XIcon size={12} weight="bold" />
                        </button>
                        <div className="absolute bottom-0 left-0 right-0 bg-slate-900/70 px-1 py-0.5 font-mono text-[9px] uppercase tracking-wider text-white truncate">
                          {a.name}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
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
                    placeholder={attachments.length > 0
                      ? "Add a question about the image(s) — or send as-is"
                      : "Ask about confined space, LOTO, ISO 45001, HAZOP, incident RCA..."}
                    rows={2}
                    data-testid="chat-input"
                    className="resize-none border-0 focus-visible:ring-0 rounded-sm bg-transparent text-slate-900 placeholder:text-slate-400 px-3 sm:px-4 py-3 pl-12 pr-14 max-h-40 text-base"
                  />
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept="image/jpeg,image/png,image/webp"
                    onChange={onPickFiles}
                    className="hidden"
                    data-testid="chat-file-input"
                  />
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={attachments.length >= MAX_IMAGES || sending}
                    data-testid="attach-image-btn"
                    className="absolute bottom-2 left-2 h-9 w-9 p-0 rounded-sm border border-transparent hover:border-slate-300 hover:bg-slate-50 text-slate-500 hover:text-slate-800 flex items-center justify-center transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    title={attachments.length >= MAX_IMAGES ? "Max 3 images per message" : "Attach an image (JPG/PNG/WEBP, max 5 MB)"}
                    aria-label="Attach image"
                  >
                    <Paperclip size={16} weight="bold" />
                  </button>
                  <Button
                    type="submit"
                    disabled={(!input.trim() && attachments.length === 0) || sending}
                    data-testid="send-message-btn"
                    className="absolute bottom-2 right-2 h-9 w-9 p-0 rounded-sm bg-blue-600 hover:bg-blue-700 text-white"
                  >
                    <PaperPlaneTilt size={16} weight="fill" />
                  </Button>
                </form>
                <div className="mt-2 font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400 text-center leading-relaxed">
                  <span className="hidden sm:inline">Enter to send · Shift+Enter for newline · </span>
                  <span className="hidden sm:inline">📎 Attach hazard / PPE photos · </span>
                  <span className="text-amber-700">AI-generated — verify before acting.</span>
                </div>
              </div>
            </div>
          </div>

          <aside className="w-[320px] border-l border-slate-200 bg-slate-50 hidden xl:flex flex-col" data-testid="sources-panel">
            <div className="h-14 border-b border-slate-200 bg-white px-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Books size={16} className="text-slate-700" weight="bold" />
                <div className="font-bold tracking-tight text-sm">COMPANY SOURCES</div>
              </div>
              <div className="font-mono text-[10px] text-slate-500 uppercase tracking-wider">{activeSources.length}</div>
            </div>
            <ScrollArea className="flex-1">
              <div className="p-3 space-y-2">
                {activeSources.length === 0 ? (
                  <div className="text-xs text-slate-500 font-mono p-3 leading-relaxed">
                    {activeExternalCount > 0
                      ? <>This answer references external EHS guidance only — no internal company SOPs matched this query. <span className="text-slate-400">({activeExternalCount} external reference{activeExternalCount === 1 ? "" : "s"} used.)</span></>
                      : "Sources will appear after you ask a question"}
                  </div>
                ) : (
                  <>
                    {activeSources.map((s, i) => (
                      <SourceCard
                        key={s.doc_id ? `${s.doc_id}-${i}` : i}
                        index={i + 1}
                        src={s}
                        onOpen={() => openDocPreview(s)}
                      />
                    ))}
                    {activeExternalCount > 0 && (
                      <div
                        className="text-[11px] text-slate-500 font-mono uppercase tracking-wider px-3 py-2 border border-dashed border-slate-300 bg-white"
                        data-testid="external-references-note"
                      >
                        + {activeExternalCount} external reference{activeExternalCount === 1 ? "" : "s"} (ISO / OSHA / regulators)
                      </div>
                    )}
                  </>
                )}
              </div>
            </ScrollArea>
          </aside>
        </div>
      </main>

      <Dialog
        open={!!docPreview}
        onOpenChange={(o) => { if (!o) setDocPreview(null); }}
      >
        <DialogContent className="max-w-2xl" data-testid="source-preview-modal">
          <DialogHeader>
            <DialogTitle className="font-bold tracking-tight text-base pr-6">
              {docPreview?.src?.title || "Source document"}
            </DialogTitle>
            <DialogDescription className="text-xs text-slate-500 font-mono uppercase tracking-wider pt-1">
              {docPreview?.src?.doc_type} · similarity {((docPreview?.src?.similarity_score || 0) * 100).toFixed(0)}%
              {docPreview?.doc?.original_filename ? ` · ${docPreview.doc.original_filename}` : ""}
            </DialogDescription>
          </DialogHeader>
          {docPreview?.loading && (
            <div className="text-xs text-slate-500 font-mono py-4">Loading document metadata…</div>
          )}
          {docPreview?.error && (
            <div className="text-xs text-rose-700 font-mono py-3">{docPreview.error}</div>
          )}
          {docPreview?.src && (
            <div className="space-y-3">
              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-1.5">Retrieved excerpt</div>
                <div className="text-sm text-slate-700 leading-relaxed bg-slate-50 border border-slate-200 p-3 max-h-64 overflow-y-auto whitespace-pre-wrap">
                  {docPreview.src.chunk_text}
                </div>
              </div>
              {docPreview?.doc && (
                <div className="grid grid-cols-2 gap-3 text-xs">
                  {docPreview.doc.jurisdiction && (
                    <div><span className="text-slate-500 font-mono uppercase text-[10px] tracking-wider">Jurisdiction:</span> <span className="text-slate-900">{docPreview.doc.jurisdiction}</span></div>
                  )}
                  {docPreview.doc.expiry_date && (
                    <div><span className="text-slate-500 font-mono uppercase text-[10px] tracking-wider">Expires:</span> <span className="text-slate-900">{new Date(docPreview.doc.expiry_date).toISOString().slice(0, 10)}</span></div>
                  )}
                  {docPreview.doc.version && (
                    <div><span className="text-slate-500 font-mono uppercase text-[10px] tracking-wider">Version:</span> <span className="text-slate-900">{docPreview.doc.version}</span></div>
                  )}
                  {docPreview.doc.created_at && (
                    <div><span className="text-slate-500 font-mono uppercase text-[10px] tracking-wider">Uploaded:</span> <span className="text-slate-900">{new Date(docPreview.doc.created_at).toISOString().slice(0, 10)}</span></div>
                  )}
                </div>
              )}
              {docPreview?.doc?.id && (
                <div className="pt-2">
                  <Button
                    type="button"
                    onClick={() => downloadDocBlob(docPreview.doc.id, docPreview.doc.original_filename)}
                    className="rounded-sm bg-slate-900 hover:bg-slate-800 text-white h-9 font-semibold tracking-tight"
                    data-testid="open-original-doc-btn"
                  >
                    Open original file
                  </Button>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
