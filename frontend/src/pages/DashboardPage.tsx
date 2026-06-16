import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  BookOpen,
  CheckCircle2,
  Rss,
  ShoppingCart,
  TrendingUp,
  Zap,
} from "lucide-react";
import { getDashboardStats } from "@/api/dashboard";
import { listStandards } from "@/api/standards";
import { getWorkerStatus } from "@/api/admin";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/badge";
import { formatDate, timeAgo } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";

function StatCard({
  label,
  value,
  icon: Icon,
  color,
  sub,
}: {
  label: string;
  value: number | undefined;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
  sub?: string;
}) {
  return (
    <Card className="relative overflow-hidden transition-transform duration-200 hover:scale-[1.02]">
      <CardContent className="p-5">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium">
              {label}
            </p>
            <p className="mt-2 text-3xl font-bold text-foreground">
              {value === undefined ? (
                <span className="inline-block"><Skeleton className="h-8 w-16 inline-block" /></span>
              ) : (
                value.toLocaleString()
              )}
            </p>
            {sub && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
          </div>
          <div
            className={`flex h-12 w-12 items-center justify-center rounded-xl ${color}`}
          >
            <Icon className="h-6 w-6" />
          </div>
        </div>
        {/* Gradient accent line at bottom */}
        <div className={`absolute bottom-0 left-0 h-0.5 w-full opacity-60 ${color.replace("bg-", "bg-gradient-to-r from-")}`} />
      </CardContent>
    </Card>
  );
}

export function DashboardPage() {
  const { user, isAdmin } = useAuth();

  const { data: stats } = useQuery({
    queryKey: ["dashboard", "stats"],
    queryFn: getDashboardStats,
  });

  const { data: recentStandards } = useQuery({
    queryKey: ["standards", "recent"],
    queryFn: () => listStandards({ page: 1, page_size: 8, sort_by: "updated_at", sort_order: "desc" }),
  });

  const { data: workerStatus } = useQuery({
    queryKey: ["admin", "worker-status"],
    queryFn: getWorkerStatus,
    refetchInterval: 30000,
    enabled: isAdmin,
  });

  return (
    <div className="space-y-8">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">
            Good morning,{" "}
            <span className="gradient-text">
              {user?.full_name?.split(" ")[0] ?? "Admin"}
            </span>
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Here's what's happening with your ISO standards library today.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground border border-white/8 rounded-lg px-3 py-1.5 bg-white/4">
          <Activity className="h-3.5 w-3.5 text-teal-400" />
          <span>Live monitoring active</span>
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total Standards"
          value={stats?.total_standards}
          icon={BookOpen}
          color="bg-indigo-600/20 text-indigo-400"
          sub={`${stats?.active_standards ?? "—"} active`}
        />
        <StatCard
          label="Purchased"
          value={stats?.purchased_standards}
          icon={ShoppingCart}
          color="bg-teal-600/20 text-teal-400"
        />
        <StatCard
          label="Active Feeds"
          value={stats?.enabled_feeds}
          icon={Rss}
          color="bg-blue-600/20 text-blue-400"
          sub={`${stats?.total_feeds ?? "—"} total configured`}
        />
        <StatCard
          label="Events (7 days)"
          value={stats?.events_last_7_days}
          icon={TrendingUp}
          color="bg-purple-600/20 text-purple-400"
        />
      </div>

      {/* Recently updated standards */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Main table */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-4">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <Zap className="h-4 w-4 text-indigo-400" />
                Recently Updated Standards
              </CardTitle>
              <a
                href="/standards"
                className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
              >
                View all →
              </a>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {recentStandards ? (
              <div className="divide-y divide-white/5">
                {recentStandards.items.map((std) => (
                  <a
                    key={std.id}
                    href={`/standards/${std.id}`}
                    className="flex items-center gap-4 px-6 py-3.5 hover:bg-white/4 transition-colors group"
                  >
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-white/8 bg-white/4 text-xs font-bold text-indigo-300 group-hover:border-indigo-500/30 transition-colors">
                      {std.iso_reference.replace(/[^A-Z/]/g, "").slice(0, 3)}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-foreground truncate">
                        {std.iso_reference}
                      </p>
                      <p className="text-xs text-muted-foreground truncate">{std.title}</p>
                    </div>
                    <div className="flex flex-col items-end gap-1.5 shrink-0">
                      <StatusBadge status={std.status} />
                      <p className="text-[10px] text-muted-foreground/60">
                        {timeAgo(std.updated_at)}
                      </p>
                    </div>
                  </a>
                ))}
              </div>
            ) : (
              <div className="divide-y divide-white/5">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className="flex items-center gap-4 px-6 py-3.5">
                    <Skeleton className="h-9 w-9 rounded-lg" />
                    <div className="flex-1 space-y-1.5">
                      <Skeleton className="h-4 w-32" />
                      <Skeleton className="h-3 w-48" />
                    </div>
                    <Skeleton className="h-5 w-14 rounded-full" />
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Quick stats sidebar */}
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-teal-400" />
                Library Health
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {[
                {
                  label: "Active",
                  value: stats?.active_standards,
                  total: stats?.total_standards,
                  color: "bg-teal-500",
                },
                {
                  label: "Purchased",
                  value: stats?.purchased_standards,
                  total: stats?.total_standards,
                  color: "bg-indigo-500",
                },
              ].map((item) => {
                const pct =
                  item.total && item.value !== undefined
                    ? Math.round((item.value / item.total) * 100)
                    : 0;
                return (
                  <div key={item.label} className="space-y-1.5">
                    <div className="flex justify-between text-xs">
                      <span className="text-muted-foreground">{item.label}</span>
                      <span className="text-foreground font-medium">
                        {item.value ?? "—"} ({pct}%)
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full bg-white/8 overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-700 ${item.color}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Rss className="h-4 w-4 text-blue-400" />
                Feed Status
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Enabled feeds</span>
                <span className="font-medium text-teal-400">{stats?.enabled_feeds ?? "—"}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Total configured</span>
                <span className="font-medium">{stats?.total_feeds ?? "—"}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Unread alerts</span>
                <span className="font-medium text-yellow-400">
                  {stats?.unread_notifications ?? "—"}
                </span>
              </div>
            </CardContent>
          </Card>

          {isAdmin && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <Activity className="h-4 w-4 text-indigo-400" />
                    Worker Health
                  </span>
                  {workerStatus ? (
                    <div className="flex items-center gap-1.5">
                      <span className={`h-2 w-2 rounded-full ${workerStatus.status === "online" ? "bg-emerald-500 animate-pulse" : "bg-rose-500"}`} />
                      <span className="text-xs font-semibold capitalize text-foreground">{workerStatus.status}</span>
                    </div>
                  ) : (
                    <Skeleton className="h-4 w-16" />
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex justify-between items-center text-sm">
                  <span className="text-muted-foreground">Feeds Queue</span>
                  {workerStatus ? (
                    <span className="inline-flex items-center justify-center rounded-full bg-indigo-500/10 px-2.5 py-0.5 text-xs font-semibold text-indigo-400 border border-indigo-500/20">
                      {workerStatus.queues.feeds}
                    </span>
                  ) : (
                    <Skeleton className="h-5 w-8" />
                  )}
                </div>
                <div className="flex justify-between items-center text-sm">
                  <span className="text-muted-foreground">Notifications Queue</span>
                  {workerStatus ? (
                    <span className="inline-flex items-center justify-center rounded-full bg-teal-500/10 px-2.5 py-0.5 text-xs font-semibold text-teal-400 border border-teal-500/20">
                      {workerStatus.queues.notifications}
                    </span>
                  ) : (
                    <Skeleton className="h-5 w-8" />
                  )}
                </div>
                <div className="flex justify-between items-center text-sm">
                  <span className="text-muted-foreground">Maintenance Queue</span>
                  {workerStatus ? (
                    <span className="inline-flex items-center justify-center rounded-full bg-purple-500/10 px-2.5 py-0.5 text-xs font-semibold text-purple-400 border border-purple-500/20">
                      {workerStatus.queues.maintenance}
                    </span>
                  ) : (
                    <Skeleton className="h-5 w-8" />
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
