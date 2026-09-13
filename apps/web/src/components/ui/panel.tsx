import * as React from "react";

import { cn } from "@/lib/utils";

export function Panel({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <section className={cn("border-border bg-bg rounded-md border", className)} {...props} />;
}

export function PanelHeader({
  title,
  description,
  actions,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <header
      className={cn("border-border flex items-start justify-between gap-3 border-b px-4 py-2.5", className)}
    >
      <div className="min-w-0">
        <h2 className="text-fg text-[13px] font-medium">{title}</h2>
        {description ? <p className="text-fg-subtle mt-0.5 text-xs">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function PanelBody({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-4 py-3", className)} {...props} />;
}

export function PageHeader({
  title,
  description,
  actions,
  breadcrumb,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  breadcrumb?: React.ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        {breadcrumb ? <div className="text-fg-subtle mb-1 text-xs">{breadcrumb}</div> : null}
        <h1 className="text-fg text-lg font-semibold tracking-tight">{title}</h1>
        {description ? <p className="text-fg-muted mt-0.5 max-w-3xl text-[13px]">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function KeyValue({
  items,
  className,
}: {
  items: { label: string; value: React.ReactNode }[];
  className?: string;
}) {
  return (
    <dl className={cn("grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1.5 text-[13px]", className)}>
      {items.map((item) => (
        <React.Fragment key={item.label}>
          <dt className="text-fg-subtle">{item.label}</dt>
          <dd className="text-fg min-w-0">{item.value}</dd>
        </React.Fragment>
      ))}
    </dl>
  );
}
