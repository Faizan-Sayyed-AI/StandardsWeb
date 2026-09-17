import { Bell, CheckCheck, LogOut, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getUnreadCount, listNotifications, markAllRead, markRead } from "@/api/notifications";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { cn, timeAgo } from "@/lib/utils";

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const { user } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();

  // Close on any click/tap outside the bell, and on Escape.
  //
  // This replaces a `fixed inset-0` backdrop div, which could not work
  // reliably: the bell lives inside the header, and the header is
  // `sticky z-30` — a stacking context. The backdrop's z-40 was therefore
  // confined *within* that z-30 layer, so the sidebar (z-40 at the root
  // level) painted above it and swallowed clicks. A document-level listener
  // is immune to stacking order. touchstart is included so a tap outside
  // closes it on touch devices.
  useEffect(() => {
    if (!open) return;

    const onPointerDown = (event: MouseEvent | TouchEvent) => {
      const target = event.target as Node | null;
      if (target && !containerRef.current?.contains(target)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("touchstart", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("touchstart", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const { data: count } = useQuery({
    queryKey: ["notifications", "count"],
    queryFn: getUnreadCount,
    refetchInterval: 30_000,
    enabled: !!user,
  });

  const { data: notifications, isLoading } = useQuery({
    queryKey: ["notifications", "list"],
    queryFn: () => listNotifications(1, 10),
    enabled: open && !!user,
  });

  const markAll = useMutation({
    mutationFn: markAllRead,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
  });

  const markOne = useMutation({
    mutationFn: markRead,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
  });

  /**
   * Open the standard a notification is about.
   *
   * Navigation is not awaited on the mark-read call: the row is already read
   * from the user's point of view the moment they click it, and making them
   * wait on a PATCH before the page moves would feel broken on a slow link.
   * A notification with no related standard (nothing links to a deleted one)
   * still marks read — it just has nowhere to go.
   */
  const openNotification = (n: { id: string; is_read: boolean; related_standard_id: string | null }) => {
    if (!n.is_read) markOne.mutate(n.id);
    setOpen(false);
    if (n.related_standard_id) navigate(`/standards/${n.related_standard_id}`);
  };

  const unreadCount = count?.unread ?? 0;

  const severityColor = (severity: string) => {
    switch (severity) {
      case "critical": return "border-danger-line bg-danger-soft";
      case "warning": return "border-warning-line bg-warning-soft";
      default: return "border-border bg-muted";
    }
  };

  return (
    <div className="relative" ref={containerRef}>
      <button
        onClick={() => setOpen(!open)}
        className={cn(
          "relative flex h-9 w-9 items-center justify-center rounded-lg border transition-all duration-200",
          open
            ? "border-brand-line bg-brand-soft text-brand"
            : "border-border bg-foreground/5 text-muted-foreground hover:text-foreground hover:bg-muted"
        )}
      >
        <Bell className="h-4 w-4" />
        {unreadCount > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[9px] font-bold text-primary-foreground pulse-ring">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <>
          {/* Panel — dismissal is handled by the outside-click effect above,
              not a backdrop element (see the comment there for why). */}
          <div className="absolute right-0 top-11 z-50 w-80 rounded-xl border border-border bg-popover/95 backdrop-blur-xl shadow-2xl">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <div>
                <p className="text-sm font-semibold text-foreground">Notifications</p>
                {unreadCount > 0 && (
                  <p className="text-xs text-muted-foreground">{unreadCount} unread</p>
                )}
              </div>
              {unreadCount > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => markAll.mutate()}
                  disabled={markAll.isPending}
                  className="text-xs text-muted-foreground gap-1 h-7"
                >
                  {markAll.isPending ? (
                    <RefreshCw className="h-3 w-3 animate-spin" />
                  ) : (
                    <CheckCheck className="h-3 w-3" />
                  )}
                  Mark all read
                </Button>
              )}
            </div>

            {/* List */}
            <div className="max-h-80 overflow-y-auto">
              {isLoading ? (
                <div className="px-4 py-8 text-center text-sm text-muted-foreground">
                  <RefreshCw className="h-4 w-4 animate-spin mx-auto mb-2" />
                  Loading…
                </div>
              ) : notifications && notifications.items.length > 0 ? (
                <div className="p-2 space-y-1">
                  {notifications.items.map((n) => (
                    <button
                      key={n.id}
                      type="button"
                      onClick={() => openNotification(n)}
                      className={cn(
                        "w-full rounded-lg border p-3 text-left transition-colors",
                        n.related_standard_id
                          ? "cursor-pointer hover:border-border-strong"
                          : "cursor-default",
                        !n.is_read
                          ? severityColor(n.severity)
                          : "border-transparent bg-transparent opacity-60"
                      )}
                    >
                      <div className="flex items-start gap-2">
                        {!n.is_read && (
                          <div className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                        )}
                        <div className="min-w-0 flex-1">
                          <p className="text-xs font-medium text-foreground leading-tight">
                            {n.title}
                          </p>
                          <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">
                            {n.body}
                          </p>
                          <p className="mt-1 text-[10px] text-subtle-foreground">
                            {timeAgo(n.created_at)}
                          </p>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="px-4 py-8 text-center">
                  <Bell className="h-8 w-8 text-subtle-foreground mx-auto mb-2" />
                  <p className="text-sm text-muted-foreground">All caught up!</p>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
