import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold whitespace-nowrap transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default: "border-indigo-500/30 bg-indigo-500/10 text-indigo-300",
        active: "border-emerald-500/30 bg-emerald-500/20 text-emerald-400",
        withdrawn: "border-red-500/30 bg-red-500/20 text-red-400",
        replaced: "border-orange-500/30 bg-orange-500/20 text-orange-400",
        amended: "border-amber-500/30 bg-amber-500/20 text-amber-400",
        revised: "border-purple-500/30 bg-purple-500/20 text-purple-400",
        under_review: "border-blue-500/30 bg-blue-500/20 text-blue-400",
        purchased: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
        ok: "border-teal-500/30 bg-teal-500/10 text-teal-300",
        failed: "border-red-500/30 bg-red-500/10 text-red-400",
        pending: "border-yellow-500/30 bg-yellow-500/10 text-yellow-300",
        secondary: "border-white/10 bg-white/5 text-muted-foreground",
        outline: "border-white/10 text-foreground bg-transparent",
        admin: "border-purple-500/30 bg-purple-500/10 text-purple-300",
        manager: "border-blue-500/30 bg-blue-500/10 text-blue-300",
        viewer: "border-gray-500/30 bg-gray-500/10 text-gray-400",
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
