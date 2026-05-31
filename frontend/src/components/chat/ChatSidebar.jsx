import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Plus, ChatCircle, SignOut, Trash, GearSix, User as UserIcon, X as XIcon,
} from "@phosphor-icons/react";
import { Logo } from "@/components/Logo";

export function ChatSidebar({
  sessions, currentSessionId, user, mobileOpen, onClose,
  onStartNew, onLoadSession, onDeleteSession, onClearAll, onLogout,
}) {
  const navigate = useNavigate();
  return (
    <>
      {mobileOpen && (
        <div
          onClick={onClose}
          className="lg:hidden fixed inset-0 z-30 bg-slate-900/50 backdrop-blur-sm"
          data-testid="mobile-sidebar-backdrop"
          aria-hidden="true"
        />
      )}
      <aside
        className={`fixed lg:static inset-y-0 left-0 z-40 w-[280px] lg:w-[260px] border-r border-slate-200 bg-white flex flex-col transform transition-transform duration-200 lg:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        data-testid="chat-sidebar"
      >
        <div className="p-4 border-b border-slate-200 flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <Logo size={32} />
              <div className="font-bold tracking-tight text-slate-900 truncate">EHS Intelligence</div>
            </div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500">Turnstile360 RAG</div>
          </div>
          <button
            onClick={onClose}
            data-testid="close-sidebar-btn"
            className="lg:hidden p-1.5 text-slate-500 hover:text-slate-900 hover:bg-slate-100 transition-colors"
            aria-label="Close menu"
          >
            <XIcon size={18} weight="bold" />
          </button>
        </div>

        <div className="p-3">
          <Button
            onClick={onStartNew}
            data-testid="new-chat-btn"
            className="w-full rounded-sm bg-slate-900 hover:bg-slate-800 text-white font-semibold tracking-tight h-10"
          >
            <Plus size={16} weight="bold" />
            <span className="ml-2">NEW CHAT</span>
          </Button>
        </div>

        <div className="px-3 pb-1 flex items-center justify-between gap-2">
          <div className="font-mono text-[10px] uppercase tracking-[0.25em] text-slate-500 px-1">Recent</div>
          {sessions.length > 0 && (
            <button
              onClick={onClearAll}
              data-testid="clear-all-sessions-btn"
              className="font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 text-slate-500 hover:text-rose-700 hover:bg-rose-50 border border-transparent hover:border-rose-200 transition-colors"
              title="Delete all chats"
            >
              Clear all
            </button>
          )}
        </div>
        <ScrollArea className="flex-1 px-2">
          <div className="space-y-px pb-2">
            {sessions.length === 0 && (
              <div className="px-3 py-4 text-xs text-slate-500 font-mono">No conversations yet</div>
            )}
            {sessions.map((s) => (
              <div
                key={s.id}
                className={`group w-full px-2 py-2 border border-transparent hover:border-slate-200 hover:bg-slate-50 transition-colors flex items-center gap-1.5 ${
                  currentSessionId === s.id ? "bg-slate-100 border-slate-200" : ""
                }`}
              >
                <button
                  onClick={(e) => onDeleteSession(s.id, e)}
                  data-testid={`delete-session-${s.id}`}
                  className="p-1.5 text-slate-400 hover:text-rose-700 hover:bg-rose-50 border border-transparent hover:border-rose-200 shrink-0 transition-colors"
                  aria-label="Delete chat"
                  title="Delete chat"
                >
                  <Trash size={14} weight="bold" />
                </button>
                <button
                  type="button"
                  onClick={() => onLoadSession(s.id)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onLoadSession(s.id); } }}
                  data-testid={`session-${s.id}`}
                  className="flex-1 min-w-0 text-left flex items-center gap-2 px-1 py-0.5 cursor-pointer"
                >
                  <ChatCircle size={14} className="text-slate-400 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate text-slate-800">{s.title || "Untitled"}</div>
                    <div className="font-mono text-[10px] text-slate-400 uppercase tracking-wider">
                      {s.message_count} msgs
                    </div>
                  </div>
                </button>
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
            <div className="w-7 h-7 bg-slate-100 border border-slate-200 flex items-center justify-center shrink-0">
              <UserIcon size={14} weight="bold" className="text-slate-600" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium truncate">{user?.full_name || user?.email}</div>
              <div className="font-mono text-[9px] text-slate-500 uppercase tracking-wider">{user?.role}</div>
            </div>
            <button
              onClick={onLogout}
              data-testid="logout-btn"
              className="text-slate-400 hover:text-rose-600 transition-colors"
              title="Sign out"
            >
              <SignOut size={15} />
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
