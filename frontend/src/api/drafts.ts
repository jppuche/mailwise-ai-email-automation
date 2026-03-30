// src/api/drafts.ts
// Typed API functions for draft endpoints — types from generated schema
import apiClient from "./client";
import type {
  PaginationParams,
  PaginatedResponse,
  DraftListItem,
  DraftDetailResponse,
  DraftApproveRequest,
  DraftApproveResponse,
  DraftRejectRequest,
  DraftReassignRequest,
} from "@/types/generated/api";

/** Query params accepted by GET /drafts */
type DraftListParams = PaginationParams & {
  status?: "pending" | "approved" | "rejected";
};

/**
 * GET /drafts — paginated draft list with optional status filter.
 */
export async function fetchDrafts(
  params: DraftListParams,
): Promise<PaginatedResponse<DraftListItem>> {
  const { data } = await apiClient.get<PaginatedResponse<DraftListItem>>("/drafts", {
    params,
  });
  return data;
}

/**
 * GET /drafts/{draftId} — full draft detail with email context for side-by-side review.
 */
export async function fetchDraftDetail(draftId: string): Promise<DraftDetailResponse> {
  const { data } = await apiClient.get<DraftDetailResponse>(`/drafts/${draftId}`);
  return data;
}

/**
 * POST /drafts/{draftId}/approve — approve a draft and optionally push to Gmail.
 */
export async function approveDraft(
  draftId: string,
  body?: DraftApproveRequest,
): Promise<DraftApproveResponse> {
  const { data } = await apiClient.post<DraftApproveResponse>(
    `/drafts/${draftId}/approve`,
    body ?? {},
  );
  return data;
}

/**
 * POST /drafts/{draftId}/reject — reject a draft with a required reason.
 * Returns HTTP 204 No Content — resolves to void.
 */
export async function rejectDraft(draftId: string, body: DraftRejectRequest): Promise<void> {
  await apiClient.post(`/drafts/${draftId}/reject`, body);
}

/**
 * POST /drafts/{draftId}/reassign — reassign draft to a different reviewer (admin only).
 */
export async function reassignDraft(
  draftId: string,
  body: DraftReassignRequest,
): Promise<DraftDetailResponse> {
  const { data } = await apiClient.post<DraftDetailResponse>(
    `/drafts/${draftId}/reassign`,
    body,
  );
  return data;
}
