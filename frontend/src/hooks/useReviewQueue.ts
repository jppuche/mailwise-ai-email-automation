// src/hooks/useReviewQueue.ts
// Composed hooks for the Review Queue page.
// No dedicated backend endpoint — composed from emails + drafts queries (handoff delta #3).
//
// REVIEW_QUEUE_POLL_PAGE_SIZE is a named constant, not a magic number.
// The backend does NOT support a confidence filter — low-confidence filtering is client-side
// (handoff delta: confidence filter gap). Total reflects the filtered count, NOT the API total.
import { useEmails } from "./useEmails";
import { useDrafts } from "./useDrafts";
import type { PaginationParams, EmailListItem, DraftListItem } from "@/types/generated/api";

/** Page size for the review queue badge count queries — small to minimise payload. */
const REVIEW_QUEUE_POLL_PAGE_SIZE = 50;

// ─────────────────────────────────────────────────────────────────────────────
// Low-confidence emails
// ─────────────────────────────────────────────────────────────────────────────

export interface UseLowConfidenceEmailsResult {
  /** Emails filtered client-side to confidence === "low". */
  emails: EmailListItem[];
  /**
   * Count of low-confidence items in the current page.
   * NOTE: this is the client-filtered count, not the API total,
   * because the backend does not expose a confidence filter param.
   */
  total: number;
  isLoading: boolean;
  error: Error | null;
  refetch: () => void;
}

/**
 * Fetch classified emails and filter client-side to those with confidence === "low".
 *
 * Uses useEmails({ state: "classified" }, pagination) and filters the items array.
 * The returned `total` is the count of filtered items (not the API page total),
 * because pagination counts include high-confidence emails that are filtered out.
 *
 * Confidence precondition — the backend returns a string enum "high" | "low".
 * If this ever changes to a float, the badge will silently show nothing.
 * Validated by tsc against ClassificationSummary.confidence type.
 */
export function useLowConfidenceEmails(
  pagination: PaginationParams,
): UseLowConfidenceEmailsResult {
  const query = useEmails({ state: "classified" }, pagination);

  const allItems = query.data?.items ?? [];
  const emails = allItems.filter((e) => e.classification?.confidence === "low");

  return {
    emails,
    total: emails.length,
    isLoading: query.isLoading,
    error: query.error,
    refetch: query.refetch,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Pending drafts
// ─────────────────────────────────────────────────────────────────────────────

export interface UsePendingDraftsResult {
  drafts: DraftListItem[];
  total: number;
  isLoading: boolean;
  error: Error | null;
  refetch: () => void;
}

/**
 * Fetch pending drafts using the status query param.
 */
export function usePendingDrafts(pagination: PaginationParams): UsePendingDraftsResult {
  const query = useDrafts({ status: "pending", ...pagination });

  return {
    drafts: query.data?.items ?? [],
    total: query.data?.total ?? 0,
    isLoading: query.isLoading,
    error: query.error,
    refetch: query.refetch,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Badge counts (sidebar)
// ─────────────────────────────────────────────────────────────────────────────

export interface UseReviewQueueCountsResult {
  /** Number of classified emails with confidence === "low" in the sample page. */
  lowConfidenceCount: number;
  /** Number of pending drafts (API-accurate total). */
  pendingDraftsCount: number;
  /** Sum of both counts — used for the sidebar badge. */
  totalCount: number;
  isLoading: boolean;
}

/**
 * Fetch small pages of both review queue halves to derive sidebar badge counts.
 *
 * REVIEW_QUEUE_POLL_PAGE_SIZE is a named constant (50).
 * Low-confidence count is an approximation across the sample page because
 * the backend lacks a confidence filter. A future backend enhancement
 * (adding confidence to EmailFilter) would make this accurate.
 */
export function useReviewQueueCounts(): UseReviewQueueCountsResult {
  const smallPage: PaginationParams = {
    page: 1,
    page_size: REVIEW_QUEUE_POLL_PAGE_SIZE,
  };

  const emailsQuery = useEmails({ state: "classified" }, smallPage);
  const draftsQuery = useDrafts({ status: "pending", ...smallPage });

  const lowConfidenceCount =
    (emailsQuery.data?.items ?? []).filter((e) => e.classification?.confidence === "low")
      .length;
  const pendingDraftsCount = draftsQuery.data?.total ?? 0;

  return {
    lowConfidenceCount,
    pendingDraftsCount,
    totalCount: lowConfidenceCount + pendingDraftsCount,
    isLoading: emailsQuery.isLoading || draftsQuery.isLoading,
  };
}
