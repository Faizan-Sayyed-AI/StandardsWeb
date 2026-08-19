import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

// Every variant is <tint fill> + <hairline> + <readable text>, drawn from one
// accent family so the set reads as a system rather than a pile of colours.
// The families resolve per theme, which is what keeps these legible on white —
// the old raw values (emerald-400, yellow-300, indigo-400, …) measured under 2:1
// against a light surface.
const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold leading-5 whitespace-nowrap transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
  {
    variants: {
      variant: {
        default: "border-brand-line bg-brand-soft text-brand",
        brand: "border-brand-line bg-brand-soft text-brand",

        // Standard lifecycle. Six states, six distinguishable hues.
        active: "border-success-line bg-success-soft text-success",
        withdrawn: "border-danger-line bg-danger-soft text-danger",
        amended: "border-warning-line bg-warning-soft text-warning",
        revised: "border-violet-line bg-violet-soft text-violet",
        under_review: "border-info-line bg-info-soft text-info",
        // Superseded rather than wrong — reads as archival, not as an alarm.
        replaced: "border-border-strong bg-foreground/5 text-muted-foreground",

        // Job / task outcomes
        ok: "border-success-line bg-success-soft text-success",
        failed: "border-danger-line bg-danger-soft text-danger",
        pending: "border-warning-line bg-warning-soft text-warning",
        purchased: "border-success-line bg-success-soft text-success",

        // Roles
        admin: "border-violet-line bg-violet-soft text-violet",
        manager: "border-info-line bg-info-soft text-info",
        viewer: "border-border-strong bg-foreground/5 text-muted-foreground",

        secondary: "border-border bg-foreground/5 text-muted-foreground",
        outline: "border-border-strong bg-transparent text-foreground",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };

// Convenience component: auto-selects variant from standard status string
export function StatusBadge({ status }: { status: string }) {
  const variantMap: Record<string, BadgeProps["variant"]> = {
    active: "active",
    withdrawn: "withdrawn",
    replaced: "replaced",
    amended: "amended",
    revised: "revised",
    under_review: "under_review",
    ok: "ok",
    failed: "failed",
    pending: "pending",
    admin: "admin",
    manager: "manager",
    viewer: "viewer",
  };
  const variant = variantMap[status] ?? "secondary";
  const label = status.replace(/_/g, " ");
  const displayLabel = label.charAt(0).toUpperCase() + label.slice(1);
  return <Badge variant={variant}>{displayLabel}</Badge>;
}
