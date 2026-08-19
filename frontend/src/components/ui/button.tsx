import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground hover:bg-primary-hover shadow-sm active:scale-[0.98]",
        destructive:
          "bg-danger-soft text-danger border border-danger-line hover:bg-danger hover:text-primary-foreground hover:border-transparent active:scale-[0.98]",
        outline:
          "border border-border-strong bg-card text-foreground shadow-sm hover:bg-muted active:scale-[0.98]",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-foreground/10 active:scale-[0.98]",
        ghost: "text-foreground hover:bg-muted active:scale-[0.98]",
        link: "text-brand underline-offset-4 hover:underline p-0 h-auto",
        success:
          "bg-success-soft text-success border border-success-line hover:bg-success hover:text-primary-foreground hover:border-transparent active:scale-[0.98]",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-11 rounded-md px-8 text-base",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
