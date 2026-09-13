import * as React from "react";

import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export { Label } from "@/components/ui/label";
export { Textarea } from "@/components/ui/textarea";

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-8 w-full rounded-sm border border-border bg-bg px-2 text-[13px] text-fg placeholder:text-fg-faint focus-visible:border-accent focus-visible:outline-none disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

function Select({ className, children, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      data-slot="native-select"
      className={cn(
        "select-chevron h-8 appearance-none rounded-sm border border-border bg-bg bg-no-repeat px-2 pr-7 text-[13px] text-fg focus-visible:border-accent focus-visible:outline-none disabled:opacity-50",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}

function Field({
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

export { Field, Input, Select };
