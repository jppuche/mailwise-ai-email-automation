// src/api/logs.ts
// Typed API function for system logs with offset/limit pagination.
// Types from generated schema (tighten-types D4).
import apiClient from "./client";
import type { LogListResponse } from "@/types/generated/api";

/**
 * Query params for GET /logs.
 * Uses offset/limit pagination — NOT page/page_size.
 * Exported so hooks can reuse the type.
 */
export interface LogQueryParams {
  level?: string;
  source?: string;
  since?: string;
  until?: string;
  email_id?: string;
  limit?: number;
  offset?: number;
}

/**
 * GET /logs — paginated system log entries with optional filters.
 * Pagination: offset/limit (NOT page/page_size).
 * Page N: offset = (N - 1) * limit. Total pages: Math.ceil(total / limit).
 * Auth: Admin only.
 */
export async function fetchLogs(params?: LogQueryParams): Promise<LogListResponse> {
  const { data } = await apiClient.get<LogListResponse>("/logs", { params });
  return data;
}
