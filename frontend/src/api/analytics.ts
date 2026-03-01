// src/api/analytics.ts
// Typed API functions for analytics endpoints + CSV export.
// Types from generated schema (tighten-types D4).
import apiClient from "./client";
import type {
  VolumeResponse,
  ClassificationDistributionResponse,
  AccuracyResponse,
  RoutingResponse,
} from "@/types/generated/api";

/**
 * GET /analytics/volume — email volume time series for a date range.
 * Both start_date and end_date are required in "YYYY-MM-DD" format.
 * Auth: Reviewer + Admin.
 */
export async function fetchVolume(startDate: string, endDate: string): Promise<VolumeResponse> {
  const { data } = await apiClient.get<VolumeResponse>("/analytics/volume", {
    params: { start_date: startDate, end_date: endDate },
  });
  return data;
}

/**
 * GET /analytics/classification-distribution — action/type distribution for a date range.
 * Both start_date and end_date are required in "YYYY-MM-DD" format.
 * Auth: Reviewer + Admin.
 */
export async function fetchDistribution(
  startDate: string,
  endDate: string,
): Promise<ClassificationDistributionResponse> {
  const { data } = await apiClient.get<ClassificationDistributionResponse>(
    "/analytics/classification-distribution",
    { params: { start_date: startDate, end_date: endDate } },
  );
  return data;
}

/**
 * GET /analytics/accuracy — classification accuracy for a date range.
 * Both start_date and end_date are required in "YYYY-MM-DD" format.
 * Auth: Reviewer + Admin.
 */
export async function fetchAccuracy(
  startDate: string,
  endDate: string,
): Promise<AccuracyResponse> {
  const { data } = await apiClient.get<AccuracyResponse>("/analytics/accuracy", {
    params: { start_date: startDate, end_date: endDate },
  });
  return data;
}

/**
 * GET /analytics/routing — per-channel routing stats for a date range.
 * Both start_date and end_date are required in "YYYY-MM-DD" format.
 * Auth: Reviewer + Admin.
 */
export async function fetchRouting(
  startDate: string,
  endDate: string,
): Promise<RoutingResponse> {
  const { data } = await apiClient.get<RoutingResponse>("/analytics/routing", {
    params: { start_date: startDate, end_date: endDate },
  });
  return data;
}

/**
 * GET /analytics/export — download emails CSV for a date range.
 * Returns a Blob with Content-Type text/csv.
 * Content-Disposition: attachment; filename=emails_YYYY-MM-DD_YYYY-MM-DD.csv
 * Auth: Admin only.
 */
export async function exportAnalyticsCsv(startDate: string, endDate: string): Promise<Blob> {
  const { data } = await apiClient.get<Blob>("/analytics/export", {
    params: { start_date: startDate, end_date: endDate },
    responseType: "blob",
  });
  return data;
}
