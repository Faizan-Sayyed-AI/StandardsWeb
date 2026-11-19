import { NavLink } from "react-router-dom";
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
  Tag,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/useAuth";
import { useQuery } from "@tanstack/react-query";
import { getUnreadCount } from "@/api/notifications";

interface NavItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  adminOnly?: boolean;
}

interface SidebarProps {
  collapsed: boolean;
  onToggle?: () => void;
  onNavigate?: () => void;
}

const navItems: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: BarChart3 },
  { label: "Standards", href: "/standards", icon: BookOpen },
  { label: "Feeds", href: "/feeds", icon: Rss, adminOnly: true },
  { label: "Feed schedule", href: "/schedule", icon: Calendar, adminOnly: true },
  { label: "Distribution lists", href: "/admin/distribution-lists", icon: Mail, adminOnly: true },
  { label: "SMTP settings", href: "/admin/smtp-config", icon: Settings, adminOnly: true },
  { label: "Tagging settings", href: "/admin/document-tagging", icon: Tag, adminOnly: true },
  { label: "Users", href: "/users", icon: Users, adminOnly: true },
  { label: "Audit logs", href: "/admin/audit-logs", icon: Layers, adminOnly: true },
];

export function Sidebar({ collapsed, onToggle, onNavigate }: SidebarProps) {
  const { user, isAdmin } = useAuth();
  const { data } = useQuery({
    queryKey: ["notifications", "count"],
    queryFn: getUnreadCount,
    refetchInterval: 30_000,
    enabled: !!user,
  });
  return (
    <aside className="flex h-full min-h-0 flex-col border-r bg-sidebar">
      <div className="flex h-16 shrink-0 items-center gap-3 border-b px-4">
        {collapsed ? (
          <span aria-label="Biorad Medisys" className="grid h-8 w-8 place-items-center rounded-lg border bg-card text-xs font-bold shadow-sm">BR</span>
        ) : (
          <img src="/biorad-medisys.svg" alt="Biorad Medisys" className="w-40" />
        )}
      </div>
      <nav aria-label="Main navigation" className="flex-1 space-y-1 overflow-y-auto p-2">
        {navItems.filter(item => !item.adminOnly || isAdmin).map(({ href, label, icon: Icon }) => (
          <NavLink key={href} to={href} onClick={onNavigate} aria-label={label} title={collapsed ? label : undefined}
            className={({ isActive }) => cn("flex min-h-11 items-center gap-3 rounded-md px-3 text-sm font-medium",
              collapsed && "justify-center", isActive ? "bg-gold text-foreground" : "text-muted-foreground hover:bg-muted")}>
            <Icon className="h-4 w-4 shrink-0" />
            {!collapsed && label}
            {!collapsed && href === "/dashboard" && !!data?.unread && <span className="ml-auto text-xs">{data.unread}</span>}
          </NavLink>
        ))}
      </nav>
      {!collapsed && user && <div className="border-t p-4 text-sm">
        <p className="truncate font-medium">{user.full_name || user.email}</p>
        <p className="capitalize text-muted-foreground">{user.role}</p>
      </div>}
      {onToggle && <button onClick={onToggle} aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
        className="flex min-h-11 items-center justify-center gap-2 border-t text-sm text-muted-foreground hover:bg-muted">
        {collapsed ? <ChevronRight size={16} /> : <><ChevronLeft size={16} />Collapse navigation</>}
      </button>}
    </aside>
  );
}
