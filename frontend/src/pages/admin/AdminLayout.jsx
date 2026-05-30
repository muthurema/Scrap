import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/auth-context";
import {
  ShieldCheck, ChartBar, FileText, Globe, ArrowLeft, SignOut, User as UserIcon,
} from "@phosphor-icons/react";

export default function AdminLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const navItems = [
    { to: "/admin/stats", label: "Stats", icon: ChartBar, testid: "nav-stats" },
    { to: "/admin/documents", label: "Documents", icon: FileText, testid: "nav-documents" },
    { to: "/admin/web-sources", label: "Web Sources", icon: Globe, testid: "nav-web-sources" },
  ];

  return (
    <div className="h-screen flex bg-slate-50 text-slate-900">
      <aside className="w-[240px] border-r border-slate-200 bg-white flex flex-col" data-testid="admin-sidebar">
        <div className="p-4 border-b border-slate-200">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-7 h-7 bg-slate-900 flex items-center justify-center">
              <ShieldCheck size={16} weight="bold" className="text-white" />
            </div>
            <div className="font-bold tracking-tight text-slate-900">EHS Admin</div>
          </div>
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500">Control Room</div>
        </div>

        <nav className="p-2 flex-1">
          {navItems.map((it) => (
            <NavLink
              key={it.to}
              to={it.to}
              data-testid={it.testid}
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
            <div className="w-7 h-7 bg-slate-100 border border-slate-200 flex items-center justify-center">
              <UserIcon size={14} weight="bold" className="text-slate-600" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium truncate">{user?.full_name || user?.email}</div>
              <div className="font-mono text-[9px] text-slate-500 uppercase tracking-wider">{user?.role}</div>
            </div>
            <button
              onClick={() => { logout(); navigate("/login"); }}
              data-testid="admin-logout-btn"
              className="text-slate-400 hover:text-rose-600 transition-colors"
              title="Sign out"
            >
              <SignOut size={15} />
            </button>
          </div>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
