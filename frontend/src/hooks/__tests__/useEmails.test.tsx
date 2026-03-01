// src/hooks/__tests__/useEmails.test.ts
// Tests for useEmails, useEmailDetail, and useEmailMutations hooks.
// Mocks the API module — tests exercise hook query key logic, loading state,
// and mutation invalidation without touching the network.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type {
  PaginatedResponse,
  EmailListItem,
  EmailDetailResponse,
  ReclassifyResponse,
} from "@/types/generated/api";

// ─────────────────────────────────────────────────────────────────────────────
// API module mock — at module level, before hook imports
// ─────────────────────────────────────────────────────────────────────────────

vi.mock("@/api/emails", () => ({
  fetchEmails: vi.fn(),
  fetchEmailDetail: vi.fn(),
  fetchEmailClassification: vi.fn(),
  reclassifyEmail: vi.fn(),
  retryEmail: vi.fn(),
  submitClassificationFeedback: vi.fn(),
}));

import {
  fetchEmails,
  fetchEmailDetail,
  reclassifyEmail,
} from "@/api/emails";
import { useEmails, useEmailDetail, useEmailMutations } from "../useEmails";

const mockFetchEmails = vi.mocked(fetchEmails);
const mockFetchEmailDetail = vi.mocked(fetchEmailDetail);
const mockReclassifyEmail = vi.mocked(reclassifyEmail);

// ─────────────────────────────────────────────────────────────────────────────
// Wrapper factory — fresh QueryClient per test to prevent cache bleed
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

function makePaginatedEmails(
  items: EmailListItem[] = [],
): PaginatedResponse<EmailListItem> {
  return { items, total: items.length, page: 1, page_size: 25, pages: 1 };
}

function makeEmailListItem(overrides: Partial<EmailListItem> = {}): EmailListItem {
  return {
    id: "email-abc",
    subject: "Hello World",
    sender_email: "sender@example.com",
    sender_name: "Sender Name",
    received_at: "2026-01-01T10:00:00Z",
    state: "classified",
    snippet: "Short snippet",
    classification: {
      action: "respond",
      type: "inquiry",
      confidence: "high",
      is_fallback: false,
    },
    ...overrides,
  };
}

function makeEmailDetail(overrides: Partial<EmailDetailResponse> = {}): EmailDetailResponse {
  return {
    id: "email-abc",
    subject: "Hello World",
    sender_email: "sender@example.com",
    sender_name: "Sender Name",
    received_at: "2026-01-01T10:00:00Z",
    state: "classified",
    snippet: "Short snippet",
    thread_id: null,
    classification: null,
    routing_actions: [],
    crm_sync: null,
    draft: null,
    created_at: "2026-01-01T09:00:00Z",
    updated_at: "2026-01-01T10:00:00Z",
    ...overrides,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// useEmails
// ─────────────────────────────────────────────────────────────────────────────

describe("useEmails", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls fetchEmails with merged filter and pagination params", async () => {
    const responseData = makePaginatedEmails([makeEmailListItem()]);
    mockFetchEmails.mockResolvedValueOnce(responseData);

    const wrapper = createWrapper();
    renderHook(
      () => useEmails({ state: "classified", sender: "alice@example.com" }, { page: 2, page_size: 10 }),
      { wrapper },
    );

    await waitFor(() => {
      expect(mockFetchEmails).toHaveBeenCalledOnce();
    });

    expect(mockFetchEmails).toHaveBeenCalledWith({
      state: "classified",
      sender: "alice@example.com",
      page: 2,
      page_size: 10,
    });
  });

  it("returns isLoading true before the fetch resolves", () => {
    // Never resolve — stays pending
    mockFetchEmails.mockReturnValue(new Promise(() => {}));

    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useEmails({}, { page: 1, page_size: 25 }),
      { wrapper },
    );

    expect(result.current.isLoading).toBe(true);
    expect(result.current.data).toBeUndefined();
  });

  it("returns paginated data after fetch resolves", async () => {
    const item = makeEmailListItem();
    const responseData = makePaginatedEmails([item]);
    mockFetchEmails.mockResolvedValueOnce(responseData);

    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useEmails({}, { page: 1, page_size: 25 }),
      { wrapper },
    );

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.data).toEqual(responseData);
    expect(result.current.data?.items).toHaveLength(1);
    expect(result.current.data?.items[0].id).toBe("email-abc");
  });

  it("exposes error when fetch rejects", async () => {
    mockFetchEmails.mockRejectedValueOnce(new Error("Network error"));

    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useEmails({}, { page: 1, page_size: 25 }),
      { wrapper },
    );

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error?.message).toBe("Network error");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// useEmailDetail
// ─────────────────────────────────────────────────────────────────────────────

describe("useEmailDetail", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does NOT call fetchEmailDetail when emailId is an empty string", () => {
    mockFetchEmailDetail.mockResolvedValue(makeEmailDetail());

    const wrapper = createWrapper();
    renderHook(() => useEmailDetail(""), { wrapper });

    // Never called — enabled: false when emailId is falsy
    expect(mockFetchEmailDetail).not.toHaveBeenCalled();
  });

  it("calls fetchEmailDetail with the provided emailId when truthy", async () => {
    const detail = makeEmailDetail({ id: "email-xyz" });
    mockFetchEmailDetail.mockResolvedValueOnce(detail);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useEmailDetail("email-xyz"), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(mockFetchEmailDetail).toHaveBeenCalledWith("email-xyz");
    expect(result.current.data?.id).toBe("email-xyz");
  });

  it("returns isLoading true initially for a truthy emailId", () => {
    mockFetchEmailDetail.mockReturnValue(new Promise(() => {}));

    const wrapper = createWrapper();
    const { result } = renderHook(() => useEmailDetail("email-xyz"), { wrapper });

    expect(result.current.isLoading).toBe(true);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// useEmailMutations
// ─────────────────────────────────────────────────────────────────────────────

describe("useEmailMutations", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("reclassify.mutate calls reclassifyEmail with the emailId", async () => {
    const response: ReclassifyResponse = {
      queued: true,
      message: "Re-queued for classification",
      email_id: "email-abc",
    };
    mockReclassifyEmail.mockResolvedValueOnce(response);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useEmailMutations(), { wrapper });

    result.current.reclassify.mutate("email-abc");

    await waitFor(() => {
      expect(result.current.reclassify.isSuccess).toBe(true);
    });

    expect(mockReclassifyEmail).toHaveBeenCalledWith("email-abc");
  });

  it("reclassify.mutate invalidates the ['emails'] query on success", async () => {
    const response: ReclassifyResponse = {
      queued: true,
      message: "Re-queued",
      email_id: "email-abc",
    };
    mockReclassifyEmail.mockResolvedValueOnce(response);

    // Provide pre-populated cache to verify invalidation triggers a refetch
    mockFetchEmails.mockResolvedValue(makePaginatedEmails([]));

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    // Prime the cache with a query
    await queryClient.prefetchQuery({
      queryKey: ["emails", {}, { page: 1, page_size: 25 }],
      queryFn: () => mockFetchEmails({}),
    });

    const { result } = renderHook(() => useEmailMutations(), { wrapper });

    result.current.reclassify.mutate("email-abc");

    await waitFor(() => {
      expect(result.current.reclassify.isSuccess).toBe(true);
    });

    // invalidateQueries marks the query stale — subsequent access will refetch
    const queryState = queryClient.getQueryState(["emails", {}, { page: 1, page_size: 25 }]);
    expect(queryState?.isInvalidated).toBe(true);
  });

  it("retry.mutate calls retryEmail with the emailId", async () => {
    const { retryEmail: mockRetryEmail } = await import("@/api/emails");
    vi.mocked(mockRetryEmail).mockResolvedValueOnce({
      queued: true,
      message: "Retried",
      email_id: "email-abc",
    });

    const wrapper = createWrapper();
    const { result } = renderHook(() => useEmailMutations(), { wrapper });

    result.current.retry.mutate("email-abc");

    await waitFor(() => {
      expect(result.current.retry.isSuccess).toBe(true);
    });

    expect(vi.mocked(mockRetryEmail)).toHaveBeenCalledWith("email-abc");
  });

  it("submitFeedback.mutate calls submitClassificationFeedback with emailId and body", async () => {
    const { submitClassificationFeedback: mockSubmitFeedback } = await import("@/api/emails");
    vi.mocked(mockSubmitFeedback).mockResolvedValueOnce({
      recorded: true,
      feedback_id: "feedback-uuid",
    });

    const wrapper = createWrapper();
    const { result } = renderHook(() => useEmailMutations(), { wrapper });

    result.current.submitFeedback.mutate({
      emailId: "email-abc",
      body: { corrected_action: "respond", corrected_type: "inquiry" },
    });

    await waitFor(() => {
      expect(result.current.submitFeedback.isSuccess).toBe(true);
    });

    expect(vi.mocked(mockSubmitFeedback)).toHaveBeenCalledWith("email-abc", {
      corrected_action: "respond",
      corrected_type: "inquiry",
    });
  });
});
