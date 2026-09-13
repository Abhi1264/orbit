import { AlertTriangle } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("bg-surface-2 animate-pulse rounded-sm", className)} aria-hidden />;
}

export function TableSkeleton({ rows = 6, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-2 p-4" role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-3">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className={cn("h-4", c === 0 ? "w-48" : "w-20")} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function ChartSkeleton({ height = 240 }: { height?: number }) {
  return <Skeleton className="w-full" aria-label="Loading chart" {...{ style: { height } }} />;
}

export function EmptyState({
  title,
  description,
  action,
  className,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-10 text-center", className)}>
      <p className="text-fg text-[13px] font-medium">{title}</p>
      {description ? <p className="text-fg-subtle mt-1 max-w-sm text-xs">{description}</p> : null}
      {action ? <div className="mt-3">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  title = "Something went wrong",
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
  className?: string;
}) {
  const detail =
    error instanceof ApiError ? error.detail : error instanceof Error ? error.message : String(error);
  const requestId = error instanceof ApiError ? error.requestId : undefined;
  return (
    <div
      role="alert"
      className={cn("flex flex-col items-center justify-center px-6 py-10 text-center", className)}
    >
      <AlertTriangle className="text-danger mb-2 size-5" aria-hidden />
      <p className="text-fg text-[13px] font-medium">{title}</p>
      <p className="text-fg-subtle mt-1 max-w-md text-xs break-words">{detail}</p>
      {requestId ? <p className="text-2xs text-fg-faint mt-1 font-mono">request {requestId}</p> : null}
      {onRetry ? (
        <Button size="sm" className="mt-3" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </div>
  );
}
