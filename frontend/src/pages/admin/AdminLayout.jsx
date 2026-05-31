import { useState } from "react";
import { NavLink, Outlet, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/lib/auth-context";
import {
  ShieldCheck, ChartBar, FileText, Globe, ArrowLeft, SignOut, User as UserIcon,
  ChatCenteredDots, ChartLineUp, SealCheck, List, X as XIcon,
} from "@phosphor-icons/react";

const NAV_ITEMS = [
  { to: "/admin/stats", label: "Stats", icon: ChartBar, testid: "nav-stats" },
  { to: "/admin/analytics", label: "Analytics", icon: ChartLineUp, testid: "nav-analytics" },
  { to: "/admin/documents", label: "Documents", icon: FileText, testid: "nav-documents" },
  { to: "/admin/web-sources", label: "Web Sources", icon: Globe, testid: "nav-web-sources" },
  { to: "/admin/feedback", label: "Feedback Review", icon: ChatCenteredDots, testid: "nav-feedback" },
  { to: "/admin/acknowledgements", label: "Acknowledgements", icon: SealCheck, testid: "nav-acknowledgements" },
];

export default function AdminLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  const currentLabel = NAV_ITEMS.find((n) => location.pathname.startsWith(n.to))?.label || "Admin";

  return (
    <div className="h-[100dvh] flex bg-slate-50 text-slate-900 overflow-hidden">
      {/* MOBILE BACKDROP */}
      {mobileOpen && (
        <div
          onClick={() => setMobileOpen(false)}
          className="lg:hidden fixed inset-0 z-30 bg-slate-900/50 backdrop-blur-sm"
          data-testid="admin-sidebar-backdrop"
          aria-hidden="true"
        />
      )}

      {/* SIDEBAR */}
      <aside
        className={`fixed lg:static inset-y-0 left-0 z-40 w-[260px] lg:w-[240px] border-r border-slate-200 bg-white flex flex-col transform transition-transform duration-200 lg:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        data-testid="admin-sidebar"
      >
        <div className="p-4 border-b border-slate-200 flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <div className="w-7 h-7 bg-slate-900 flex items-center justify-center shrink-0">
                <ShieldCheck size={16} weight="bold" className="text-white" />
              </div>
              <div className="font-bold tracking-tight text-slate-900 truncate">EHS Admin</div>
            </div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500">Control Room</div>
          </div>
          <button
            onClick={() => setMobileOpen(false)}
            data-testid="close-admin-sidebar-btn"
            className="lg:hidden p-1.5 text-slate-500 hover:text-slate-900 hover:bg-slate-100 transition-colors"
            aria-label="Close menu"
          >
            <XIcon size={18} weight="bold" />
          </button>
        </div>

        <nav className="p-2 flex-1 overflow-y-auto">
          {NAV_ITEMS.map((it) => (
            <NavLink
              key={it.to}
              to={it.to}
              data-testid={it.testid}
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-2 px-3 py-2 border border-transparent transition-colors text-sm ${
                  isActive
                    ? "bg-slate-900 text-white"
                    : "hover:bg-slate-50 hover:border-slate-200 text-slate-700"
                }`
              }
            >
              <it.icon size={15} weight="bold" />
              <span className="font-medium">{it.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-slate-200 p-3 space-y-1">
          <button
            onClick={() => navigate("/chat")}
            data-testid="goto-chat-btn"
            className="w-full flex items-center gap-2 px-3 py-2 hover:bg-slate-50 border border-transparent hover:border-slate-200 text-sm transition-colors"
          >
            <ArrowLeft size={14} />
            <span className="font-medium">Back to chat</span>
          </button>
          <div className="flex items-center gap-2 px-3 py-2">
            <div className="w-7 h-7 bg-slate-100 border border-slate-200 flex items-center justify-center shrink-0">
              <UserIcon size={14} weight="bold" className="text-slate-600" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium truncate">{user?.full_name || user?.email}</div>
              <div className="font-mono text-[9px] text-slate-500 uppercase tracking-wider">{user?.role}</div>
            </div>
            <button
              onClick={() => { logout(); navigate("/login"); }}
              data-testid="logout-button"
              className="text-slate-400 hover:text-rose-600 transition-colors"
              title="Sign out"
            >
              <SignOut size={15} />
            </button>
          </div>
        </div>
      </aside>

      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* MOBILE TOP BAR */}
        <div className="lg:hidden h-14 border-b border-slate-200 bg-white px-4 flex items-center gap-3 shrink-0" data-testid="admin-mobile-topbar">
          <button
            onClick={() => setMobileOpen(true)}
            data-testid="open-admin-sidebar-btn"
            className="-ml-1 p-1.5 text-slate-700 hover:bg-slate-100 transition-colors"
            aria-label="Open menu"
          >
            <List size={20} weight="bold" />
          </button>
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-6 h-6 bg-slate-900 flex items-center justify-center shrink-0">
              <ShieldCheck size={13} weight="bold" className="text-white" />
            </div>
            <div className="font-bold tracking-tight text-slate-900 truncate">{currentLabel}</div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
