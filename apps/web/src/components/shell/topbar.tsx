"use client";

import { ChevronDown } from "lucide-react";

import { CommandPalette } from "@/components/shell/command-palette";
import { DateRangePicker } from "@/components/shell/date-range-picker";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/menu";
import { useLogout, useMe } from "@/lib/api/hooks";

export function Topbar({
  dataStart,
  dataEnd,
  projectName,
  children,
}: {
  dataStart?: string;
  dataEnd?: string;
  projectName?: string;
  children?: React.ReactNode;
}) {
  const me = useMe();
  const logout = useLogout();

  return (
    <header className="border-border bg-bg flex h-12 shrink-0 items-center justify-between gap-3 border-b px-4">
      <div className="flex items-center gap-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" aria-label="Project">
              <span className="text-fg font-medium">{projectName ?? "Threadline"}</span>
              <ChevronDown className="text-fg-subtle size-3.5" aria-hidden />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuLabel>Projects</DropdownMenuLabel>
            <DropdownMenuItem>{projectName ?? "Threadline"}</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <div className="flex items-center gap-2">
        <CommandPalette />
        {children}
        <DateRangePicker dataStart={dataStart} dataEnd={dataEnd} />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" aria-label="Account menu">
              <span className="bg-surface-2 text-2xs flex size-5 items-center justify-center rounded-full font-medium uppercase">
                {me.data?.name?.[0] ?? "·"}
              </span>
              <span className="max-w-32 truncate">{me.data?.name ?? ""}</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuLabel>
              <div className="text-fg">{me.data?.name}</div>
              <div className="text-2xs font-mono">{me.data?.email}</div>
              <div className="mt-0.5 capitalize">{me.data?.role}</div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => logout.mutate()}>Sign out</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
