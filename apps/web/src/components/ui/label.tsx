"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

function Label({ className, ...props }: React.ComponentProps<"label">) {
  return (
    <label
      data-slot="label"
      className={cn("text-fg-muted mb-1 block text-xs font-medium", className)}
      {...props}
    />
  );
}

export { Label };
