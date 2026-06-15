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

export function SchedulePage() {
  const { data, isLoading } = useQuery({
    queryKey: ["feeds", 1],
    queryFn: () => listFeeds(1, 100),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
          <Calendar className="h-6 w-6 text-purple-400" />
          Schedule Configuration
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          View and manage the polling schedule for all configured RSS feeds.
          Edit individual feed schedules from the{" "}
          <a href="/feeds" className="text-indigo-400 hover:underline">
            Feed Management
          </a>{" "}
          page.
        </p>
      </div>

      {/* Overview cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          {
            label: "Total Scheduled",
            value: data?.total,
            icon: Calendar,
            color: "text-purple-400 bg-purple-600/20",
          },
          {
            label: "Active Schedules",
            value: data?.items.filter((f) => f.is_enabled).length,
            icon: Clock,
            color: "text-teal-400 bg-teal-600/20",
          },
          {
            label: "Disabled",
            value: data?.items.filter((f) => !f.is_enabled).length,
            icon: Settings,
            color: "text-yellow-400 bg-yellow-600/20",
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
            <Clock className="h-4 w-4 text-purple-400" />
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
                  className="flex items-center gap-4 rounded-lg border border-white/8 bg-white/4 p-4 transition-colors hover:bg-white/6"
                >
                  {/* Status indicator */}
                  <div
                    className={`h-2 w-2 rounded-full shrink-0 ${
                      feed.is_enabled ? "bg-teal-400" : "bg-white/20"
                    }`}
                  />

                  {/* Feed info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <Rss className="h-3.5 w-3.5 text-blue-400 shrink-0" />
                      <p className="text-sm font-medium text-foreground truncate">{feed.name}</p>
                      {feed.tc_committee && (
                        <span className="shrink-0 rounded-full border border-white/10 px-2 py-0.5 text-[10px] text-muted-foreground">
                          {feed.tc_committee}
                        </span>
                      )}
                    </div>
                    <p className="mt-0.5 text-xs text-muted-foreground truncate">{feed.url}</p>
                  </div>

                  {/* Cron expression */}
                  <div className="text-right shrink-0">
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
                        feed.schedule_type === "daily" ? "*" : (feed.schedule_day_of_week ?? 0)
                      }`}
                    </p>
                  </div>

                  {/* Enabled badge */}
                  <div
                    className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium border ${
                      feed.is_enabled
                        ? "border-teal-500/30 bg-teal-500/10 text-teal-300"
                        : "border-white/10 bg-white/5 text-muted-foreground"
                    }`}
                  >
                    {feed.is_enabled ? "Active" : "Disabled"}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-12 text-center space-y-3">
              <Calendar className="h-10 w-10 text-muted-foreground/30" />
              <p className="text-sm text-muted-foreground">No feeds configured yet</p>
              <a href="/feeds" className="text-xs text-indigo-400 hover:underline">
                Go to Feed Management →
              </a>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="rounded-lg border border-yellow-500/20 bg-yellow-500/8 p-4 text-sm text-yellow-300/80">
        <strong>Note:</strong> Schedule changes take effect within 5 minutes as Celery Beat
        re-reads its schedule table. To trigger an immediate poll, use the{" "}
        <a href="/feeds" className="underline">Play button on the Feeds page</a>.
      </div>
    </div>
  );
}
