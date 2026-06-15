import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default: "border-indigo-500/30 bg-indigo-500/10 text-indigo-300",
        active: "border-teal-500/30 bg-teal-500/10 text-teal-300",
        withdrawn: "border-red-500/30 bg-red-500/10 text-red-400",
        replaced: "border-orange-500/30 bg-orange-500/10 text-orange-300",
        amended: "border-yellow-500/30 bg-yellow-500/10 text-yellow-300",
        revised: "border-blue-500/30 bg-blue-500/10 text-blue-300",
        purchased: "border-teal-400/30 bg-teal-400/10 text-teal-300",
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
    ok: "ok",
    failed: "failed",
    pending: "pending",
    admin: "admin",
    manager: "manager",
    viewer: "viewer",
  };
  const variant = variantMap[status] ?? "secondary";
  return (
    <Badge variant={variant}>
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </Badge>
  );
}
