import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import "./styles.css";
import Layout from "./components/Layout";
import { Loading } from "./components/ui";
import { AuthProvider, useAuth } from "./lib/auth";
import LoginPage from "./app/login/page";
import OnboardingPage from "./app/onboarding/page";
import InboxPage from "./app/inbox/page";
import JobPage from "./app/jobs/page";
import StudioPage from "./app/studio/page";
import PipelinePage from "./app/pipeline/page";
import MessagesPage from "./app/messages/page";
import RunsPage, { RunPage } from "./app/runs/page";
import AnalyticsPage from "./app/analytics/page";
import SettingsPage from "./app/settings/page";
import SharedTracePage from "./app/share/page";

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  if (!user.settings?.onboarded && loc.pathname !== "/onboarding") return <Navigate to="/onboarding" replace />;
  return <Layout>{children}</Layout>;
}

const routes: [string, ReactNode][] = [
  ["/onboarding", <OnboardingPage />],
  ["/inbox", <InboxPage />],
  ["/jobs/:id", <JobPage />],
  ["/studio/:id", <StudioPage />],
  ["/pipeline", <PipelinePage />],
  ["/messages", <MessagesPage />],
  ["/runs", <RunsPage />],
  ["/runs/:id", <RunPage />],
  ["/analytics", <AnalyticsPage />],
  ["/settings", <SettingsPage />],
];

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/share/trace/:id" element={<SharedTracePage />} />
          {routes.map(([path, el]) => (
            <Route key={path} path={path} element={<RequireAuth>{el}</RequireAuth>} />
          ))}
          <Route path="*" element={<Navigate to="/inbox" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  </StrictMode>,
);
