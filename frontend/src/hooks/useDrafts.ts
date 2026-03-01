// src/hooks/useDrafts.ts
// TanStack Query hooks for draft data fetching and mutations.
// All types imported from generated schema — no manual duplication (tighten-types D4).
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchDrafts,
  fetchDraftDetail,
  approveDraft,
  rejectDraft,
  reassignDraft,
} from "@/api/drafts";
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

/** Combined params for GET /drafts — pagination + optional status filter. */
export type DraftQueryParams = PaginationParams & {
  status?: "pending" | "approved" | "rejected";
};

// ─────────────────────────────────────────────────────────────────────────────
// Query hooks
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch a paginated draft list with optional status filter.
 *
 * Query key: ["drafts", params]
 * Data: PaginatedResponse<DraftListItem> | undefined
 */
export function useDrafts(params: DraftQueryParams) {
  return useQuery<PaginatedResponse<DraftListItem>>({
    queryKey: ["drafts", params],
    queryFn: () => fetchDrafts(params),
  });
}

/**
 * Fetch full draft detail with embedded email context for side-by-side review.
 *
 * Query key: ["drafts", draftId]
 * Only runs when draftId is truthy.
 */
export function useDraftDetail(draftId: string) {
  return useQuery<DraftDetailResponse>({
    queryKey: ["drafts", draftId],
    queryFn: () => fetchDraftDetail(draftId),
    enabled: Boolean(draftId),
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Mutation hook
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Returns draft mutation functions for approve, reject, and reassign.
 *
 * - approve: POST /drafts/{id}/approve. Invalidates ["drafts"].
 * - reject: POST /drafts/{id}/reject. Invalidates ["drafts"].
 * - reassign: POST /drafts/{id}/reassign (admin only). Invalidates ["drafts"].
 */
export function useDraftMutations() {
  const queryClient = useQueryClient();

  const approve = useMutation<
    DraftApproveResponse,
    Error,
    { draftId: string; body?: DraftApproveRequest }
  >({
    mutationFn: ({ draftId, body }) => approveDraft(draftId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["drafts"] });
    },
  });

  const reject = useMutation<void, Error, { draftId: string; body: DraftRejectRequest }>({
    mutationFn: ({ draftId, body }) => rejectDraft(draftId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["drafts"] });
    },
  });

  const reassign = useMutation<
    DraftDetailResponse,
    Error,
    { draftId: string; body: DraftReassignRequest }
  >({
    mutationFn: ({ draftId, body }) => reassignDraft(draftId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["drafts"] });
    },
  });

  return { approve, reject, reassign };
}
