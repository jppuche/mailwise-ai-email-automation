// src/hooks/useEmails.ts
// TanStack Query hooks for email data fetching and mutations.
// All types imported from generated schema — no manual duplication (tighten-types D4).
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchEmails,
  fetchEmailDetail,
  fetchEmailClassification,
  reclassifyEmail,
  retryEmail,
  submitClassificationFeedback,
} from "@/api/emails";
import type {
  EmailFilterParams,
  PaginationParams,
  PaginatedResponse,
  EmailListItem,
  EmailDetailResponse,
  ClassificationDetailResponse,
  ClassificationFeedbackRequest,
  RetryResponse,
  ReclassifyResponse,
  FeedbackResponse,
} from "@/types/generated/api";

// ─────────────────────────────────────────────────────────────────────────────
// Query hooks
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch a paginated email list with optional filters.
 *
 * Query key: ["emails", filters, pagination]
 * Data: PaginatedResponse<EmailListItem> | undefined
 */
export function useEmails(filters: EmailFilterParams, pagination: PaginationParams) {
  return useQuery<PaginatedResponse<EmailListItem>>({
    queryKey: ["emails", filters, pagination],
    queryFn: () => fetchEmails({ ...filters, ...pagination }),
  });
}

/**
 * Fetch full detail for a single email.
 *
 * Query key: ["emails", emailId]
 * Only runs when emailId is truthy.
 */
export function useEmailDetail(emailId: string) {
  return useQuery<EmailDetailResponse>({
    queryKey: ["emails", emailId],
    queryFn: () => fetchEmailDetail(emailId),
    enabled: Boolean(emailId),
  });
}

/**
 * Fetch the classification record for an email.
 *
 * Query key: ["emails", emailId, "classification"]
 * Only runs when emailId is truthy.
 */
export function useEmailClassification(emailId: string) {
  return useQuery<ClassificationDetailResponse>({
    queryKey: ["emails", emailId, "classification"],
    queryFn: () => fetchEmailClassification(emailId),
    enabled: Boolean(emailId),
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Mutation hook
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Returns email mutation functions for admin actions and feedback submission.
 *
 * - reclassify: re-queue email for classification (admin only). Invalidates ["emails"].
 * - retry: re-queue failed/stuck email through the pipeline (admin only). Invalidates ["emails"].
 * - submitFeedback: submit reviewer classification correction.
 */
export function useEmailMutations() {
  const queryClient = useQueryClient();

  const reclassify = useMutation<ReclassifyResponse, Error, string>({
    mutationFn: (emailId: string) => reclassifyEmail(emailId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["emails"] });
    },
  });

  const retry = useMutation<RetryResponse, Error, string>({
    mutationFn: (emailId: string) => retryEmail(emailId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["emails"] });
    },
  });

  const submitFeedback = useMutation<
    FeedbackResponse,
    Error,
    { emailId: string; body: ClassificationFeedbackRequest }
  >({
    mutationFn: ({ emailId, body }) => submitClassificationFeedback(emailId, body),
  });

  return { reclassify, retry, submitFeedback };
}
