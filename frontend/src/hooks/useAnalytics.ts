// src/hooks/useAnalytics.ts
// TanStack Query hooks for analytics data and CSV export download.
// All types imported from generated schema — no manual duplication (tighten-types D4).
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  fetchVolume,
  fetchDistribution,
  fetchAccuracy,
  fetchRouting,
  exportAnalyticsCsv,
} from "@/api/analytics";
import type {
  VolumeResponse,
  ClassificationDistributionResponse,
  AccuracyResponse,
  RoutingResponse,
} from "@/types/generated/api";

// ─────────────────────────────────────────────────────────────────────────────
// Query hooks
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch email volume time series for a date range.
 *
 * Query key: ["analytics", "volume", startDate, endDate]
 * Re-fetches automatically when dates change.
 */
export function useVolume(startDate: string, endDate: string) {
  return useQuery<VolumeResponse>({
    queryKey: ["analytics", "volume", startDate, endDate],
    queryFn: () => fetchVolume(startDate, endDate),
  });
}

/**
 * Fetch classification action/type distribution for a date range.
 *
 * Query key: ["analytics", "distribution", startDate, endDate]
 * Re-fetches automatically when dates change.
 */
export function useDistribution(startDate: string, endDate: string) {
  return useQuery<ClassificationDistributionResponse>({
    queryKey: ["analytics", "distribution", startDate, endDate],
    queryFn: () => fetchDistribution(startDate, endDate),
  });
}

/**
 * Fetch classification accuracy for a date range.
 *
 * Query key: ["analytics", "accuracy", startDate, endDate]
 * Re-fetches automatically when dates change.
 */
export function useAccuracy(startDate: string, endDate: string) {
  return useQuery<AccuracyResponse>({
    queryKey: ["analytics", "accuracy", startDate, endDate],
    queryFn: () => fetchAccuracy(startDate, endDate),
  });
}

/**
 * Fetch per-channel routing stats for a date range.
 *
 * Query key: ["analytics", "routing", startDate, endDate]
 * Re-fetches automatically when dates change.
 */
export function useRoutingAnalytics(startDate: string, endDate: string) {
  return useQuery<RoutingResponse>({
    queryKey: ["analytics", "routing", startDate, endDate],
    queryFn: () => fetchRouting(startDate, endDate),
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// CSV export mutation
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Returns a mutation that downloads the analytics CSV for the given date range.
 *
 * On success:
 *   1. Creates an object URL from the Blob response.
 *   2. Triggers a file download via a dynamically created <a> element.
 *   3. Revokes the object URL to free memory.
 *
 * Usage:
 *   const exportCsv = useExportCsv();
 *   exportCsv.mutate({ startDate: "2026-01-01", endDate: "2026-01-31" });
 */
export function useExportCsv() {
  return useMutation<void, Error, { startDate: string; endDate: string }>({
    mutationFn: async ({ startDate, endDate }) => {
      const blob = await exportAnalyticsCsv(startDate, endDate);
      const url = URL.createObjectURL(blob);
      try {
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `emails_${startDate}_${endDate}.csv`;
        document.body.appendChild(anchor);
        anchor.click();
        document.body.removeChild(anchor);
      } finally {
        URL.revokeObjectURL(url);
      }
    },
  });
}
