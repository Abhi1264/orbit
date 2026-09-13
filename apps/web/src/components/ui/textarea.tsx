import * as React from "react";

import { cn } from "@/lib/utils";

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "rounded-sm border border-border bg-bg min-h-20 w-full px-2 py-1.5 text-[13px] leading-5 text-fg placeholder:text-fg-faint focus-visible:border-accent focus-visible:outline-none disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
