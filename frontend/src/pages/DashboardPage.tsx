import { QueryError } from "@/components/QueryError";
import { Link } from "react-router-dom";
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
import { timeAgo } from "@/lib/utils";
import { useAuth } from "@/contexts/useAuth";

// One tone per tile, drawn from the accent families so the four tiles read as
// a set. The icon plate carries the colour; the number stays foreground ink so
// the eye lands on the value first.
const STAT_TONES = {
  brand: "bg-brand-soft text-brand",
  success: "bg-success-soft text-success",
  info: "bg-info-soft text-info",
  violet: "bg-violet-soft text-violet",
} as const;

function StatCard({
  label,
  value,
  icon: Icon,
  tone,
  sub,
}: {
  label: string;
  value: number | undefined;
  icon: React.ComponentType<{ className?: string }>;
  tone: keyof typeof STAT_TONES;
  sub?: string;
}) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-subtle-foreground">
              {label}
            </p>
            <p className="tabular mt-2 text-[28px] font-semibold leading-none tracking-tight text-foreground">
              {value === undefined ? (
                <Skeleton className="inline-block h-7 w-16 align-middle" />
              ) : (
                value.toLocaleString()
              )}
            </p>
            {sub && <p className="mt-2 text-xs text-muted-foreground">{sub}</p>}
          </div>
          <div
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${STAT_TONES[tone]}`}
          >
            <Icon className="h-5 w-5" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function DashboardPage() {
  const { isAdmin } = useAuth();

  const { data: stats, isError: statsFailed, refetch: retryStats } = useQuery({
    queryKey: ["dashboard", "stats"],
    queryFn: getDashboardStats,
  });

  const { data: recentStandards, isError: recentFailed } = useQuery({
    queryKey: ["standards", "recent"],
    queryFn: () => listStandards({ page: 1, page_size: 8, sort_by: "updated_at", sort_order: "desc", grouped: false }),
  });

  const { data: workerStatus, isError: workerFailed, refetch: retryWorker } = useQuery({
    queryKey: ["admin", "worker-status"],
    queryFn: getWorkerStatus,
    refetchInterval: 30000,
    enabled: isAdmin,
  });

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      {statsFailed && !stats && <QueryError subject="dashboard statistics" onRetry={retryStats} />}
      {/* Stats grid */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total standards"
          value={stats?.total_standards}
          icon={BookOpen}
          tone="brand"
          sub={`${stats?.active_standards ?? "—"} active`}
        />
        <StatCard
          label="Purchased"
          value={stats?.purchased_standards}
          icon={ShoppingCart}
          tone="success"
          sub="all editions owned"
        />
        <StatCard
          label={isAdmin ? "Active feeds" : "Unread notifications"}
          value={isAdmin ? stats?.enabled_feeds : stats?.unread_notifications}
          icon={Rss}
          tone="info"
          sub={isAdmin ? `${stats?.total_feeds ?? "—"} total configured` : undefined}
        />
        <StatCard
          label="Events (7 days)"
          value={stats?.events_last_7_days}
          icon={TrendingUp}
          tone="violet"
        />
      </div>

      {/* Recently updated standards */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Main table */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-4">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <Zap className="h-4 w-4 text-brand" />
                Recently updated standards
              </CardTitle>
              <Link
                to="/standards"
                className="text-xs font-medium text-brand hover:underline underline-offset-4 transition-colors"
              >
                View all →
              </Link>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {recentFailed ? <p role="alert" className="p-6 text-sm">Recent standards could not be loaded.</p> : recentStandards ? (
              <div className="divide-y divide-border">
                {recentStandards.items.length === 0 && <p className="p-6 text-sm text-muted-foreground">No standards yet.</p>}
                {recentStandards.items.map((std) => (
                  <Link
                    key={std.id}
                    to={`/standards/${std.id}`}
                    className="flex items-center gap-4 px-6 py-3.5 hover:bg-muted transition-colors group"
                  >
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border bg-muted text-xs font-bold text-brand group-hover:border-brand-line transition-colors">
                      {std.iso_reference.replace(/[^A-Z/]/g, "").slice(0, 3)}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-foreground truncate">
                        {std.iso_reference}
                      </p>
                      <p className="text-xs text-muted-foreground truncate">{std.title}</p>
                    </div>
                    <p className="shrink-0 text-[10px] text-subtle-foreground">
                      {timeAgo(std.updated_at)}
                    </p>
                  </Link>
                ))}
              </div>
            ) : (
              <div className="divide-y divide-border">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className="flex items-center gap-4 px-6 py-3.5">
                    <Skeleton className="h-9 w-9 rounded-lg" />
                    <div className="flex-1 space-y-1.5">
                      <Skeleton className="h-4 w-32" />
                      <Skeleton className="h-3 w-48" />
                    </div>
                    <Skeleton className="h-3 w-12" />
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
                <CheckCircle2 className="h-4 w-4 text-success" />
                Library health
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Both rows are shares of total_standards — the standards the
                  library lists — so the printed denominator is the population
                  the numerator was actually counted over. Purchased must use
                  purchased_current_standards for this: purchased_standards
                  counts superseded and edition-less rows that are not in the
                  listed library at all, so as a share of it it can exceed
                  100%. The KPI tile above still shows that fuller count. */}
              {[
                {
                  label: "Active",
                  value: stats?.active_standards,
                  total: stats?.total_standards,
                  hint: "of current editions",
                  color: "bg-success",
                },
                {
                  label: "Purchased",
                  value: stats?.purchased_current_standards,
                  total: stats?.total_standards,
                  hint: "of current editions",
                  color: "bg-primary",
                },
              ].map((item) => {
                // Clamped as a backstop: both rows now share their
                // denominator's population, but a future stat wired to the
                // wrong pair should read 100% rather than render a bar wider
                // than its track (which overflow-hidden would silently hide).
                const pct =
                  item.total && item.value !== undefined
                    ? Math.min(100, Math.round((item.value / item.total) * 100))
                    : 0;
                return (
                  <div key={item.label} className="space-y-1.5">
                    <div className="flex items-baseline justify-between gap-2 text-xs">
                      <span className="text-muted-foreground">
                        {item.label}{" "}
                        <span className="text-subtle-foreground">{item.hint}</span>
                      </span>
                      <span className="tabular font-medium text-foreground">
                        {item.value?.toLocaleString() ?? "—"} / {item.total?.toLocaleString() ?? "—"}{" "}
                        <span className="text-muted-foreground">({pct}%)</span>
                      </span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-muted border border-border">
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

          {isAdmin && <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Rss className="h-4 w-4 text-info" />
                Feed status
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Enabled feeds</span>
                <span className="tabular font-semibold text-success">{stats?.enabled_feeds ?? "—"}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Total configured</span>
                <span className="tabular font-medium text-foreground">{stats?.total_feeds ?? "—"}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Unread alerts</span>
                <span className="tabular font-semibold text-warning">
                  {stats?.unread_notifications ?? "—"}
                </span>
              </div>
            </CardContent>
          </Card>}

          {isAdmin && workerFailed && !workerStatus && <QueryError subject="worker health" onRetry={retryWorker} />}
          {isAdmin && (!workerFailed || workerStatus) && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <Activity className="h-4 w-4 text-brand" />
                    Worker health
                  </span>
                  {workerStatus ? (
                    <div className="flex items-center gap-1.5">
                      <span className={`h-2 w-2 rounded-full ${workerStatus.status === "online" ? "bg-success animate-pulse" : "bg-danger"}`} />
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
                    <span className="inline-flex items-center justify-center rounded-full bg-brand-soft px-2.5 py-0.5 text-xs font-semibold text-brand border border-brand-line">
                      {workerStatus.queues.feeds}
                    </span>
                  ) : (
                    <Skeleton className="h-5 w-8" />
                  )}
                </div>
                <div className="flex justify-between items-center text-sm">
                  <span className="text-muted-foreground">Notifications Queue</span>
                  {workerStatus ? (
                    <span className="inline-flex items-center justify-center rounded-full bg-success-soft px-2.5 py-0.5 text-xs font-semibold text-success border border-success-line">
                      {workerStatus.queues.notifications}
                    </span>
                  ) : (
                    <Skeleton className="h-5 w-8" />
                  )}
                </div>
                <div className="flex justify-between items-center text-sm">
                  <span className="text-muted-foreground">Maintenance Queue</span>
                  {workerStatus ? (
                    <span className="inline-flex items-center justify-center rounded-full bg-violet-soft px-2.5 py-0.5 text-xs font-semibold text-violet border border-violet-line">
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
