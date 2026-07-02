# Change History Timeline — Rich Badges & Snapshot Modal

## Context

`StandardDetailPage.tsx`'s "History" tab renders `ChangeHistoryTimeline`, a horizontal
timeline of `HistoryItem` rows (desktop) with a vertical fallback (mobile). Each node
currently shows a plain event-type label and an inline expandable raw-JSON block
(`JsonSnapshot`). This spec replaces both with (1) richer, color-coded event badges with
a derived plain-English secondary line, and (2) a structured Before/After snapshot modal.

Scope is frontend-only. No backend files are touched.

## Data reality check

`HistoryItem.new_value` / `old_value` (from `backend/app/tasks/feeds.py` and
`standard_service.py`) are `Record<string, unknown>` snapshots with these actual keys:

- `new` event: `iso_reference, title, edition, stage, stage_name, status, tc_committee, published_date, source_feed_id`. `old_value` is `null`.
- `updated` / `amended` events: `title, edition, stage, stage_name, status, tc_committee, published_date, content_hash`. **No `iso_reference`.**
- Confirmed via direct DB query against `ISO 27874:2008` (8 rows: 1 new, 4 updated, 3 amended) that **no** `amendment_reference`, `amendment_stage`, `amendment_stage_name`, or `amendment_status` fields exist anywhere in current data — `amended` events use the identical snapshot shape as `updated` events. The amendment description lives inside the `title` string itself (e.g. `"/CD Amd 1 - Metallic and other..."`).
- `EventType` enum (backend) has exactly: `new, updated, amended, withdrawn, replaced, purchased, status_change` — matches the spec's 7 named cases + `default`.
- "Stage Date" in the UI maps to the `published_date` snapshot key.

**Decision (user-confirmed): graceful fallback.** Helper code reads
`amendment_reference` etc. from `new_value` if present (future-proof), but since they're
never present today, `amended` events render using the same Before/After layout as
`updated` events. The dedicated "amendment" modal section only renders when those fields
actually exist.

## Code structure (user-confirmed: Approach A)

New logic lives in a new pure-function module, `frontend/src/lib/historyEvents.ts`; new
components (`EventBadge`, `SnapshotModal`) are added inline in `StandardDetailPage.tsx`
alongside the existing `TimelineNodeContent` / `ChangeHistoryTimeline`, matching how that
file already inlines its timeline components. No new directories.

## `frontend/src/lib/historyEvents.ts`

```ts
export interface EventMeta {
  icon: string;        // e.g. "✦"
  label: string;       // e.g. "Standard Discovered"
  badgeClass: string;  // Tailwind classes, badge color per spec
}

export const EVENT_META: Record<string, EventMeta> = {
  new:           { icon: "✦", label: "Standard Discovered", badgeClass: "border-emerald-500/30 bg-emerald-500/15 text-emerald-400" },
  updated:       { icon: "↻", label: "Details Updated",     badgeClass: "border-blue-500/30 bg-blue-500/15 text-blue-400" },
  amended:       { icon: "⊕", label: "Amendment Added",     badgeClass: "border-amber-500/30 bg-amber-500/15 text-amber-400" },
  withdrawn:     { icon: "✕", label: "Standard Withdrawn",  badgeClass: "border-red-500/30 bg-red-500/15 text-red-400" },
  replaced:      { icon: "→", label: "Standard Replaced",   badgeClass: "border-orange-500/30 bg-orange-500/15 text-orange-400" },
  purchased:     { icon: "★", label: "Marked as Purchased", badgeClass: "border-purple-500/30 bg-purple-500/15 text-purple-400" },
  status_change: { icon: "⟳", label: "Status Changed",      badgeClass: "border-cyan-500/30 bg-cyan-500/15 text-cyan-400" },
  default:       { icon: "•", label: "Updated",             badgeClass: "border-slate-500/30 bg-slate-500/15 text-slate-400" },
};

export function getEventMeta(eventType: string): EventMeta {
  return EVENT_META[eventType] ?? EVENT_META.default;
}

export interface SecondaryLine {
  text: string;
  italic?: boolean;
}

// Priority order per spec: stage -> status -> stage_name -> amendment_reference
// (only if present) -> iso_reference (new events only).
export function getSecondaryLine(item: HistoryItem): SecondaryLine | null;

// Keys whose value differs between old and new snapshots. Empty set if old is null.
export function diffFields(
  oldValue: Record<string, unknown> | null,
  newValue: Record<string, unknown>
): Set<string>;

export const AMENDMENT_FIELDS = [
  "amendment_reference",
  "amendment_stage",
  "amendment_stage_name",
  "amendment_status",
] as const;

// True only if new_value actually contains at least one amendment_* field.
export function hasAmendmentFields(value: Record<string, unknown>): boolean;
```

`getSecondaryLine` behavior, evaluated in this order, first match wins:

1. `old_value` exists and `old_value.stage !== new_value.stage` → `"Stage: {old} → {new}"`
2. `old_value` exists and `old_value.status !== new_value.status` → `"Status: {old} → {new}"`
3. `old_value` exists and `old_value.stage_name !== new_value.stage_name` → new stage_name, `italic: true`
4. `new_value.amendment_reference` exists → that value verbatim (inert today; see data-reality note)
5. `old_value === null` (a `new` event) and `new_value.iso_reference` exists → `"ISO Reference: {iso_reference}"`
6. else → `null` (no secondary line rendered)

## `EventBadge` component (in `StandardDetailPage.tsx`)

```tsx
function EventBadge({ item }: { item: HistoryItem }) {
  const meta = getEventMeta(item.event_type);
  const secondary = getSecondaryLine(item);
  return (
    <div className="flex flex-col items-center gap-1">
      <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${meta.badgeClass}`}>
        <span aria-hidden>{meta.icon}</span>
        {meta.label}
      </span>
      {secondary && (
        <span className={`text-[10px] text-muted-foreground ${secondary.italic ? "italic" : ""}`}>
          {secondary.text}
        </span>
      )}
    </div>
  );
}
```

Replaces the current plain event-type `<span>` inside `TimelineNodeContent`. The
existing "Via RSS / Via Manual" pill next to it is unchanged.

## `SnapshotModal` component (in `StandardDetailPage.tsx`)

```tsx
function SnapshotModal({ item, onClose }: { item: HistoryItem | null; onClose: () => void }) {
  useEffect(() => {
    if (!item) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [item, onClose]);

  if (!item) return null;
  // ... render (see behavior below)
}
```

Mounted once at the top of `ChangeHistoryTimeline`'s return, controlled by
`const [openItem, setOpenItem] = useState<HistoryItem | null>(null)`. Each node's "View
Snapshot" button calls `setOpenItem(item)`; modal's `onClose` sets it back to `null`.

**Layout**

- Overlay: `fixed inset-0 bg-black/60 backdrop-blur-sm z-50`, click closes modal.
- Panel: `bg-slate-900 border border-slate-700 rounded-xl max-w-2xl w-full mx-auto mt-20 shadow-2xl transition-all duration-200`, click inside does not propagate to overlay's close handler.
- Header: `EventBadge`-equivalent pill, formatted date/time (`formatDateTime(item.created_at)`), and a "Via RSS"/"Via Manual" tag (reusing the existing `isRss` styling from `TimelineNodeContent`).
- Body, one of three cases:
  1. **`item.old_value === null`** (a `new` event): single full-width column, header "Initial State", rows: ISO Reference, Stage (with `stage_name` in brackets if present), Status (rendered via `StatusBadge`), Title (`line-clamp-2` with native `title` attribute for hover), Edition (or "—"), TC Committee (or "—"), Stage Date (formatted `published_date`, or "—").
  2. **`item.event_type === "amended"` and `hasAmendmentFields(item.new_value)`**: single column, rows: Amendment Reference, Amendment Stage, Amendment Stage Name, Amendment Status (badge), Stage Date.
  3. **otherwise** (covers `updated`, and `amended` without real amendment fields): two columns. Left header "Before" (`bg-red-950/30`), right header "After" (`bg-green-950/30`). Both render the same row set as case 1. Each row gets `bg-amber-500/10` when its key is in `diffFields(item.old_value, item.new_value)`.
- Footer: single "Close" button, calls `onClose`.

**Row rendering helper** — a small local `SnapshotRow({ label, value, changed })` renders
a `label: value` row with the amber highlight when `changed` is true; used by all three
body cases to avoid duplicating row markup.

## `ChangeHistoryTimeline` changes

- Remove `expandedIds` state and the inline `JsonSnapshot` render (both the desktop
  `TimelineNodeContent` and the mobile vertical-fallback list) — replaced by the single
  `SnapshotModal` mounted once, keyed by `openItem`.
- `TimelineNodeContent`'s "View snapshot" toggle button becomes a "View Snapshot" button
  that calls `setOpenItem(item)` instead of toggling local expand state.
- `EventBadge` replaces the current inline badge markup in `TimelineNodeContent`; the
  existing "Via RSS/Manual" pill stays as-is next to it.

## Out of scope

- No backend changes. `amendment_reference` and friends are read defensively but the
  spec does not ask for (and this change does not add) backend support for populating
  them.
- No changes to `EVENT_ICONS` / `EVENT_COLORS` (still used by the mobile fallback's
  timeline dot icon, separate from the new badge).

## Testing plan

Manual verification only (no test suite exists in this repo). Against the local dev
server at `http://localhost:5174/standards`, open **ISO 27874:2008** (8 history rows: 1
new, 4 updated, 3 amended):

- Each event type on the timeline shows the correct icon/label/color badge.
- Secondary line appears correctly: `new` row shows `ISO Reference: ISO 27874:2008`;
  `updated`/`amended` rows show the stage/status/stage_name diff per priority order.
- "View Snapshot" opens the modal; `new` row renders single-column "Initial State";
  `updated`/`amended` rows render two-column Before/After with amber highlights on
  fields that actually changed (stage, title, status, stage_name, published_date).
- Escape key and overlay click both close the modal; clicking inside the panel does not.
- Mobile viewport (narrow window) no longer shows raw JSON; uses the same modal via its
  own "View Snapshot" button.
