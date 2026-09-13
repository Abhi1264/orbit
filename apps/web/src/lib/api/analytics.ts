"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { components } from "./schema";

export type Schemas = components["schemas"];
export type MetricQuery = Schemas["MetricQuery"];
export type MetricQueryResult = Schemas["MetricQueryResult"];
export type Filter = Schemas["Filter"];
export type FunnelQuery = Schemas["FunnelQuery"];
export type FunnelResult = Schemas["FunnelResult"];
export type CohortQuery = Schemas["CohortQuery"];
export type CohortResult = Schemas["CohortResult"];
export type AnalyticsMeta = Schemas["AnalyticsMeta"];
export type MetricInfo = Schemas["MetricInfo"];
export type DimensionInfo = Schemas["DimensionInfo"];
export type SegmentOut = Schemas["SegmentOut"];
export type SegmentCreate = Schemas["SegmentCreate"];
export type SavedAnalysisOut = Schemas["SavedAnalysisOut"];
export type SavedAnalysisCreate = Schemas["SavedAnalysisCreate"];

export function useAnalyticsMeta() {
  return useQuery({
    queryKey: ["analytics", "meta"],
    queryFn: async () => unwrap(await api.GET("/api/analytics/meta")),
    staleTime: 30 * 60_000,
  });
}

export function useMetricQuery(q: MetricQuery | null) {
  return useQuery({
    queryKey: ["analytics", "query", q],
    queryFn: async () => unwrap(await api.POST("/api/analytics/query", { body: q! })),
    enabled: q !== null,
    placeholderData: (prev) => prev,
  });
}

export function useFunnel(q: FunnelQuery | null) {
  return useQuery({
    queryKey: ["analytics", "funnel", q],
    queryFn: async () => unwrap(await api.POST("/api/analytics/funnel", { body: q! })),
    enabled: q !== null,
    placeholderData: (prev) => prev,
  });
}

export function useCohort(q: CohortQuery | null) {
  return useQuery({
    queryKey: ["analytics", "cohort", q],
    queryFn: async () => unwrap(await api.POST("/api/analytics/cohort", { body: q! })),
    enabled: q !== null,
    placeholderData: (prev) => prev,
  });
}

export function useOverview(
  params: {
    date_from: string;
    date_to: string;
    compare_from?: string | null;
    compare_to?: string | null;
  } | null,
) {
  return useQuery({
    queryKey: ["analytics", "overview", params],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/analytics/overview", {
          params: {
            query: {
              date_from: params!.date_from,
              date_to: params!.date_to,
              compare_from: params!.compare_from ?? undefined,
              compare_to: params!.compare_to ?? undefined,
            },
          },
        }),
      ),
    enabled: params !== null,
    placeholderData: (prev) => prev,
  });
}

export function useInventoryRisk(asOf: string | undefined) {
  return useQuery({
    queryKey: ["analytics", "inventory", asOf],
    queryFn: async () =>
      unwrap(await api.GET("/api/analytics/inventory-risk", { params: { query: { as_of: asOf! } } })),
    enabled: !!asOf,
  });
}

export function useSegments() {
  return useQuery({
    queryKey: ["segments"],
    queryFn: async () => unwrap(await api.GET("/api/segments")),
  });
}

export function useSegmentPreview(body: Schemas["SegmentPreviewRequest"] | null) {
  return useQuery({
    queryKey: ["segments", "preview", body],
    queryFn: async () => unwrap(await api.POST("/api/segments/preview", { body: body! })),
    enabled: body !== null && (body.conditions?.length ?? 0) > 0,
    placeholderData: (prev) => prev,
  });
}

export function useSegmentMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["segments"] });
  const create = useMutation({
    mutationFn: async (body: SegmentCreate) => unwrap(await api.POST("/api/segments", { body })),
    onSuccess: invalidate,
  });
  const update = useMutation({
    mutationFn: async ({ id, body }: { id: number; body: SegmentCreate }) =>
      unwrap(await api.PUT("/api/segments/{segment_id}", { params: { path: { segment_id: id } }, body })),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: async (id: number) => {
      const r = await api.DELETE("/api/segments/{segment_id}", { params: { path: { segment_id: id } } });
      if (r.error) throw r.error;
    },
    onSuccess: invalidate,
  });
  return { create, update, remove };
}

export function useSavedAnalyses() {
  return useQuery({
    queryKey: ["saved-analyses"],
    queryFn: async () => unwrap(await api.GET("/api/saved-analyses")),
  });
}

export function useSavedAnalysisMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["saved-analyses"] });
  const create = useMutation({
    mutationFn: async (body: SavedAnalysisCreate) => unwrap(await api.POST("/api/saved-analyses", { body })),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: async (id: number) => {
      const r = await api.DELETE("/api/saved-analyses/{analysis_id}", {
        params: { path: { analysis_id: id } },
      });
      if (r.error) throw r.error;
    },
    onSuccess: invalidate,
  });
  return { create, remove };
}
