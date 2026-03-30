// src/hooks/useLogs.ts
// TanStack Query hook for system logs with offset/limit pagination and filtering.
// Types from generated schema.
import { useQuery } from "@tanstack/react-query";
import { fetchLogs } from "@/api/logs";
import type { LogQueryParams } from "@/api/logs";
import type { LogListResponse } from "@/types/generated/api";

// Re-export LogQueryParams so consumers can import it from the hook module
export type { LogQueryParams };

/**
 * Fetch paginated system log entries with optional filters.
 *
 * Uses offset/limit pagination (NOT page/page_size).
 * To compute current page N from offset: Math.floor(offset / limit) + 1
 * To compute total pages: Math.ceil(total / limit)
 *
 * Query key: ["logs", params] — re-fetches when any param changes.
 * Pass an empty object or undefined to fetch with server defaults.
 */
export function useLogs(params: LogQueryParams) {
  return useQuery<LogListResponse>({
    queryKey: ["logs", params],
    queryFn: () => fetchLogs(params),
  });
}
