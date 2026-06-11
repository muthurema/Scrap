import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "@/lib/auth-context";
import { Toaster } from "@/components/ui/sonner";
import LoginPage from "@/pages/LoginPage";
import ForgotPasswordPage from "@/pages/ForgotPasswordPage";
import ResetPasswordPage from "@/pages/ResetPasswordPage";
import ChatPage from "@/pages/ChatPage";
import AdminLayout from "@/pages/admin/AdminLayout";
import DocumentsPage from "@/pages/admin/DocumentsPage";
import WebSourcesPage from "@/pages/admin/WebSourcesPage";
import StatsPage from "@/pages/admin/StatsPage";
import AnalyticsPage from "@/pages/admin/AnalyticsPage";
import FeedbackQueuePage from "@/pages/admin/FeedbackQueuePage";
import AcknowledgementsPage from "@/pages/admin/AcknowledgementsPage";
import TeamPage from "@/pages/admin/TeamPage";
import CompaniesPage from "@/pages/admin/CompaniesPage";
import SettingsPage from "@/pages/admin/SettingsPage";
import "@/App.css";

function RequireAuth({ children, roles }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/chat" replace />;
  return children;
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route
            path="/chat"
            element={<RequireAuth><ChatPage /></RequireAuth>}
          />
          <Route
            path="/admin"
            element={<RequireAuth roles={["superadmin", "admin"]}><AdminLayout /></RequireAuth>}
          >
            <Route index element={<Navigate to="stats" replace />} />
            <Route path="stats" element={<StatsPage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
            <Route path="documents" element={<DocumentsPage />} />
            <Route path="web-sources" element={<WebSourcesPage />} />
            <Route path="feedback" element={<FeedbackQueuePage />} />
            <Route path="acknowledgements" element={<AcknowledgementsPage />} />
            <Route path="team" element={<TeamPage />} />
            <Route path="companies" element={<RequireAuth roles={["superadmin"]}><CompaniesPage /></RequireAuth>} />
            <Route path="settings" element={<RequireAuth roles={["superadmin"]}><SettingsPage /></RequireAuth>} />
          </Route>
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Routes>
        <Toaster position="top-right" richColors />
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
