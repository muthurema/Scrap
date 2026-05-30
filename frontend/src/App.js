import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "@/lib/auth-context";
import { Toaster } from "@/components/ui/sonner";
import LoginPage from "@/pages/LoginPage";
import OnboardingPage from "@/pages/OnboardingPage";
import ChatPage from "@/pages/ChatPage";
import AdminLayout from "@/pages/admin/AdminLayout";
import DocumentsPage from "@/pages/admin/DocumentsPage";
import WebSourcesPage from "@/pages/admin/WebSourcesPage";
import StatsPage from "@/pages/admin/StatsPage";
import AnalyticsPage from "@/pages/admin/AnalyticsPage";
import FeedbackQueuePage from "@/pages/admin/FeedbackQueuePage";
import "@/App.css";

function RequireAuth({ children, roles }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/chat" replace />;
  if (user.needs_onboarding) return <Navigate to="/onboarding" replace />;
  return children;
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/onboarding" element={<OnboardingPage />} />
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route
            path="/chat"
            element={<RequireAuth><ChatPage /></RequireAuth>}
          />
          <Route
            path="/admin"
            element={<RequireAuth roles={["superadmin"]}><AdminLayout /></RequireAuth>}
          >
            <Route index element={<Navigate to="stats" replace />} />
            <Route path="stats" element={<StatsPage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
            <Route path="documents" element={<DocumentsPage />} />
            <Route path="web-sources" element={<WebSourcesPage />} />
            <Route path="feedback" element={<FeedbackQueuePage />} />
          </Route>
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Routes>
        <Toaster position="top-right" richColors />
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
