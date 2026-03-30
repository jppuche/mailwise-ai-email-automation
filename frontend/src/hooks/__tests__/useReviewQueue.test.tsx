// src/hooks/__tests__/useReviewQueue.test.ts
// Tests for useLowConfidenceEmails, usePendingDrafts, and useReviewQueueCounts.
//
// Architecture note: useReviewQueue composes useEmails and useDrafts internally.
// We mock the API modules (emails + drafts) so that useEmails and useDrafts
// receive controlled data and the client-side filtering logic can be exercised.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type {
  EmailListItem,
  DraftListItem,
  PaginatedResponse,
} from "@/types/generated/api";

// ─────────────────────────────────────────────────────────────────────────────
// API module mocks — must precede hook imports
// ─────────────────────────────────────────────────────────────────────────────

vi.mock("@/api/emails", () => ({
  fetchEmails: vi.fn(),
  fetchEmailDetail: vi.fn(),
  fetchEmailClassification: vi.fn(),
  reclassifyEmail: vi.fn(),
  retryEmail: vi.fn(),
  submitClassificationFeedback: vi.fn(),
}));

vi.mock("@/api/drafts", () => ({
  fetchDrafts: vi.fn(),
  fetchDraftDetail: vi.fn(),
  approveDraft: vi.fn(),
  rejectDraft: vi.fn(),
  reassignDraft: vi.fn(),
}));

import { fetchEmails } from "@/api/emails";
import { fetchDrafts } from "@/api/drafts";
import {
  useLowConfidenceEmails,
  usePendingDrafts,
  useReviewQueueCounts,
} from "../useReviewQueue";

const mockFetchEmails = vi.mocked(fetchEmails);
const mockFetchDrafts = vi.mocked(fetchDrafts);

// ─────────────────────────────────────────────────────────────────────────────
// Wrapper factory — fresh QueryClient per test
// ─────────────────────────────────────────────────────────────────────────────

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Test data factories
// ─────────────────────────────────────────────────────────────────────────────

function makeEmailListItem(overrides: Partial<EmailListItem> = {}): EmailListItem {
  return {
    id: "email-1",
    subject: "Test Subject",
    sender_email: "test@example.com",
    sender_name: null,
    received_at: "2026-01-01T00:00:00Z",
    state: "classified",
    snippet: null,
    classification: {
      action: "respond",
      type: "inquiry",
      confidence: "high",
      is_fallback: false,
    },
    ...overrides,
  };
}

function makePaginatedEmails(
  items: EmailListItem[],
  total?: number,
): PaginatedResponse<EmailListItem> {
  return {
    items,
    total: total ?? items.length,
    page: 1,
    page_size: 50,
    pages: 1,
  };
}

function makeDraftListItem(overrides: Partial<DraftListItem> = {}): DraftListItem {
  return {
    id: "draft-1",
    email_id: "email-1",
    email_subject: "Test Subject",
    email_sender: "test@example.com",
    status: "pending",
    reviewer_id: null,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makePaginatedDrafts(
  items: DraftListItem[],
  total?: number,
): PaginatedResponse<DraftListItem> {
  return {
    items,
    total: total ?? items.length,
    page: 1,
    page_size: 50,
    pages: 1,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// useLowConfidenceEmails
// ─────────────────────────────────────────────────────────────────────────────

describe("useLowConfidenceEmails", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("filters items client-side to those with confidence === 'low'", async () => {
    const highItem = makeEmailListItem({
      id: "email-high",
      classification: { action: "respond", type: "inquiry", confidence: "high", is_fallback: false },
    });
    const lowItem = makeEmailListItem({
      id: "email-low",
      classification: { action: "archive", type: "spam", confidence: "low", is_fallback: false },
    });

    mockFetchEmails.mockResolvedValueOnce(makePaginatedEmails([highItem, lowItem], 2));

    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useLowConfidenceEmails({ page: 1, page_size: 25 }),
      { wrapper },
    );

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.emails).toHaveLength(1);
    expect(result.current.emails[0].id).toBe("email-low");
  });

  it("excludes items whose classification is null", async () => {
    const noClassification = makeEmailListItem({
      id: "email-no-class",
      classification: null,
    });
    const lowItem = makeEmailListItem({
      id: "email-low",
      classification: { action: "archive", type: "spam", confidence: "low", is_fallback: false },
    });

    mockFetchEmails.mockResolvedValueOnce(makePaginatedEmails([noClassification, lowItem]));

    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useLowConfidenceEmails({ page: 1, page_size: 25 }),
      { wrapper },
    );

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.emails).toHaveLength(1);
    expect(result.current.emails[0].id).toBe("email-low");
  });

  it("total reflects the filtered count, NOT the API total", async () => {
    // API returns 10 items but only 3 are low confidence
    const items: EmailListItem[] = [
      makeEmailListItem({ id: "low-1", classification: { action: "a", type: "b", confidence: "low", is_fallback: false } }),
      makeEmailListItem({ id: "low-2", classification: { action: "a", type: "b", confidence: "low", is_fallback: false } }),
      makeEmailListItem({ id: "low-3", classification: { action: "a", type: "b", confidence: "low", is_fallback: false } }),
      makeEmailListItem({ id: "high-1" }),
      makeEmailListItem({ id: "high-2" }),
      makeEmailListItem({ id: "high-3" }),
      makeEmailListItem({ id: "high-4" }),
      makeEmailListItem({ id: "high-5" }),
      makeEmailListItem({ id: "high-6" }),
      makeEmailListItem({ id: "high-7" }),
    ];

    mockFetchEmails.mockResolvedValueOnce(makePaginatedEmails(items, 100));

    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useLowConfidenceEmails({ page: 1, page_size: 50 }),
      { wrapper },
    );

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    // total = 3 (filtered), NOT 100 (API total)
    expect(result.current.total).toBe(3);
  });

  it("returns empty array and total 0 when all items are high confidence", async () => {
    const items = [makeEmailListItem({ id: "high-1" }), makeEmailListItem({ id: "high-2" })];
    mockFetchEmails.mockResolvedValueOnce(makePaginatedEmails(items));

    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useLowConfidenceEmails({ page: 1, page_size: 25 }),
      { wrapper },
    );

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.emails).toHaveLength(0);
    expect(result.current.total).toBe(0);
  });

  it("passes state: 'classified' to the underlying useEmails call", async () => {
    mockFetchEmails.mockResolvedValueOnce(makePaginatedEmails([]));

    const wrapper = createWrapper();
    renderHook(
      () => useLowConfidenceEmails({ page: 1, page_size: 25 }),
      { wrapper },
    );

    await waitFor(() => {
      expect(mockFetchEmails).toHaveBeenCalled();
    });

    expect(mockFetchEmails).toHaveBeenCalledWith(
      expect.objectContaining({ state: "classified" }),
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// usePendingDrafts
// ─────────────────────────────────────────────────────────────────────────────

describe("usePendingDrafts", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("passes status: 'pending' to the underlying API call", async () => {
    mockFetchDrafts.mockResolvedValueOnce(makePaginatedDrafts([]));

    const wrapper = createWrapper();
    renderHook(
      () => usePendingDrafts({ page: 1, page_size: 25 }),
      { wrapper },
    );

    await waitFor(() => {
      expect(mockFetchDrafts).toHaveBeenCalled();
    });

    expect(mockFetchDrafts).toHaveBeenCalledWith(
      expect.objectContaining({ status: "pending" }),
    );
  });

  it("returns drafts array and total from the API response", async () => {
    const draft = makeDraftListItem();
    mockFetchDrafts.mockResolvedValueOnce(makePaginatedDrafts([draft], 42));

    const wrapper = createWrapper();
    const { result } = renderHook(
      () => usePendingDrafts({ page: 1, page_size: 25 }),
      { wrapper },
    );

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.drafts).toHaveLength(1);
    expect(result.current.drafts[0].id).toBe("draft-1");
    // total comes from API — no client-side filtering for drafts
    expect(result.current.total).toBe(42);
  });

  it("returns empty array and total 0 before data resolves", () => {
    mockFetchDrafts.mockReturnValue(new Promise(() => {}));

    const wrapper = createWrapper();
    const { result } = renderHook(
      () => usePendingDrafts({ page: 1, page_size: 25 }),
      { wrapper },
    );

    expect(result.current.isLoading).toBe(true);
    expect(result.current.drafts).toEqual([]);
    expect(result.current.total).toBe(0);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// useReviewQueueCounts
// ─────────────────────────────────────────────────────────────────────────────

describe("useReviewQueueCounts", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("combines lowConfidenceCount and pendingDraftsCount into totalCount", async () => {
    // 3 classified emails, 2 are low confidence
    const emailItems: EmailListItem[] = [
      makeEmailListItem({ id: "low-a", classification: { action: "a", type: "b", confidence: "low", is_fallback: false } }),
      makeEmailListItem({ id: "low-b", classification: { action: "a", type: "b", confidence: "low", is_fallback: false } }),
      makeEmailListItem({ id: "high-a" }),
    ];
    mockFetchEmails.mockResolvedValueOnce(makePaginatedEmails(emailItems, 3));

    // 5 pending drafts
    mockFetchDrafts.mockResolvedValueOnce(makePaginatedDrafts([], 5));

    const wrapper = createWrapper();
    const { result } = renderHook(() => useReviewQueueCounts(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.lowConfidenceCount).toBe(2);
    expect(result.current.pendingDraftsCount).toBe(5);
    expect(result.current.totalCount).toBe(7);
  });

  it("is isLoading true while either sub-query is pending", () => {
    mockFetchEmails.mockReturnValue(new Promise(() => {}));
    mockFetchDrafts.mockReturnValue(new Promise(() => {}));

    const wrapper = createWrapper();
    const { result } = renderHook(() => useReviewQueueCounts(), { wrapper });

    expect(result.current.isLoading).toBe(true);
  });

  it("returns zeros when both queries return empty results", async () => {
    mockFetchEmails.mockResolvedValueOnce(makePaginatedEmails([], 0));
    mockFetchDrafts.mockResolvedValueOnce(makePaginatedDrafts([], 0));

    const wrapper = createWrapper();
    const { result } = renderHook(() => useReviewQueueCounts(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.lowConfidenceCount).toBe(0);
    expect(result.current.pendingDraftsCount).toBe(0);
    expect(result.current.totalCount).toBe(0);
  });
});
