// src/hooks/useHealth.ts
// TanStack Query hook for health polling.
// Types from generated schema (tighten-types D4).
import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "@/api/health";
import { HEALTH_POLL_INTERVAL_MS } from "@/utils/constants";
import type { HealthResponse } from "@/types/generated/api";

/**
 * Poll the health endpoint every HEALTH_POLL_INTERVAL_MS (30s).
 * The endpoint always returns HTTP 200 — check data.status for "ok" vs "degraded".
 *
 * Query key: ["health"]
 */
export function useHealth() {
  return useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: HEALTH_POLL_INTERVAL_MS,
  });
}
