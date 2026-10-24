"use client";

import { Sidebar } from "@/components/shell/sidebar";
import { Topbar } from "@/components/shell/topbar";
import { useAnalyticsMeta } from "@/lib/api/analytics";

export function AppShell({ children }: { children: React.ReactNode }) {
  const meta = useAnalyticsMeta();
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar dataStart={meta.data?.data_start ?? undefined} dataEnd={meta.data?.data_end ?? undefined} />
        <main id="main" className="bg-surface flex-1 overflow-y-auto px-4 py-4 md:px-6 md:py-5">
          {children}
        </main>
      </div>
    </div>
  );
}
