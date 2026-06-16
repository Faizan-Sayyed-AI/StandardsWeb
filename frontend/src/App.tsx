import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "@/lib/queryClient";
import { AuthProvider } from "@/contexts/AuthContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { Layout } from "@/components/Layout";
import { LoginPage } from "@/pages/LoginPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { StandardsPage } from "@/pages/StandardsPage";
import { StandardDetailPage } from "@/pages/StandardDetailPage";
import { FeedsPage } from "@/pages/FeedsPage";
import { SchedulePage } from "@/pages/SchedulePage";
import { DistributionListsPage } from "@/pages/DistributionListsPage";
import { SMTPConfigPage } from "@/pages/SMTPConfigPage";

// Layout route: ProtectedRoute + Layout together as the parent route element
function ProtectedLayout() {
  return (
    <ProtectedRoute>
      <Layout />
    </ProtectedRoute>
  );
}

// Admin-only layout: re-check admin role inside the layout
function AdminLayout() {
  return (
    <ProtectedRoute requireAdmin>
      <Outlet />
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            {/* Public routes */}
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<Navigate to="/dashboard" replace />} />

            {/* Protected routes — use Layout which renders <Outlet /> for page content */}
            <Route element={<ProtectedLayout />}>
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/standards" element={<StandardsPage />} />
              <Route path="/standards/:id" element={<StandardDetailPage />} />

              {/* Admin-only routes — nested inside ProtectedLayout */}
              <Route element={<AdminLayout />}>
                <Route path="/feeds" element={<FeedsPage />} />
                <Route path="/schedule" element={<SchedulePage />} />
                <Route path="/admin/distribution-lists" element={<DistributionListsPage />} />
                <Route path="/admin/smtp-config" element={<SMTPConfigPage />} />
              </Route>
            </Route>

            {/* 404 fallback */}
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
