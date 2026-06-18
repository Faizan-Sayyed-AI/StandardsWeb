import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle, Clock, Loader2, Play, Plus, RefreshCw, Rss,
  ToggleRight, Trash2, XCircle,
} from "lucide-react";
import { listFeeds, createFeed, updateFeed, deleteFeed, triggerPoll, type FeedCreate } from "@/api/feeds";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusBadge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime, timeAgo } from "@/lib/utils";

const DAYS_OF_WEEK = [
  { value: 0, label: "Monday" },
  { value: 1, label: "Tuesday" },
  { value: 2, label: "Wednesday" },
  { value: 3, label: "Thursday" },
  { value: 4, label: "Friday" },
  { value: 5, label: "Saturday" },
  { value: 6, label: "Sunday" },
];

const DEFAULT_FORM: FeedCreate = {
  name: "",
  url: "",
  tc_committee: "",
  schedule_type: "daily",
  schedule_hour: 6,
  schedule_day_of_week: 0,
  is_enabled: true,
};

export function FeedsPage() {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<FeedCreate>(DEFAULT_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [pollingFeed, setPollingFeed] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["feeds", page],
    queryFn: () => listFeeds(page, 20),
  });

  const createMutation = useMutation({
    mutationFn: createFeed,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["feeds"] });
      setShowCreate(false);
      setForm(DEFAULT_FORM);
      setFormError(null);
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      setFormError(err?.response?.data?.detail ?? "Failed to create feed");
    },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      updateFeed(id, { is_enabled: enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["feeds"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteFeed,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["feeds"] }),
  });

  const handlePoll = async (id: string) => {
    setPollingFeed(id);
    try {
      const result = await triggerPoll(id);
      alert(`Poll dispatched! Task ID: ${result.task_id}`);
    } catch {
      alert("Failed to trigger poll");
    } finally {
      setPollingFeed(null);
      qc.invalidateQueries({ queryKey: ["feeds"] });
    }
  };

  const totalPages = data ? Math.ceil(data.total / 20) : 1;

  const PollStatusIcon = ({ status }: { status: string }) => {
    switch (status) {
      case "ok": return <CheckCircle className="h-4 w-4 text-teal-400" />;
      case "failed": return <XCircle className="h-4 w-4 text-red-400" />;
      default: return <Clock className="h-4 w-4 text-muted-foreground" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Rss className="h-6 w-6 text-blue-400" />
            Feed Management
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            {data ? `${data.total} RSS feeds configured` : "Loading…"}
          </p>
        </div>
        <Button onClick={() => setShowCreate(true)} className="gap-2">
          <Plus className="h-4 w-4" />
          Add Feed
        </Button>
      </div>

      {/* Feeds table */}
      <Card className="overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Feed</TableHead>
              <TableHead className="w-28">Committee</TableHead>
              <TableHead className="w-28">Schedule</TableHead>
              <TableHead className="w-24">Status</TableHead>
              <TableHead className="w-36">Last Polled</TableHead>
              <TableHead className="w-20 text-center">Failures</TableHead>
              <TableHead className="w-40 text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading
              ? Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 7 }).map((_, j) => (
                      <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                    ))}
                  </TableRow>
                ))
              : data?.items.map((feed) => (
                  <TableRow key={feed.id}>
                    <TableCell>
                      <div>
                        <p className="font-medium text-foreground text-sm">{feed.name}</p>
                        <p className="text-xs text-muted-foreground truncate max-w-64">{feed.url}</p>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="text-xs text-muted-foreground">{feed.tc_committee ?? "—"}</span>
                    </TableCell>
                    <TableCell>
                      <span className="text-xs text-muted-foreground">
                        {feed.schedule_type === "daily"
                          ? `Daily ${String(feed.schedule_hour).padStart(2, "0")}:00 UTC`
                          : `Weekly ${DAYS_OF_WEEK[feed.schedule_day_of_week ?? 0]?.label ?? "Mon"} ${String(feed.schedule_hour).padStart(2, "0")}:00 UTC`}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1.5">
                        <PollStatusIcon status={feed.last_poll_status} />
                        <span className={`text-xs ${feed.is_enabled ? "text-teal-400" : "text-muted-foreground"}`}>
                          {feed.is_enabled ? "Active" : "Disabled"}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="text-xs text-muted-foreground">
                        {feed.last_polled_at ? timeAgo(feed.last_polled_at) : "Never"}
                      </span>
                    </TableCell>
                    <TableCell className="text-center">
                      <span className={`text-xs font-mono font-semibold ${feed.failure_count > 0 ? "text-red-400" : "text-muted-foreground"}`}>
                        {feed.failure_count}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center justify-end gap-1">
                        {/* Poll now */}
                        <Button
                          variant="ghost"
                          size="icon"
                          title="Poll now"
                          disabled={pollingFeed === feed.id}
                          onClick={() => handlePoll(feed.id)}
                          className="h-7 w-7 text-muted-foreground hover:text-teal-400"
                        >
                          {pollingFeed === feed.id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Play className="h-3.5 w-3.5" />
                          )}
                        </Button>
                        {/* Toggle enabled */}
                        <Button
                          variant="ghost"
                          size="icon"
                          title={feed.is_enabled ? "Disable" : "Enable"}
                          disabled={toggleMutation.isPending}
                          onClick={() =>
                            toggleMutation.mutate({ id: feed.id, enabled: !feed.is_enabled })
                          }
                          className="h-7 w-7 text-muted-foreground hover:text-indigo-400"
                        >
                          <ToggleRight className="h-3.5 w-3.5" />
                        </Button>
                        {/* Delete */}
                        <Button
                          variant="ghost"
                          size="icon"
                          title="Delete feed"
                          disabled={deleteMutation.isPending}
                          onClick={() => {
                            if (confirm(`Delete feed "${feed.name}"?`)) {
                              deleteMutation.mutate(feed.id);
                            }
                          }}
                          className="h-7 w-7 text-muted-foreground hover:text-red-400"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
          </TableBody>
        </Table>

        {/* Pagination */}
        {data && totalPages > 1 && (
          <div className="flex items-center justify-end gap-2 border-t border-white/8 px-6 py-3">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
              Previous
            </Button>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
              Next
            </Button>
          </div>
        )}
      </Card>

      {/* Create Feed Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Rss className="h-5 w-5 text-blue-400" />
              Add RSS Feed
            </DialogTitle>
            <DialogDescription>
              Configure a new RSS feed to monitor for ISO standard updates.
            </DialogDescription>
          </DialogHeader>

          {formError && (
            <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-2 text-sm text-red-400">
              {formError}
            </div>
          )}

          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="feed-name">Feed name</Label>
              <Input
                id="feed-name"
                placeholder="ISO TC 176 Standards"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="feed-url">RSS URL</Label>
              <Input
                id="feed-url"
                placeholder="https://www.iso.org/rss/home.xml"
                value={form.url}
                onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="feed-committee">TC Committee (optional)</Label>
                <Input
                  id="feed-committee"
                  placeholder="TC 176"
                  value={form.tc_committee ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, tc_committee: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="feed-hour">Poll hour (UTC)</Label>
                <Input
                  id="feed-hour"
                  type="number"
                  min={0}
                  max={23}
                  value={form.schedule_hour}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, schedule_hour: parseInt(e.target.value, 10) }))
                  }
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label>Schedule type</Label>
              <div className="flex gap-2">
                {(["daily", "weekly"] as const).map((type) => (
                  <button
                    key={type}
                    onClick={() => setForm((f) => ({ ...f, schedule_type: type }))}
                    className={`flex-1 rounded-lg border py-2 text-sm font-medium transition-colors ${
                      form.schedule_type === type
                        ? "border-indigo-500/40 bg-indigo-600/20 text-indigo-300"
                        : "border-white/10 text-muted-foreground hover:border-white/20"
                    }`}
                  >
                    {type.charAt(0).toUpperCase() + type.slice(1)}
                  </button>
                ))}
              </div>
            </div>

            {form.schedule_type === "weekly" && (
              <div className="space-y-1.5">
                <Label htmlFor="feed-day-of-week">Day of week</Label>
                <select
                  id="feed-day-of-week"
                  value={form.schedule_day_of_week ?? 0}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, schedule_day_of_week: parseInt(e.target.value, 10) }))
                  }
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring text-foreground"
                >
                  {DAYS_OF_WEEK.map((day) => (
                    <option key={day.value} value={day.value}>
                      {day.label}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => { setShowCreate(false); setFormError(null); }}>
              Cancel
            </Button>
            <Button
              onClick={() =>
                createMutation.mutate({
                  ...form,
                  tc_committee: form.tc_committee || undefined,
                  schedule_day_of_week:
                    form.schedule_type === "weekly" ? (form.schedule_day_of_week ?? 0) : undefined,
                })
              }
              disabled={createMutation.isPending || !form.name || !form.url}
              className="gap-2"
            >
              {createMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Create Feed
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
