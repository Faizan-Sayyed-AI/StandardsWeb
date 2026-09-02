import type { HistoryItem } from "@/api/standards";

export interface EventMeta {
  icon: string;
  label: string;
  badgeClass: string;
}

// badgeClass follows the same <tint fill> + <hairline> + <readable text> shape
// as badgeVariants in components/ui/badge.tsx, drawn from the same six accent
// families so the timeline reads as part of the system. These must stay
// tokenised: the raw values they replaced (text-emerald-400 on a 15% emerald
// tint, text-slate-400, …) were dark-theme-only and measured under 2:1 against
// a white card, which is the contrast failure the theme rework set out to fix.
//
// Eight event types onto six families means some reuse. The hue carries
// severity, and the icon plus label carry the specific event: the two mundane
// "something changed" entries take the neutral treatment, and the four
// lifecycle events keep the hue badge.tsx already uses for that status.
export const EVENT_META: Record<string, EventMeta> = {
  new: {
    icon: "✦",
    label: "Standard Discovered",
    badgeClass: "border-success-line bg-success-soft text-success",
  },
  updated: {
    icon: "↻",
    label: "Details Updated",
    badgeClass: "border-border-strong bg-foreground/5 text-muted-foreground",
  },
  amended: {
    icon: "⊕",
    label: "Amendment Added",
    badgeClass: "border-warning-line bg-warning-soft text-warning",
  },
  withdrawn: {
    icon: "✕",
    label: "Standard Withdrawn",
    badgeClass: "border-danger-line bg-danger-soft text-danger",
  },
  replaced: {
    icon: "→",
    label: "Standard Replaced",
    badgeClass: "border-violet-line bg-violet-soft text-violet",
  },
  purchased: {
    icon: "★",
    label: "Marked as Purchased",
    badgeClass: "border-brand-line bg-brand-soft text-brand",
  },
  status_change: {
    icon: "⟳",
    label: "Status Changed",
    badgeClass: "border-info-line bg-info-soft text-info",
  },
  default: {
    icon: "•",
    label: "Updated",
    badgeClass: "border-border bg-foreground/5 text-muted-foreground",
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
