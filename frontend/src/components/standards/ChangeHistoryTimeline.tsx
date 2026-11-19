import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { useState } from "react";
import {
  ArrowLeft, GitBranch, Package, ScrollText, Tag
} from "lucide-react";
import { type HistoryItem } from "@/api/standards";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDate, formatDateTime, formatTime } from "@/lib/utils";
import {
  getEventMeta,
  getSecondaryLine,
  diffFields,
  hasAmendmentFields,
} from "@/lib/historyEvents";

const EVENT_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  new: Package,
  updated: GitBranch,
  amended: ScrollText,
  replaced: ArrowLeft,
  withdrawn: Tag,
};

const EVENT_COLORS: Record<string, string> = {
  new: "border-success-line bg-success-soft text-success",
  updated: "border-info-line bg-info-soft text-info",
  amended: "border-warning-line bg-warning-soft text-warning",
  replaced: "border-warning-line bg-warning-soft text-warning",
  withdrawn: "border-danger-line bg-danger-soft text-danger",
};

// ── Timeline event styling ──────────────────────────────────────────────────

const EVENT_DOT_COLORS: Record<string, string> = {
  new: "bg-success",
  updated: "bg-info",
  amended: "bg-warning",
  withdrawn: "bg-danger",
  replaced: "bg-warning",
  default: "bg-muted",
};

// ── Event badge: icon + plain-English label + derived secondary line ────────

function EventBadge({ item }: { item: HistoryItem }) {
  const meta = getEventMeta(item.event_type);
  const secondary = getSecondaryLine(item);

  return (
    <div className="flex flex-col items-center gap-1">
      <span
        className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${meta.badgeClass}`}
      >
        <span aria-hidden>{meta.icon}</span>
        {meta.label}
      </span>
      {secondary && (
        <span
          className={`text-[10px] text-muted-foreground ${secondary.italic ? "italic" : ""}`}
        >
          {secondary.text}
        </span>
      )}
    </div>
  );
}

// ── Snapshot modal: structured Before/After (or Initial State) view ─────────

interface SnapshotRowProps {
  label: string;
  value: React.ReactNode;
  changed?: boolean;
}

function SnapshotRow({ label, value, changed }: SnapshotRowProps) {
  return (
    <div
      className={`flex items-baseline justify-between gap-3 rounded px-2 py-1.5 text-xs ${changed ? "bg-warning-soft" : ""
        }`}
    >
      <span className="text-muted-foreground shrink-0">{label}</span>
      <span className="text-foreground text-right min-w-0">{value}</span>
    </div>
  );
}

function SnapshotFields({
  value,
  changedKeys,
}: {
  value: Record<string, unknown>;
  changedKeys: Set<string>;
}) {
  const stage = value.stage != null ? String(value.stage) : null;
  const stageName = value.stage_name != null ? String(value.stage_name) : null;

  return (
    <div className="space-y-0.5">
      {typeof value.iso_reference === "string" && (
        <SnapshotRow
          label="ISO Reference"
          value={value.iso_reference}
          changed={changedKeys.has("iso_reference")}
        />
      )}
      <SnapshotRow
        label="Stage"
        value={stage ? (stageName ? `${stage} (${stageName})` : stage) : "—"}
        changed={changedKeys.has("stage") || changedKeys.has("stage_name")}
      />
      <SnapshotRow
        label="Status"
        value={
          typeof value.status === "string" ? (
            <StatusBadge status={value.status} />
          ) : (
            "—"
          )
        }
        changed={changedKeys.has("status")}
      />
      <SnapshotRow
        label="Title"
        value={
          <span
            className="line-clamp-2 text-left"
            title={typeof value.title === "string" ? value.title : undefined}
          >
            {typeof value.title === "string" ? value.title : "—"}
          </span>
        }
        changed={changedKeys.has("title")}
      />
      <SnapshotRow
        label="Edition"
        value={value.edition != null ? String(value.edition) : "—"}
        changed={changedKeys.has("edition")}
      />
      <SnapshotRow
        label="TC Committee"
        value={value.tc_committee != null ? String(value.tc_committee) : "—"}
        changed={changedKeys.has("tc_committee")}
      />
      <SnapshotRow
        label="Stage Date"
        value={
          typeof value.published_date === "string"
            ? formatDate(value.published_date)
            : "—"
        }
        changed={changedKeys.has("published_date")}
      />
    </div>
  );
}

function AmendmentFields({ value }: { value: Record<string, unknown> }) {
  return (
    <div className="space-y-0.5">
      <SnapshotRow
        label="Amendment Reference"
        value={value.amendment_reference != null ? String(value.amendment_reference) : "—"}
      />
      <SnapshotRow
        label="Amendment Stage"
        value={value.amendment_stage != null ? String(value.amendment_stage) : "—"}
      />
      <SnapshotRow
        label="Amendment Stage Name"
        value={value.amendment_stage_name != null ? String(value.amendment_stage_name) : "—"}
      />
      <SnapshotRow
        label="Amendment Status"
        value={
          typeof value.amendment_status === "string" ? (
            <StatusBadge status={value.amendment_status} />
          ) : (
            "—"
          )
        }
      />
      <SnapshotRow
        label="Stage Date"
        value={
          typeof value.published_date === "string"
            ? formatDate(value.published_date)
            : "—"
        }
      />
    </div>
  );
}

function SnapshotModal({
  item,
  onClose,
}: {
  item: HistoryItem | null;
  onClose: () => void;
}) {
  if (!item) return null;

  const meta = getEventMeta(item.event_type);
  const isRss = item.source?.toLowerCase() === "rss";
  const isInitial = item.old_value === null;
  const isAmendment = item.event_type === "amended" && hasAmendmentFields(item.new_value);
  const changedKeys = diffFields(item.old_value, item.new_value);

  return (
    <Dialog open onOpenChange={open => { if (!open) onClose(); }}>
      <DialogContent aria-describedby={undefined} className="max-w-2xl gap-0 p-0">
        <DialogTitle className="sr-only">History snapshot</DialogTitle>
        {/* Header */}
        <div className="flex items-center justify-between gap-3 border-b border-border p-5">
          <div className="flex items-center gap-3">
            <span
              className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${meta.badgeClass}`}
            >
              <span aria-hidden>{meta.icon}</span>
              {meta.label}
            </span>
            <span className="text-xs text-muted-foreground">
              {formatDateTime(item.created_at)}
            </span>
            <span
              className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium ${isRss
                  ? "border-border bg-foreground/5 text-muted-foreground"
                  : "border-brand-line bg-brand-soft text-brand"
                }`}
            >
              Via {isRss ? "RSS" : "Manual"}
            </span>
          </div>

        </div>

        {/* Body */}
        <div className="p-5">
          {isInitial && (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Initial State
              </p>
              <SnapshotFields value={item.new_value} changedKeys={new Set()} />
            </div>
          )}

          {!isInitial && isAmendment && <AmendmentFields value={item.new_value} />}

          {!isInitial && !isAmendment && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <p className="mb-2 rounded bg-danger-soft px-2 py-1 text-xs font-semibold uppercase tracking-wide text-danger">
                  Before
                </p>
                <SnapshotFields value={item.old_value ?? {}} changedKeys={changedKeys} />
              </div>
              <div>
                <p className="mb-2 rounded bg-success-soft px-2 py-1 text-xs font-semibold uppercase tracking-wide text-success">
                  After
                </p>
                <SnapshotFields value={item.new_value} changedKeys={changedKeys} />
              </div>
            </div>
          )}

          {item.notes && (
            <p className="mt-4 text-xs text-muted-foreground italic">{item.notes}</p>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end border-t border-border p-4">
          <Button variant="outline" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Change History: horizontal timeline (desktop) + vertical fallback (mobile) ──

interface TimelineNodeContentProps {
  item: HistoryItem;
  onView: () => void;
}

function TimelineNodeContent({ item, onView }: TimelineNodeContentProps) {
  const isRss = item.source?.toLowerCase() === "rss";

  return (
    <div className="flex w-[180px] shrink-0 flex-col items-center gap-1.5 px-2 text-center">
      <div className="flex flex-wrap items-center justify-center gap-1.5">
        <EventBadge item={item} />
        <span
          className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium ${isRss
              ? "border-border bg-foreground/5 text-muted-foreground"
              : "border-brand-line bg-brand-soft text-brand"
            }`}
        >
          Via {isRss ? "RSS" : "Manual"}
        </span>
      </div>
      <p className="text-xs font-semibold text-foreground">{formatDate(item.created_at)}</p>
      <p className="text-[10px] text-muted-foreground">{formatTime(item.created_at)}</p>
      <button
        onClick={onView}
        className="flex items-center gap-1 text-[10px] font-medium text-muted-foreground hover:text-foreground transition-colors"
      >
        View Snapshot
      </button>
    </div>
  );
}

export function ChangeHistoryTimeline({ items }: { items: HistoryItem[] }) {
  const [openItem, setOpenItem] = useState<HistoryItem | null>(null);

  if (items.length === 0) {
    return (
      <div className="flex items-center justify-center py-16 text-center">
        <p className="text-sm text-muted-foreground">No change history recorded yet.</p>
      </div>
    );
  }

  // Oldest → newest, left → right
  const sorted = [...items].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );

  return (
    <>
      {/* Desktop: horizontal timeline */}
      <div className="hidden md:block">
        <div className="relative overflow-x-auto pb-2">
          <div
            className="grid"
            style={{
              gridTemplateColumns: `repeat(${sorted.length}, minmax(180px, 1fr))`,
              gridTemplateRows: "auto 2rem auto",
              width: sorted.length > 5 ? `${sorted.length * 180}px` : "100%",
            }}
          >
            {/* Full-width line running through the middle */}
            <div
              className="col-start-1 row-start-2 self-center h-px bg-border"
              style={{ gridColumnEnd: `span ${sorted.length}` }}
            />

            {sorted.map((item, index) => {
              const isAbove = index % 2 === 0;
              const dotColor = EVENT_DOT_COLORS[item.event_type] ?? EVENT_DOT_COLORS.default;

              return (
                <div key={item.id} className="contents">
                  {/* Above-the-line slot */}
                  <div
                    className="row-start-1 flex flex-col items-center justify-end gap-2"
                    style={{ gridColumnStart: index + 1 }}
                  >
                    {isAbove && (
                      <>
                        <TimelineNodeContent item={item} onView={() => setOpenItem(item)} />
                        <div className="w-px h-4 bg-border" />
                      </>
                    )}
                  </div>

                  {/* Dot on the line */}
                  <div
                    className="row-start-2 self-center flex items-center justify-center"
                    style={{ gridColumnStart: index + 1 }}
                  >
                    <div
                      className={`h-4 w-4 rounded-full border-2 border-background ${dotColor} shadow-md z-10`}
                      title={`${getEventMeta(item.event_type).label} · ${formatDateTime(item.created_at)}`}
                    />
                  </div>

                  {/* Below-the-line slot */}
                  <div
                    className="row-start-3 flex flex-col items-center justify-start gap-2"
                    style={{ gridColumnStart: index + 1 }}
                  >
                    {!isAbove && (
                      <>
                        <div className="w-px h-4 bg-border" />
                        <TimelineNodeContent item={item} onView={() => setOpenItem(item)} />
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Mobile: vertical card list fallback */}
      <div className="relative md:hidden">
        <div className="absolute left-[18px] top-2 bottom-0 w-px bg-border" />
        <div className="space-y-4 pl-12">
          {sorted.map((item) => {
            const Icon = EVENT_ICONS[item.event_type] ?? GitBranch;
            const colorClass =
              EVENT_COLORS[item.event_type] ?? "border-border bg-foreground/5 text-muted-foreground";
            return (
              <div key={item.id} className="relative">
                <div
                  className={`absolute -left-10 flex h-7 w-7 items-center justify-center rounded-full border ${colorClass}`}
                >
                  <Icon className="h-3.5 w-3.5" />
                </div>
                <div className="rounded-lg border border-border bg-muted p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <StatusBadge status={item.event_type} />
                      <span className="text-xs text-muted-foreground capitalize">
                        via {item.source}
                      </span>
                    </div>
                    <time className="text-xs text-muted-foreground">
                      {formatDateTime(item.created_at)}
                    </time>
                  </div>
                  <button
                    onClick={() => setOpenItem(item)}
                    className="text-xs font-medium text-brand hover:text-brand transition-colors"
                  >
                    View Snapshot
                  </button>
                  {item.notes && (
                    <p className="mt-2 text-xs text-muted-foreground">{item.notes}</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <SnapshotModal item={openItem} onClose={() => setOpenItem(null)} />
    </>
  );
}
