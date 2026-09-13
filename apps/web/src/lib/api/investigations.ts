"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { Schemas } from "./analytics";
import { api, unwrap } from "./client";

export type AnomalyOut = Schemas["AnomalyOut"];
export type AnomalyStatus = Schemas["AnomalyStatus"];
export type InvestigationSummary = Schemas["InvestigationSummary"];
export type InvestigationOut = Schemas["InvestigationOut"];
export type InvestigationCreate = Schemas["InvestigationCreate"];
export type InvestigationUpdate = Schemas["InvestigationUpdate"];
export type InvestigationStatus = Schemas["InvestigationStatus"];
export type FindingOut = Schemas["FindingOut"];
export type FindingCreate = Schemas["FindingCreate"];
export type FindingUpdate = Schemas["FindingUpdate"];
export type FindingKind = Schemas["FindingKind"];
export type ActionOut = Schemas["ActionOut"];
export type ActionCreate = Schemas["ActionCreate"];
export type ActionUpdate = Schemas["ActionUpdate"];
export type RootCauseAnalysis = Schemas["RootCauseAnalysis"];
export type RootCauseCandidate = Schemas["Candidate"];
export type Contribution = Schemas["Contribution"];
export type CommentOut = Schemas["CommentOut"];
export type EntityType = Schemas["EntityType"];
export type StakeholderOut = Schemas["StakeholderOut"];

// --------------------------------------------------------------------------- anomalies

export function useAnomalies(status?: AnomalyStatus | "all") {
  return useQuery({
    queryKey: ["anomalies", status ?? "all"],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/anomalies", {
          params: { query: status && status !== "all" ? { status } : {} },
        }),
      ),
  });
}

export function useAnomaly(id: number | null) {
  return useQuery({
    queryKey: ["anomalies", "one", id],
    queryFn: async () =>
      unwrap(await api.GET("/api/anomalies/{anomaly_id}", { params: { path: { anomaly_id: id! } } })),
    enabled: id !== null,
  });
}

export function useAnomalyMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["anomalies"] });
  const setStatus = useMutation({
    mutationFn: async ({ id, status }: { id: number; status: AnomalyStatus }) =>
      unwrap(
        await api.PATCH("/api/anomalies/{anomaly_id}", {
          params: { path: { anomaly_id: id } },
          body: { status },
        }),
      ),
    onSuccess: invalidate,
  });
  const detect = useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/anomalies/detect")),
    onSuccess: invalidate,
  });
  return { setStatus, detect };
}

// --------------------------------------------------------------------------- investigations

export function useInvestigations(status?: InvestigationStatus | "all") {
  return useQuery({
    queryKey: ["investigations", status ?? "all"],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/investigations", {
          params: { query: status && status !== "all" ? { status } : {} },
        }),
      ),
  });
}

export function useInvestigation(id: number | null) {
  return useQuery({
    queryKey: ["investigations", "one", id],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/investigations/{investigation_id}", {
          params: { path: { investigation_id: id! } },
        }),
      ),
    enabled: id !== null,
  });
}

export function useRootCause(id: number | null) {
  return useQuery({
    queryKey: ["investigations", "root-cause", id],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/investigations/{investigation_id}/root-cause", {
          params: { path: { investigation_id: id! } },
        }),
      ),
    enabled: id !== null,
    staleTime: 10 * 60_000,
  });
}

export function useInvestigationMutations(id?: number) {
  const qc = useQueryClient();
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["investigations"] });
    void qc.invalidateQueries({ queryKey: ["anomalies"] });
  };
  const path = (investigation_id: number) => ({ params: { path: { investigation_id } } });

  const create = useMutation({
    mutationFn: async (body: InvestigationCreate) => unwrap(await api.POST("/api/investigations", { body })),
    onSuccess: invalidate,
  });
  const update = useMutation({
    mutationFn: async (body: InvestigationUpdate) =>
      unwrap(await api.PATCH("/api/investigations/{investigation_id}", { ...path(id!), body })),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: async (investigation_id: number) => {
      const r = await api.DELETE("/api/investigations/{investigation_id}", path(investigation_id));
      if (r.error) throw r.error;
    },
    onSuccess: invalidate,
  });
  const addFinding = useMutation({
    mutationFn: async (body: FindingCreate) =>
      unwrap(await api.POST("/api/investigations/{investigation_id}/findings", { ...path(id!), body })),
    onSuccess: invalidate,
  });
  const updateFinding = useMutation({
    mutationFn: async ({ finding_id, body }: { finding_id: number; body: FindingUpdate }) =>
      unwrap(
        await api.PATCH("/api/investigations/{investigation_id}/findings/{finding_id}", {
          params: { path: { investigation_id: id!, finding_id } },
          body,
        }),
      ),
    onSuccess: invalidate,
  });
  const deleteFinding = useMutation({
    mutationFn: async (finding_id: number) => {
      const r = await api.DELETE("/api/investigations/{investigation_id}/findings/{finding_id}", {
        params: { path: { investigation_id: id!, finding_id } },
      });
      if (r.error) throw r.error;
    },
    onSuccess: invalidate,
  });
  const addAction = useMutation({
    mutationFn: async (body: ActionCreate) =>
      unwrap(await api.POST("/api/investigations/{investigation_id}/actions", { ...path(id!), body })),
    onSuccess: invalidate,
  });
  const updateAction = useMutation({
    mutationFn: async ({ action_id, body }: { action_id: number; body: ActionUpdate }) =>
      unwrap(
        await api.PATCH("/api/investigations/{investigation_id}/actions/{action_id}", {
          params: { path: { investigation_id: id!, action_id } },
          body,
        }),
      ),
    onSuccess: invalidate,
  });
  const deleteAction = useMutation({
    mutationFn: async (action_id: number) => {
      const r = await api.DELETE("/api/investigations/{investigation_id}/actions/{action_id}", {
        params: { path: { investigation_id: id!, action_id } },
      });
      if (r.error) throw r.error;
    },
    onSuccess: invalidate,
  });
  const setStakeholders = useMutation({
    mutationFn: async (body: Schemas["StakeholderAssignment"][]) =>
      unwrap(await api.PUT("/api/investigations/{investigation_id}/stakeholders", { ...path(id!), body })),
    onSuccess: invalidate,
  });
  return {
    create,
    update,
    remove,
    addFinding,
    updateFinding,
    deleteFinding,
    addAction,
    updateAction,
    deleteAction,
    setStakeholders,
  };
}

export function useStakeholders() {
  return useQuery({
    queryKey: ["stakeholders"],
    queryFn: async () => unwrap(await api.GET("/api/stakeholders")),
    staleTime: 30 * 60_000,
  });
}

// --------------------------------------------------------------------------- comments

export function useComments(entityType: EntityType, entityId: number | null) {
  return useQuery({
    queryKey: ["comments", entityType, entityId],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/comments/{entity_type}/{entity_id}", {
          params: { path: { entity_type: entityType, entity_id: entityId! } },
        }),
      ),
    enabled: entityId !== null,
  });
}

export function useCommentMutations(entityType: EntityType, entityId: number) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["comments", entityType, entityId] });
  const add = useMutation({
    mutationFn: async (body: string) =>
      unwrap(
        await api.POST("/api/comments/{entity_type}/{entity_id}", {
          params: { path: { entity_type: entityType, entity_id: entityId } },
          body: { body },
        }),
      ),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: async (comment_id: number) => {
      const r = await api.DELETE("/api/comments/{comment_id}", { params: { path: { comment_id } } });
      if (r.error) throw r.error;
    },
    onSuccess: invalidate,
  });
  return { add, remove };
}
