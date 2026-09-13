"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { Schemas } from "./analytics";
import { api, unwrap } from "./client";

export type AskRequest = Schemas["AskRequest"];
export type AskContext = Schemas["AskContext"];
export type AskResponse = Schemas["AskResponse"];
export type AnalystAnswer = Schemas["AnalystAnswer"];
export type ToolCallRecord = Schemas["ToolCallRecord"];
export type Fact = Schemas["Fact"];
export type Inference = Schemas["Inference"];
export type CandidateOut = Schemas["CandidateOut"];
export type RecommendationItem = Schemas["RecommendationItem"];
export type AiRunSummary = Schemas["AiRunSummary"];
export type PlanRequest = Schemas["PlanRequest"];
export type PlanResponse = Schemas["PlanResponse"];
export type Suggestion = Schemas["Suggestion"];

export function useAnalystStatus() {
  return useQuery({
    queryKey: ["ai", "status"],
    queryFn: async () => unwrap(await api.GET("/api/ai/status")),
    staleTime: 10 * 60_000,
  });
}

export function useSuggestions(ctx: {
  metric?: string | null;
  experiment_id?: number;
  investigation_id?: number;
}) {
  return useQuery({
    queryKey: ["ai", "suggestions", ctx],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/ai/suggestions", {
          params: {
            query: {
              metric: ctx.metric ?? undefined,
              experiment_id: ctx.experiment_id,
              investigation_id: ctx.investigation_id,
            },
          },
        }),
      ),
    staleTime: 10 * 60_000,
  });
}

export function useAsk() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: AskRequest) => unwrap(await api.POST("/api/ai/ask", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ai", "runs"] }),
  });
}

export function usePlan() {
  return useMutation({
    mutationFn: async (body: PlanRequest) => unwrap(await api.POST("/api/ai/plan", { body })),
  });
}

export function useRuns(limit = 20) {
  return useQuery({
    queryKey: ["ai", "runs", limit],
    queryFn: async () => unwrap(await api.GET("/api/ai/runs", { params: { query: { limit } } })),
  });
}

export function useRun(id: number | null) {
  return useQuery({
    queryKey: ["ai", "run", id],
    queryFn: async () =>
      unwrap(await api.GET("/api/ai/runs/{run_id}", { params: { path: { run_id: id! } } })),
    enabled: id !== null,
    staleTime: Infinity,
  });
}
