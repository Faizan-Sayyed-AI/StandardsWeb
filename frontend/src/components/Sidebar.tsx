import { NavLink, useLocation } from "react-router-dom";
import {
  BarChart3,
  BookOpen,
  Calendar,
  ChevronLeft,
  ChevronRight,
  Layers,
  Mail,
  Rss,
  Settings,
  Shield,
  Tag,
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
}

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

const navItems: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: BarChart3 },
  { label: "Standards", href: "/standards", icon: BookOpen },
  { label: "Feeds", href: "/feeds", icon: Rss, adminOnly: true },
  { label: "Schedule", href: "/schedule", icon: Calendar, adminOnly: true },
  { label: "Distribution Lists", href: "/admin/distribution-lists", icon: Mail, adminOnly: true },
  { label: "SMTP Settings", href: "/admin/smtp-config", icon: Settings, adminOnly: true },
  { label: "Document Tagging", href: "/admin/document-tagging", icon: Tag, adminOnly: true },
  { label: "Users", href: "/users", icon: Users, adminOnly: true },
  { label: "Audit Logs", href: "/admin/audit-logs", icon: Layers, adminOnly: true },
];

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
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
    <aside
      id="leftWrapper"
      style={{ width: collapsed ? 60 : 240 }}
      className="fixed inset-y-0 left-0 z-40 flex flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-[width] duration-300 ease-in-out"
    >
      {/* Logo row + collapse toggle */}
      <div className="relative flex h-16 shrink-0 items-center border-b border-sidebar-border px-3">
        <div className={cn("flex items-center gap-3 overflow-hidden", collapsed && "w-full justify-center")}>
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-accent shadow-sm">
            <Shield className="h-4 w-4 text-primary-foreground" />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <p className="text-sm font-semibold text-sidebar-foreground tracking-tight">StandardSphere</p>
              <p className="text-[10px] text-sidebar-muted">Standards Tracker</p>
            </div>
          )}
        </div>

        {/* Collapse / expand button — sits on the right edge */}
        <button
          onClick={onToggle}

          className="absolute -right-3 top-1/2 -translate-y-1/2 z-50 flex h-6 w-6 items-center justify-center rounded-full border border-sidebar-border bg-sidebar text-sidebar-muted shadow-sm transition-colors hover:border-border-strong hover:text-sidebar-foreground"
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed
            ? <ChevronRight className="h-3 w-3" />
            : <ChevronLeft className="h-3 w-3" />
          }
        </button>
      </div>

      {/* Navigation */}
      <nav className={cn("flex-1 overflow-y-auto py-4 space-y-1", collapsed ? "px-1.5" : "px-3")}>
        {!collapsed && (
          <p className="px-2 pb-2 text-[10px] uppercase tracking-widest text-sidebar-muted font-semibold">
            Navigation
          </p>
        )}

        {visibleItems.map((item) => {
          const Icon = item.icon;
          const isActive = location.pathname.startsWith(item.href);
          const unreadCount = item.href === "/dashboard" && notifData && notifData.unread > 0
            ? notifData.unread
            : null;

          if (collapsed) {
            return (
              <div key={item.href} className="relative group">
                <NavLink
                  to={item.href}
                  className={cn(
                    "flex items-center justify-center rounded-lg p-2.5 transition-all duration-200",
                    isActive
                      ? "bg-brand-soft text-brand"
                      : "text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-foreground"
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {unreadCount && (
                    <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[9px] font-bold text-primary-foreground">
                      {unreadCount > 99 ? "99+" : unreadCount}
                    </span>
                  )}
                </NavLink>
                {/* Hover tooltip */}
                <span className="pointer-events-none absolute left-full top-1/2 ml-3 -translate-y-1/2 rounded-md border border-border bg-popover px-2.5 py-1.5 text-xs text-popover-foreground whitespace-nowrap shadow-md opacity-0 transition-opacity group-hover:opacity-100 z-50">
                  {item.label}
                </span>
              </div>
            );
          }

          return (
            <NavLink
              key={item.href}
              to={item.href}
              className={cn(
                "relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors duration-200",
                "before:absolute before:left-0 before:top-1/2 before:h-5 before:w-0.5 before:-translate-y-1/2 before:rounded-r-full before:bg-primary before:transition-opacity",
                isActive
                  ? "bg-brand-soft text-brand before:opacity-100"
                  : "text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-foreground before:opacity-0"
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="flex-1 truncate">{item.label}</span>
              {unreadCount && (
                <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-[10px] font-bold text-primary-foreground">
                  {unreadCount > 99 ? "99+" : unreadCount}
                </span>
              )}
              {isActive && <ChevronRight className="h-3 w-3 shrink-0" />}
            </NavLink>
          );
        })}
      </nav>

      {/* User info */}
      {user && (
        <div className={cn("shrink-0 border-t border-sidebar-border p-3", collapsed && "flex justify-center")}>
          {collapsed ? (
            <div className="relative group">
              <div className="flex h-8 w-8 cursor-default items-center justify-center rounded-full border border-border bg-brand-soft text-sm font-semibold text-brand">
                {user.full_name?.charAt(0)?.toUpperCase() ?? user.email.charAt(0).toUpperCase()}
              </div>
              <span className="pointer-events-none absolute left-full top-1/2 ml-3 -translate-y-1/2 rounded-md border border-border bg-muted px-2.5 py-1.5 text-xs text-muted-foreground whitespace-nowrap shadow-lg opacity-0 transition-opacity group-hover:opacity-100 z-50">
                {user.full_name || user.email}
              </span>
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border bg-gradient-to-br from-brand-soft to-success-soft text-sm font-semibold text-brand">
                {user.full_name?.charAt(0)?.toUpperCase() ?? user.email.charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium text-sidebar-foreground">
                  {user.full_name || user.email}
                </p>
                <p className="truncate text-[10px] text-sidebar-muted capitalize">{user.role}</p>
              </div>
              <Settings className="h-4 w-4 shrink-0 cursor-pointer text-sidebar-muted transition-colors hover:text-sidebar-foreground" />
            </div>
          )}
        </div>
      )}
    </aside>
  );
}
