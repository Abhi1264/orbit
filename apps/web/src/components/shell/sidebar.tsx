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

const GROUPS: {
  label: string;
  items: { href: string; label: string; icon: React.ComponentType<{ className?: string }> }[];
}[] = [
  {
    label: "Observe",
    items: [
      { href: "/", label: "Overview", icon: Gauge },
      { href: "/analytics", label: "Analytics", icon: Activity },
      { href: "/funnels", label: "Funnels", icon: Filter },
      { href: "/cohorts", label: "Cohorts", icon: Grid3x3 },
      { href: "/segments", label: "Segments", icon: Users },
    ],
  },
  {
    label: "Experiment",
    items: [
      { href: "/experiments", label: "Experiments", icon: Beaker },
      { href: "/investigations", label: "Investigations", icon: Search },
      { href: "/analyst", label: "Analyst", icon: MessageSquareText },
    ],
  },
  {
    label: "Operate",
    items: [
      { href: "/ops", label: "Product Ops", icon: BookOpen },
      { href: "/releases", label: "Releases", icon: Rocket },
      { href: "/decisions", label: "Decisions", icon: LayoutList },
    ],
  },
];

function NavLink({
  href,
  label,
  icon: Icon,
}: {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}) {
  const pathname = usePathname();
  const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
  return (
    <Link
      href={href as "/"}
      aria-current={active ? "page" : undefined}
      title={label}
      className={cn(
        "flex h-11 items-center gap-2 rounded-sm px-2 text-[13px] transition-colors duration-150 md:h-8",
        "max-md:justify-center",
        active ? "bg-surface-2 text-fg font-medium" : "text-fg-muted hover:bg-surface-2 hover:text-fg",
      )}
    >
      <Icon
        className={cn("size-4 shrink-0 md:size-3.5", active ? "text-fg" : "text-fg-subtle")}
        aria-hidden
      />
      <span className="truncate max-md:sr-only">{label}</span>
    </Link>
  );
}

export function Sidebar() {
  return (
    <aside className="border-border bg-bg flex h-screen w-14 shrink-0 flex-col border-r md:w-56">
      <Link href="/" className="flex h-12 items-center gap-2 px-2 md:px-3">
        <span className="bg-accent text-accent-foreground mx-auto flex size-5 items-center justify-center rounded-sm text-[11px] font-semibold md:mx-0">
          O
        </span>
        <span className="hidden text-sm font-semibold tracking-tight md:inline">Orbit</span>
      </Link>
      <nav aria-label="Primary" className="flex-1 overflow-y-auto px-2 pb-2">
        {GROUPS.map((group, i) => (
          <div key={group.label}>
            <p className={cn("text-fg-faint hidden px-2 pb-1 text-xs md:block", i === 0 ? "pt-1" : "pt-3")}>
              {group.label}
            </p>
            <ul className="flex flex-col gap-0.5">
              {group.items.map((item) => (
                <li key={item.href}>
                  <NavLink {...item} />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
      <div className="border-border border-t p-2">
        <NavLink href="/settings" label="Settings" icon={Settings} />
        <p className="text-fg-faint hidden px-2 pt-2 text-xs md:block">Threadline</p>
      </div>
    </aside>
  );
}
