"use client";

import { Sparkles } from "lucide-react";
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { usePermission } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

export function AskAnalystButton({
  href,
  children = "Ask analyst",
  className,
  size = "md",
}: {
  href: `/analyst?${string}`;
  children?: React.ReactNode;
  className?: string;
  size?: "sm" | "md";
}) {
  const allowed = usePermission("use_analyst");
  if (!allowed) return null;
  return (
    <Link href={href} className={cn(buttonVariants({ variant: "secondary", size }), className)}>
      <Sparkles className="size-3.5" />
      {children}
    </Link>
  );
}
