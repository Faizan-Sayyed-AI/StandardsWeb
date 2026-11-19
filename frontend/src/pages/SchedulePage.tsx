import { Link } from "react-router-dom";
import { QueryError } from "@/components/QueryError";
import { useQuery } from "@tanstack/react-query";
import { Calendar, Clock, Rss, Settings } from "lucide-react";
import { listFeeds } from "@/api/feeds";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

function cronToHuman(cron: string, scheduleType: string, hour: number, dow?: number | null) {
  if (scheduleType === "daily") {
    return `Every day at ${String(hour).padStart(2, "0")}:00 UTC`;
  }
  const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  return `Every ${days[dow ?? 0]} at ${String(hour).padStart(2, "0")}:00 UTC`;
}

// This app's schedule_day_of_week uses 0=Monday..6=Sunday (see DAYS_OF_WEEK
// in FeedsPage.tsx), which doesn't match standard cron's day-of-week field
// (0/7=Sunday, 1=Monday..6=Saturday) — see the matching conversion in
// backend/app/services/feed_service.py's _cron_from_schedule(). Without this,
// the raw cron string shown below would silently disagree with the schedule
// actually installed on Celery Beat.
function toCronDayOfWeek(appDayOfWeek: number): number {
  return (appDayOfWeek + 1) % 7;
}

export function SchedulePage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["feeds", "schedule", 100],
    queryFn: () => listFeeds(1, 100),
  });

  if (isError && !data) return <QueryError subject="the feed schedule" onRetry={refetch} />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
          Feed schedule
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Manage polling from <Link to="/feeds" className="font-medium text-brand hover:underline">Feeds</Link>.
        </p>
      </div>

      {/* Overview cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          {
            label: "Total Scheduled",
            value: data?.total,
            icon: Calendar,
            color: "text-violet bg-violet-soft",
          },
          {
            label: "Active Schedules",
            value: data?.items.filter((f) => f.is_enabled).length,
            icon: Clock,
            color: "text-success bg-success-soft",
          },
          {
            label: "Disabled",
            value: data?.items.filter((f) => !f.is_enabled).length,
            icon: Settings,
            color: "text-warning bg-warning-soft",
          },
        ].map(({ label, value, icon: Icon, color }) => (
          <Card key={label} className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wider">{label}</p>
                <p className="text-2xl font-bold text-foreground mt-1">
                  {value === undefined ? <Skeleton className="h-8 w-8 inline-block" /> : value}
                </p>
              </div>
              <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${color}`}>
                <Icon className="h-5 w-5" />
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Schedule list */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Clock className="h-4 w-4 text-violet" />
            Feed Schedules
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-16 w-full rounded-lg" />
              ))}
            </div>
          ) : data && data.items.length > 0 ? (
            <div className="space-y-3">
              {data.items.map((feed) => (
                <div
                  key={feed.id}
                  className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-muted p-4 transition-colors hover:bg-muted"
                >
                  {/* Status indicator */}
                  <div
                    className={`h-2 w-2 rounded-full shrink-0 ${
                      feed.is_enabled ? "bg-success" : "bg-foreground/20"
                    }`}
                  />

                  {/* Feed info */}
                  <div className="min-w-0 basis-[75%] sm:flex-1">
                    <div className="flex items-center gap-2">
                      <Rss className="h-3.5 w-3.5 text-info shrink-0" />
                      <p className="text-sm font-medium text-foreground truncate">{feed.name}</p>
                      {feed.tc_committee && (
                        <span className="shrink-0 rounded-full border border-border px-2 py-0.5 text-[10px] text-muted-foreground">
                          {feed.tc_committee}
                        </span>
                      )}
                    </div>
                    <p className="mt-0.5 text-xs text-muted-foreground truncate">{feed.url}</p>
                  </div>

                  {/* Cron expression */}
                  <div className="sm:text-right shrink-0">
                    <p className="text-xs font-medium text-foreground">
                      {cronToHuman(
                        "",
                        feed.schedule_type,
                        feed.schedule_hour,
                        feed.schedule_day_of_week
                      )}
                    </p>
                    <p className="text-[10px] text-muted-foreground mt-0.5">
                      {`0 ${feed.schedule_hour} * * ${
                        feed.schedule_type === "daily" ? "*" : toCronDayOfWeek(feed.schedule_day_of_week ?? 0)
                      }`}
                    </p>
                  </div>

                  {/* Enabled badge */}
                  <div
                    className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium border ${
                      feed.is_enabled
                        ? "border-success-line bg-success-soft text-success"
                        : "border-border bg-foreground/5 text-muted-foreground"
                    }`}
                  >
                    {feed.is_enabled ? "Active" : "Disabled"}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-12 text-center space-y-3">
              <Calendar className="h-10 w-10 text-subtle-foreground" />
              <p className="text-sm text-muted-foreground">No feeds configured yet</p>
              <a href="/feeds" className="text-xs text-brand hover:underline">
                Go to Feeds →
              </a>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="rounded-lg border border-warning-line bg-warning-soft p-4 text-sm text-warning">
        <strong>Note:</strong> Schedule changes take effect within 5 minutes as Celery Beat
        re-reads its schedule table. To trigger an immediate poll, use the{" "}
        <a href="/feeds" className="underline">Play button on the Feeds page</a>.
      </div>
    </div>
  );
}
