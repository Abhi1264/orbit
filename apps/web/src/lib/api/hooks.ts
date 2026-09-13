"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { api, unwrap } from "./client";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async () => unwrap(await api.GET("/api/auth/me")),
    staleTime: 5 * 60_000,
  });
}

export function useUsers() {
  return useQuery({
    queryKey: ["users"],
    queryFn: async () => unwrap(await api.GET("/api/auth/users")),
    staleTime: 10 * 60_000,
  });
}

export function useLogout() {
  const router = useRouter();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await api.POST("/api/auth/logout");
    },
    onSuccess: () => {
      qc.clear();
      router.push("/login");
    },
  });
}

export function usePermission(permission: string) {
  const me = useMe();
  return me.data?.permissions.includes(permission as never) ?? false;
}
