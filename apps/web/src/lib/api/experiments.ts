"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { Schemas } from "./analytics";
import { api, unwrap } from "./client";

export type ExperimentSummary = Schemas["ExperimentSummary"];
export type ExperimentOut = Schemas["ExperimentOut"];
export type ExperimentCreate = Schemas["ExperimentCreate"];
export type ExperimentUpdate = Schemas["ExperimentUpdate"];
export type ExperimentStatus = Schemas["ExperimentStatus"];
export type ExperimentDecision = Schemas["ExperimentDecision"];
export type VariantIn = Schemas["VariantIn"];
export type ExperimentResults = Schemas["ExperimentResults"];
export type MetricReadout = Schemas["MetricReadout"];
export type VariantComparison = Schemas["VariantComparison"];
export type SegmentReadout = Schemas["SegmentReadout"];
export type Recommendation = Schemas["Recommendation"];
export type Check = Schemas["Check"];
export type DecisionIn = Schemas["DecisionIn"];

export function useExperiments(status?: ExperimentStatus | "all") {
  return useQuery({
    queryKey: ["experiments", status ?? "all"],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/experiments", {
          params: { query: status && status !== "all" ? { status } : {} },
        }),
      ),
  });
}

export function useExperiment(id: number) {
  return useQuery({
    queryKey: ["experiments", "one", id],
    queryFn: async () =>
      unwrap(await api.GET("/api/experiments/{experiment_id}", { params: { path: { experiment_id: id } } })),
  });
}

export function useExperimentResults(id: number, enabled = true) {
  return useQuery({
    queryKey: ["experiments", "results", id],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/experiments/{experiment_id}/results", {
          params: { path: { experiment_id: id } },
        }),
      ),
    enabled,
    staleTime: 5 * 60 * 1000,
  });
}

export function useExperimentMemo(id: number, enabled: boolean) {
  return useQuery({
    queryKey: ["experiments", "memo", id],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/experiments/{experiment_id}/memo", { params: { path: { experiment_id: id } } }),
      ),
    enabled,
    staleTime: 5 * 60 * 1000,
  });
}

export function useExperimentMutations(id?: number) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["experiments"] });
  const create = useMutation({
    mutationFn: async (body: ExperimentCreate) => unwrap(await api.POST("/api/experiments", { body })),
    onSuccess: invalidate,
  });
  const update = useMutation({
    mutationFn: async (body: ExperimentUpdate) =>
      unwrap(
        await api.PATCH("/api/experiments/{experiment_id}", {
          params: { path: { experiment_id: id! } },
          body,
        }),
      ),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.DELETE("/api/experiments/{experiment_id}", { params: { path: { experiment_id: id! } } }),
      ),
    onSuccess: invalidate,
  });
  const decide = useMutation({
    mutationFn: async (body: DecisionIn) =>
      unwrap(
        await api.POST("/api/experiments/{experiment_id}/decision", {
          params: { path: { experiment_id: id! } },
          body,
        }),
      ),
    onSuccess: () => {
      invalidate();
      qc.invalidateQueries({ queryKey: ["decisions"] });
    },
  });
  return { create, update, remove, decide };
}
