import { NavLink, useLocation } from "react-router-dom";
import {
  BarChart3,
  BookOpen,
  Bell,
  Calendar,
  ChevronRight,
  Layers,
  Mail,
  Rss,
  Settings,
  Shield,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import { useQuery } from "@tanstack/react-query";
import { getUnreadCount } from "@/api/notifications";

interface NavItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  adminOnly?: boolean;
  managerOnly?: boolean;
  badge?: number;
}

const navItems: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: BarChart3 },
  { label: "Standards", href: "/standards", icon: BookOpen },
  { label: "Feeds", href: "/feeds", icon: Rss, adminOnly: true },
  { label: "Schedule", href: "/schedule", icon: Calendar, adminOnly: true },
  { label: "Distribution Lists", href: "/admin/distribution-lists", icon: Mail, adminOnly: true },
  { label: "SMTP Settings", href: "/admin/smtp-config", icon: Settings, adminOnly: true },
  { label: "Users", href: "/users", icon: Users, adminOnly: true },
  { label: "Audit Logs", href: "/admin/audit-logs", icon: Layers, adminOnly: true },
];

export function Sidebar() {
  const { isAdmin, isManager, user } = useAuth();
  const location = useLocation();

  const { data: notifData } = useQuery({
    queryKey: ["notifications", "count"],
    queryFn: getUnreadCount,
    refetchInterval: 30_000,
    enabled: !!user,
  });

  const visibleItems = navItems.filter((item) => {
    if (item.adminOnly) return isAdmin;
    if (item.managerOnly) return isManager;
    return true;
  });

  return (
    <aside className="fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-white/8 bg-slate-950/80 backdrop-blur-xl">
      {/* Logo */}
      <div className="flex h-16 items-center gap-3 border-b border-white/8 px-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-teal-500 shadow-lg shadow-indigo-900/40">
          <Shield className="h-4 w-4 text-white" />
        </div>
        <div>
          <p className="text-sm font-bold text-foreground tracking-tight">ISTS</p>
          <p className="text-[10px] text-muted-foreground">Standards Tracker</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
        <p className="px-2 pb-2 text-[10px] uppercase tracking-widest text-muted-foreground/60 font-semibold">
          Navigation
        </p>
        {visibleItems.map((item) => {
          const Icon = item.icon;
          const isActive = location.pathname.startsWith(item.href);
          return (
            <NavLink
              key={item.href}
              to={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-200",
                isActive
                  ? "bg-indigo-600/20 text-indigo-300 border border-indigo-500/20"
                  : "text-muted-foreground hover:bg-white/5 hover:text-foreground"
              )}
            >
              <Icon className={cn("h-4 w-4 shrink-0", isActive && "text-indigo-400")} />
              <span className="flex-1">{item.label}</span>
              {item.href === "/dashboard" && notifData && notifData.unread > 0 && (
                <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-indigo-600 px-1.5 text-[10px] font-bold text-white">
                  {notifData.unread > 99 ? "99+" : notifData.unread}
                </span>
              )}
              {isActive && <ChevronRight className="h-3 w-3 text-indigo-400" />}
            </NavLink>
          );
        })}
      </nav>

      {/* User info */}
      {user && (
        <div className="border-t border-white/8 p-4">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500/30 to-teal-500/30 border border-white/10 text-sm font-semibold text-indigo-300">
              {user.full_name?.charAt(0)?.toUpperCase() ?? user.email.charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium text-foreground">
                {user.full_name || user.email}
              </p>
              <p className="truncate text-[10px] text-muted-foreground capitalize">{user.role}</p>
            </div>
            <Settings className="h-4 w-4 text-muted-foreground hover:text-foreground cursor-pointer transition-colors" />
          </div>
        </div>
      )}
    </aside>
  );
}
