import type { HistoryItem } from "@/api/standards";

export interface EventMeta {
  icon: string;
  label: string;
  badgeClass: string;
}

export const EVENT_META: Record<string, EventMeta> = {
  new: {
    icon: "✦",
    label: "Standard Discovered",
    badgeClass: "border-emerald-500/30 bg-emerald-500/15 text-emerald-400",
  },
  updated: {
    icon: "↻",
    label: "Details Updated",
    badgeClass: "border-blue-500/30 bg-blue-500/15 text-blue-400",
  },
  amended: {
    icon: "⊕",
    label: "Amendment Added",
    badgeClass: "border-amber-500/30 bg-amber-500/15 text-amber-400",
  },
  withdrawn: {
    icon: "✕",
    label: "Standard Withdrawn",
    badgeClass: "border-red-500/30 bg-red-500/15 text-red-400",
  },
  replaced: {
    icon: "→",
    label: "Standard Replaced",
    badgeClass: "border-orange-500/30 bg-orange-500/15 text-orange-400",
  },
  purchased: {
    icon: "★",
    label: "Marked as Purchased",
    badgeClass: "border-purple-500/30 bg-purple-500/15 text-purple-400",
  },
  status_change: {
    icon: "⟳",
    label: "Status Changed",
    badgeClass: "border-cyan-500/30 bg-cyan-500/15 text-cyan-400",
  },
  default: {
    icon: "•",
    label: "Updated",
    badgeClass: "border-slate-500/30 bg-slate-500/15 text-slate-400",
  },
};

export function getEventMeta(eventType: string): EventMeta {
  return EVENT_META[eventType] ?? EVENT_META.default;
}

export interface SecondaryLine {
  text: string;
  italic?: boolean;
}

export function getSecondaryLine(item: HistoryItem): SecondaryLine | null {
  const oldValue = item.old_value;
  const newValue = item.new_value;

  if (oldValue) {
    if (oldValue.stage !== newValue.stage && newValue.stage != null) {
      return { text: `Stage: ${oldValue.stage ?? "—"} → ${newValue.stage}` };
    }
    if (oldValue.status !== newValue.status && newValue.status != null) {
      return { text: `Status: ${oldValue.status ?? "—"} → ${newValue.status}` };
    }
    if (oldValue.stage_name !== newValue.stage_name && newValue.stage_name != null) {
      return { text: String(newValue.stage_name), italic: true };
    }
  }

  if (typeof newValue.amendment_reference === "string" && newValue.amendment_reference) {
    return { text: newValue.amendment_reference };
  }

  if (oldValue === null && typeof newValue.iso_reference === "string" && newValue.iso_reference) {
    return { text: `ISO Reference: ${newValue.iso_reference}` };
  }

  return null;
}

export function diffFields(
  oldValue: Record<string, unknown> | null,
  newValue: Record<string, unknown>
): Set<string> {
  const changed = new Set<string>();
  if (!oldValue) return changed;

  for (const key of new Set([...Object.keys(oldValue), ...Object.keys(newValue)])) {
    if (oldValue[key] !== newValue[key]) {
      changed.add(key);
    }
  }
  return changed;
}

export const AMENDMENT_FIELDS = [
  "amendment_reference",
  "amendment_stage",
  "amendment_stage_name",
  "amendment_status",
] as const;

export function hasAmendmentFields(value: Record<string, unknown>): boolean {
  return AMENDMENT_FIELDS.some((key) => value[key] != null);
}
