"use client";

import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 rounded-sm border font-medium whitespace-nowrap transition-colors outline-none focus-visible:border-accent disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "border-accent bg-accent text-white hover:bg-accent-hover hover:border-accent-hover",
        primary: "border-accent bg-accent text-white hover:bg-accent-hover hover:border-accent-hover",
        secondary: "border-border bg-bg text-fg hover:bg-surface-2",
        outline: "border-border bg-bg text-fg hover:bg-surface-2",
        ghost: "border-transparent text-fg-muted hover:bg-surface-2 hover:text-fg",
        destructive: "border-danger bg-danger text-white hover:opacity-90",
        danger: "border-danger bg-danger text-white hover:opacity-90",
        link: "border-transparent text-accent underline-offset-4 hover:underline",
      },
      size: {
        default: "h-8 px-3 text-[13px]",
        md: "h-8 px-3 text-[13px]",
        sm: "h-7 px-2 text-xs",
        lg: "h-9 px-4 text-[13px]",
        icon: "h-7 w-7 p-0",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

function Button({
  className,
  variant,
  size,
  loading = false,
  children,
  disabled,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    loading?: boolean;
  }) {
  return (
    <button
      data-slot="button"
      className={cn(buttonVariants({ variant, size }), className)}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}
      {children}
    </button>
  );
}

export { Button, buttonVariants };
