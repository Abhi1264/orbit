"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { components } from "./schema";

export type UserAdminOut = components["schemas"]["UserAdminOut"];
export type UserCreate = components["schemas"]["UserCreate"];
export type UserUpdate = components["schemas"]["UserUpdate"];
export type RolePermissions = components["schemas"]["RolePermissions"];
export type SystemStatus = components["schemas"]["SystemStatus"];
export type Role = components["schemas"]["Role"];

export function useRoles() {
  return useQuery({
    queryKey: ["roles"],
    queryFn: async () => unwrap(await api.GET("/api/auth/roles")),
    staleTime: Infinity,
  });
}

export function useAdminUsers(enabled: boolean) {
  return useQuery({
    queryKey: ["admin", "users"],
    queryFn: async () => unwrap(await api.GET("/api/auth/admin/users")),
    enabled,
  });
}

export function useAdminUserMutations() {
  const qc = useQueryClient();
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["admin", "users"] });
    void qc.invalidateQueries({ queryKey: ["users"] });
  };
  const create = useMutation({
    mutationFn: async (body: UserCreate) => unwrap(await api.POST("/api/auth/admin/users", { body })),
    onSuccess: invalidate,
  });
  const update = useMutation({
    mutationFn: async ({ id, ...body }: UserUpdate & { id: number }) =>
      unwrap(await api.PATCH("/api/auth/admin/users/{user_id}", { params: { path: { user_id: id } }, body })),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: async (id: number) => {
      unwrap(await api.DELETE("/api/auth/admin/users/{user_id}", { params: { path: { user_id: id } } }));
    },
    onSuccess: invalidate,
  });
  return { create, update, remove };
}

export function useChangePassword() {
  return useMutation({
    mutationFn: async (body: { current_password: string; new_password: string }) => {
      unwrap(await api.POST("/api/auth/password", { body }));
    },
  });
}

export function useSystemStatus() {
  return useQuery({
    queryKey: ["system", "status"],
    queryFn: async () => unwrap(await api.GET("/api/system/status")),
    refetchInterval: 30_000,
  });
}
