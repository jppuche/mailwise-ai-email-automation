// src/api/health.ts
// Typed API function for health check endpoint.
// Public endpoint — no auth required (client sends Bearer anyway, that's fine).
// Types from generated schema (tighten-types D4).
import apiClient from "./client";
import type { HealthResponse } from "@/types/generated/api";

/**
 * GET /health — check system health for database and Redis adapters.
 * Always returns HTTP 200 — never 503, even if status is "degraded".
 * Auth: None (public endpoint).
 */
export async function fetchHealth(): Promise<HealthResponse> {
  const { data } = await apiClient.get<HealthResponse>("/health");
  return data;
}
