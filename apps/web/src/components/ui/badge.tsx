import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-sm border px-1.5 py-px text-2xs font-medium whitespace-nowrap",
  {
    variants: {
      variant: {
        default: "border-border bg-surface-2 text-fg-muted",
        secondary: "border-border bg-surface-2 text-fg-muted",
        outline: "border-border text-fg-muted",
        destructive: "border-danger/20 bg-danger-soft text-danger",
        success: "border-success/20 bg-success-soft text-success",
        warning: "border-warning/20 bg-warning-soft text-warning",
        info: "border-info/20 bg-info-soft text-info",
      },
      tone: {
        neutral: "border-border bg-surface-2 text-fg-muted",
        success: "border-success/20 bg-success-soft text-success",
        warning: "border-warning/20 bg-warning-soft text-warning",
        danger: "border-danger/20 bg-danger-soft text-danger",
        info: "border-info/20 bg-info-soft text-info",
        accent: "border-accent/20 bg-accent-soft text-accent",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export type BadgeTone = NonNullable<VariantProps<typeof badgeVariants>["tone"]>;

function Badge({
  className,
  variant,
  tone,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span data-slot="badge" className={cn(badgeVariants({ variant, tone }), className)} {...props} />;
}

const STATUS_TONES: Record<string, BadgeTone> = {
  open: "warning",
  investigating: "info",
  validating: "info",
  resolved: "success",
  closed: "neutral",
  draft: "neutral",
  running: "info",
  completed: "success",
  stopped: "neutral",
  planned: "neutral",
  in_progress: "info",
  rolling_out: "warning",
  rolled_back: "danger",
  ship: "success",
  iterate: "warning",
  stop: "danger",
  continue: "info",
  high: "danger",
  medium: "warning",
  low: "neutral",
  proposed: "neutral",
  supported: "success",
  refuted: "danger",
  todo: "neutral",
  done: "success",
  acknowledged: "info",
  decided: "success",
  superseded: "neutral",
  not_started: "neutral",
  complete: "success",
};

function StatusBadge({ status, className }: { status: string; className?: string }) {
  return (
    <Badge tone={STATUS_TONES[status] ?? "neutral"} className={className}>
      {status.replace(/_/g, " ")}
    </Badge>
  );
}

export { Badge, badgeVariants, StatusBadge };
