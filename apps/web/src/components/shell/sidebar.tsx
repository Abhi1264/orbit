"use client";

import {
  Activity,
  Beaker,
  BookOpen,
  Filter,
  Gauge,
  Grid3x3,
  LayoutList,
  MessageSquareText,
  Rocket,
  Search,
  Settings,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const NAV: { href: string; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { href: "/", label: "Overview", icon: Gauge },
  { href: "/analytics", label: "Analytics", icon: Activity },
  { href: "/funnels", label: "Funnels", icon: Filter },
  { href: "/cohorts", label: "Cohorts", icon: Grid3x3 },
  { href: "/segments", label: "Segments", icon: Users },
  { href: "/experiments", label: "Experiments", icon: Beaker },
  { href: "/investigations", label: "Investigations", icon: Search },
  { href: "/analyst", label: "Analyst", icon: MessageSquareText },
  { href: "/ops", label: "Product Ops", icon: BookOpen },
  { href: "/releases", label: "Releases", icon: Rocket },
  { href: "/decisions", label: "Decisions", icon: LayoutList },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="border-border bg-surface flex h-screen w-52 shrink-0 flex-col border-r">
      <div className="border-border flex h-12 items-center gap-2 border-b px-4">
        <span className="bg-accent inline-block size-2 rounded-full" aria-hidden />
        <span className="text-[13px] font-semibold tracking-tight">Orbit</span>
      </div>
      <nav aria-label="Primary" className="flex-1 overflow-y-auto px-2 py-2">
        <ul className="space-y-px">
          {NAV.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <li key={item.href}>
                <Link
                  href={item.href as "/"}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex h-7 items-center gap-2 rounded-sm px-2 text-[13px]",
                    active
                      ? "bg-surface-2 text-fg font-medium"
                      : "text-fg-muted hover:bg-surface-2 hover:text-fg",
                  )}
                >
                  <item.icon className="size-3.5 shrink-0 opacity-70" aria-hidden />
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="border-border text-2xs text-fg-faint border-t px-4 py-2">Threadline · internal</div>
    </aside>
  );
}
