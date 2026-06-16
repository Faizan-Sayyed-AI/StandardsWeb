import { Outlet, useLocation } from "react-router-dom";
import { LogOut, Search } from "lucide-react";
import { Sidebar } from "@/components/Sidebar";
import { NotificationBell } from "@/components/NotificationBell";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";

// Map route paths to human-readable breadcrumb labels
const routeLabels: Record<string, string> = {
  "/dashboard": "Dashboard",
  "/standards": "Standards Library",
  "/feeds": "Feed Management",
  "/schedule": "Schedule Config",
  "/users": "User Management",
  "/admin/distribution-lists": "Distribution Lists",
  "/admin/smtp-config": "SMTP Settings",
  "/admin/audit-logs": "Audit Logs",
};

function getBreadcrumb(pathname: string): string {
  if (routeLabels[pathname]) return routeLabels[pathname];
  const base = "/" + pathname.split("/")[1];
  return routeLabels[base] ?? "ISTS";
}

export function Layout() {
  const { logout } = useAuth();
  const location = useLocation();
  const pageTitle = getBreadcrumb(location.pathname);

  return (
    <div className="flex min-h-screen bg-slate-950">
      <Sidebar />

      {/* Main area */}
      <div className="flex flex-1 flex-col pl-60">
        {/* Top header bar */}
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-4 border-b border-white/8 bg-slate-950/80 backdrop-blur-xl px-6">
          <div>
            <h1 className="text-sm font-semibold text-foreground">{pageTitle}</h1>
            <p className="text-xs text-muted-foreground">
              ISO Standards Tracking System
            </p>
          </div>

          <div className="flex items-center gap-2">
            {/* Global search stub */}
            <button className="hidden sm:flex items-center gap-2 h-9 rounded-lg border border-white/10 bg-white/5 px-3 text-xs text-muted-foreground hover:text-foreground hover:bg-white/8 transition-colors w-48">
              <Search className="h-3.5 w-3.5 shrink-0" />
              <span>Search standards…</span>
              <kbd className="ml-auto text-[10px] font-mono border border-white/10 rounded px-1">
                ⌘K
              </kbd>
            </button>

            <NotificationBell />

            <Button
              variant="ghost"
              size="icon"
              onClick={logout}
              title="Sign out"
              className="text-muted-foreground hover:text-foreground"
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 p-6 animate-fade-in-up">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
