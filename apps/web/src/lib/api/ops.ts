"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { Schemas } from "./analytics";
import { api, unwrap } from "./client";

export type ReleaseSummary = Schemas["ReleaseSummary"];
export type ReleaseOut = Schemas["ReleaseOut"];
export type ReleaseCreate = Schemas["ReleaseCreate"];
export type ReleaseUpdate = Schemas["ReleaseUpdate"];
export type ReleaseStatus = Schemas["ReleaseStatus"];
export type ReleaseImpact = Schemas["ReleaseImpact"];
export type ImpactMetric = Schemas["ImpactMetric"];
export type ReleaseEventOut = Schemas["ReleaseEventOut"];
export type ChecklistOut = Schemas["ChecklistOut"];
export type ChecklistItem = Schemas["ChecklistItem"];
export type SopOut = Schemas["SopOut"];
export type SopCreate = Schemas["SopCreate"];
export type SopItem = Schemas["SopItem"];
export type KnowledgeSummary = Schemas["KnowledgeSummary"];
export type KnowledgeOut = Schemas["KnowledgeOut"];
export type KnowledgeCreate = Schemas["KnowledgeCreate"];
export type KnowledgeUpdate = Schemas["KnowledgeUpdate"];
export type FeedbackOut = Schemas["FeedbackOut"];
export type FeedbackCreate = Schemas["FeedbackCreate"];
export type FeedbackUpdate = Schemas["FeedbackUpdate"];
export type FeedbackStatus = Schemas["FeedbackStatus"];
export type FeedbackSource = Schemas["FeedbackSource"];
export type FeedbackSentiment = Schemas["FeedbackSentiment"];
export type ThemeSummary = Schemas["ThemeSummary"];
export type StakeholderRef = Schemas["StakeholderRef"];
export type DecisionSummary = Schemas["DecisionSummary"];
export type DecisionOut = Schemas["DecisionOut"];
export type DecisionCreate = Schemas["DecisionCreate"];
export type DecisionUpdate = Schemas["DecisionUpdate"];
export type DecisionStatus = Schemas["DecisionStatus"];
export type EntityRef = Schemas["EntityRef"];
export type SearchResponse = Schemas["SearchResponse"];
export type SearchHit = Schemas["SearchHit"];

// --------------------------------------------------------------------------- releases

export function useReleases(filters: { platform?: string; status?: ReleaseStatus } = {}) {
  return useQuery({
    queryKey: ["releases", filters],
    queryFn: async () => unwrap(await api.GET("/api/releases", { params: { query: filters } })),
  });
}

export function useRelease(id: number) {
  return useQuery({
    queryKey: ["releases", "one", id],
    queryFn: async () =>
      unwrap(await api.GET("/api/releases/{release_id}", { params: { path: { release_id: id } } })),
  });
}

export function useReleaseImpact(id: number, enabled = true) {
  return useQuery({
    queryKey: ["releases", "impact", id],
    queryFn: async () =>
      unwrap(await api.GET("/api/releases/{release_id}/impact", { params: { path: { release_id: id } } })),
    enabled,
    staleTime: 10 * 60_000,
  });
}

export function useReleaseMutations(id?: number) {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["releases"] });
    qc.invalidateQueries({ queryKey: ["ops", "checklists"] });
  };
  const create = useMutation({
    mutationFn: async (body: ReleaseCreate) => unwrap(await api.POST("/api/releases", { body })),
    onSuccess: invalidate,
  });
  const update = useMutation({
    mutationFn: async (body: ReleaseUpdate) =>
      unwrap(await api.PATCH("/api/releases/{release_id}", { params: { path: { release_id: id! } }, body })),
    onSuccess: invalidate,
  });
  const addNote = useMutation({
    mutationFn: async (note: string) =>
      unwrap(
        await api.POST("/api/releases/{release_id}/events", {
          params: { path: { release_id: id! } },
          body: { note, kind: "note" },
        }),
      ),
    onSuccess: invalidate,
  });
  const runSop = useMutation({
    mutationFn: async (sopId: number) =>
      unwrap(
        await api.POST("/api/releases/{release_id}/checklists", {
          params: { path: { release_id: id! }, query: { sop_id: sopId } },
        }),
      ),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: async () =>
      unwrap(await api.DELETE("/api/releases/{release_id}", { params: { path: { release_id: id! } } })),
    onSuccess: invalidate,
  });
  return { create, update, addNote, runSop, remove };
}

// --------------------------------------------------------------------------- SOPs & checklists

export function useSops() {
  return useQuery({
    queryKey: ["ops", "sops"],
    queryFn: async () => unwrap(await api.GET("/api/ops/sops")),
  });
}

export function useChecklists(filters: { status?: Schemas["ChecklistStatus"]; release_id?: number } = {}) {
  return useQuery({
    queryKey: ["ops", "checklists", filters],
    queryFn: async () => unwrap(await api.GET("/api/ops/checklists", { params: { query: filters } })),
  });
}

export function useOpsMutations() {
  const qc = useQueryClient();
  const invalidateOps = () => qc.invalidateQueries({ queryKey: ["ops"] });
  const createSop = useMutation({
    mutationFn: async (body: SopCreate) => unwrap(await api.POST("/api/ops/sops", { body })),
    onSuccess: invalidateOps,
  });
  const startChecklist = useMutation({
    mutationFn: async (body: Schemas["ChecklistCreate"]) =>
      unwrap(await api.POST("/api/ops/checklists", { body })),
    onSuccess: () => {
      invalidateOps();
      qc.invalidateQueries({ queryKey: ["releases"] });
    },
  });
  const toggleItem = useMutation({
    mutationFn: async (args: { checklistId: number; key: string; done: boolean }) =>
      unwrap(
        await api.PATCH("/api/ops/checklists/{checklist_id}/items/{key}", {
          params: { path: { checklist_id: args.checklistId, key: args.key } },
          body: { done: args.done },
        }),
      ),
    onSuccess: () => {
      invalidateOps();
      qc.invalidateQueries({ queryKey: ["releases"] });
    },
  });
  const createDoc = useMutation({
    mutationFn: async (body: KnowledgeCreate) => unwrap(await api.POST("/api/ops/knowledge", { body })),
    onSuccess: invalidateOps,
  });
  const updateDoc = useMutation({
    mutationFn: async (args: { id: number; body: KnowledgeUpdate }) =>
      unwrap(
        await api.PATCH("/api/ops/knowledge/{doc_id}", {
          params: { path: { doc_id: args.id } },
          body: args.body,
        }),
      ),
    onSuccess: invalidateOps,
  });
  const removeDoc = useMutation({
    mutationFn: async (id: number) =>
      unwrap(await api.DELETE("/api/ops/knowledge/{doc_id}", { params: { path: { doc_id: id } } })),
    onSuccess: invalidateOps,
  });
  const createFeedback = useMutation({
    mutationFn: async (body: FeedbackCreate) => unwrap(await api.POST("/api/ops/feedback", { body })),
    onSuccess: invalidateOps,
  });
  const updateFeedback = useMutation({
    mutationFn: async (args: { id: number; body: FeedbackUpdate }) =>
      unwrap(
        await api.PATCH("/api/ops/feedback/{feedback_id}", {
          params: { path: { feedback_id: args.id } },
          body: args.body,
        }),
      ),
    onSuccess: invalidateOps,
  });
  return {
    createSop,
    startChecklist,
    toggleItem,
    createDoc,
    updateDoc,
    removeDoc,
    createFeedback,
    updateFeedback,
  };
}

// --------------------------------------------------------------------------- knowledge

export function useKnowledge(filters: { tag?: string; q?: string } = {}) {
  return useQuery({
    queryKey: ["ops", "knowledge", filters],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/ops/knowledge", {
          params: { query: { ...filters, q: filters.q && filters.q.length >= 2 ? filters.q : undefined } },
        }),
      ),
  });
}

export function useKnowledgeDoc(id: number | null) {
  return useQuery({
    queryKey: ["ops", "knowledge", "one", id],
    queryFn: async () =>
      unwrap(await api.GET("/api/ops/knowledge/{doc_id}", { params: { path: { doc_id: id! } } })),
    enabled: id !== null,
  });
}

// --------------------------------------------------------------------------- feedback

export function useFeedback(
  filters: {
    status?: FeedbackStatus;
    theme?: string;
    open_only?: boolean;
    linked_type?: string;
    linked_id?: number;
  } = {},
) {
  return useQuery({
    queryKey: ["ops", "feedback", filters],
    queryFn: async () => unwrap(await api.GET("/api/ops/feedback", { params: { query: filters } })),
  });
}

export function useFeedbackThemes() {
  return useQuery({
    queryKey: ["ops", "feedback", "themes"],
    queryFn: async () => unwrap(await api.GET("/api/ops/feedback/themes")),
  });
}

export function useStakeholders() {
  return useQuery({
    queryKey: ["ops", "stakeholders"],
    queryFn: async () => unwrap(await api.GET("/api/ops/feedback/stakeholders")),
    staleTime: 10 * 60_000,
  });
}

// --------------------------------------------------------------------------- decisions

export function useDecisions(
  filters: {
    status?: DecisionStatus;
    experiment_id?: number;
    investigation_id?: number;
    release_id?: number;
    due_only?: boolean;
  } = {},
) {
  return useQuery({
    queryKey: ["decisions", filters],
    queryFn: async () => unwrap(await api.GET("/api/decisions", { params: { query: filters } })),
  });
}

export function useDecision(id: number | null) {
  return useQuery({
    queryKey: ["decisions", "one", id],
    queryFn: async () =>
      unwrap(await api.GET("/api/decisions/{decision_id}", { params: { path: { decision_id: id! } } })),
    enabled: id !== null,
  });
}

export function useDecisionMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["decisions"] });
  const create = useMutation({
    mutationFn: async (body: DecisionCreate) => unwrap(await api.POST("/api/decisions", { body })),
    onSuccess: invalidate,
  });
  const update = useMutation({
    mutationFn: async (args: { id: number; body: DecisionUpdate }) =>
      unwrap(
        await api.PATCH("/api/decisions/{decision_id}", {
          params: { path: { decision_id: args.id } },
          body: args.body,
        }),
      ),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: async (id: number) =>
      unwrap(await api.DELETE("/api/decisions/{decision_id}", { params: { path: { decision_id: id } } })),
    onSuccess: invalidate,
  });
  return { create, update, remove };
}

// --------------------------------------------------------------------------- search

export function useSearch(q: string, enabled = true) {
  return useQuery({
    queryKey: ["search", q],
    queryFn: async () => unwrap(await api.GET("/api/search", { params: { query: { q, limit: 5 } } })),
    enabled: enabled && q.trim().length >= 2,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });
}
