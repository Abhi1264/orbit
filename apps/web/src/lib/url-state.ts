"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

/**
 * Read/write view state in the URL so every analysis is a shareable link.
 * Values are strings; callers parse. JSON-valued keys should be encoded by the caller.
 */
export function useUrlState() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const set = useCallback(
    (patch: Record<string, string | null | undefined>) => {
      const sp = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v === null || v === undefined || v === "") sp.delete(k);
        else sp.set(k, v);
      }
      router.replace(`${pathname}?${sp.toString()}` as "/", { scroll: false });
    },
    [params, pathname, router],
  );

  const get = useCallback((key: string) => params.get(key), [params]);

  const getJson = useCallback(
    <T,>(key: string, fallback: T): T => {
      const raw = params.get(key);
      if (!raw) return fallback;
      try {
        return JSON.parse(raw) as T;
      } catch {
        return fallback;
      }
    },
    [params],
  );

  return { get, getJson, set, params };
}
