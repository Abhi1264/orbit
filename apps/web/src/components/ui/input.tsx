import * as React from "react";

import { cn } from "@/lib/utils";

const fieldClass =
  "rounded-sm border border-border bg-bg px-2 text-[13px] text-fg placeholder:text-fg-faint focus-visible:border-accent focus-visible:outline-none disabled:opacity-50";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(fieldClass, "h-8 w-full", className)} {...props} />;
}

export function Textarea({ className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(fieldClass, "min-h-20 w-full py-1.5 leading-5", className)} {...props} />;
}

export function Select({ className, children, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(fieldClass, "h-8 appearance-none bg-no-repeat pr-7", "select-chevron", className)}
      {...props}
    >
      {children}
    </select>
  );
}

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("text-fg-muted mb-1 block text-xs font-medium", className)} {...props} />;
}

export function Field({
  label,
  htmlFor,
  hint,
  children,
  className,
}: {
  label: string;
  htmlFor?: string;
  hint?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {hint ? <p className="text-fg-subtle mt-1 text-xs">{hint}</p> : null}
    </div>
  );
}
