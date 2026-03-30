import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ReviewQueuePage from "../ReviewQueuePage";
import type { EmailListItem, DraftListItem } from "@/types/generated/api";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/hooks/useReviewQueue", () => ({
  useLowConfidenceEmails: vi.fn(),
  usePendingDrafts: vi.fn(),
}));

vi.mock("@/hooks/useDrafts", () => ({
  useDraftDetail: vi.fn(),
  useDraftMutations: vi.fn(),
  useDrafts: vi.fn(),
}));

import { useLowConfidenceEmails, usePendingDrafts } from "@/hooks/useReviewQueue";
import { useDraftDetail, useDraftMutations } from "@/hooks/useDrafts";

const mockUseLowConfidenceEmails = vi.mocked(useLowConfidenceEmails);
const mockUsePendingDrafts = vi.mocked(usePendingDrafts);
const mockUseDraftDetail = vi.mocked(useDraftDetail);
const mockUseDraftMutations = vi.mocked(useDraftMutations);

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderPage(client = makeQueryClient()) {
  return render(
    <MemoryRouter initialEntries={["/review"]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="*" element={<ReviewQueuePage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function makeNoopMutation() {
  return {
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    isIdle: true,
    isSuccess: false,
    isError: false,
    error: null,
    data: undefined,
    variables: undefined,
    status: "idle" as const,
    reset: vi.fn(),
    context: undefined,
    failureCount: 0,
    failureReason: null,
    isPaused: false,
    submittedAt: 0,
  };
}

const sampleEmail: EmailListItem = {
  id: "email-1",
  subject: "Low confidence email subject",
  sender_email: "sender@example.com",
  sender_name: "Sender Name",
  received_at: "2026-01-15T10:00:00Z",
  state: "classified",
  snippet: "Email snippet text",
  classification: {
    action: "respond",
    type: "complaint",
    confidence: "low",
    is_fallback: false,
  },
};

const sampleDraft: DraftListItem = {
  id: "draft-1",
  email_id: "email-2",
  email_subject: "Pending draft subject",
  email_sender: "drafter@example.com",
  status: "pending",
  reviewer_id: null,
  created_at: "2026-01-15T11:00:00Z",
};

// ── Tests ──────────────────────────────────────────────────────────────────────

describe("ReviewQueuePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // Default: empty states, not loading
    mockUseLowConfidenceEmails.mockReturnValue({
      emails: [],
      total: 0,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    mockUsePendingDrafts.mockReturnValue({
      drafts: [],
      total: 0,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    mockUseDraftDetail.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
      isSuccess: false,
      isFetching: false,
      isError: false,
      isPending: false,
      status: "pending",
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);

    mockUseDraftMutations.mockReturnValue({
      approve: makeNoopMutation() as never,
      reject: makeNoopMutation() as never,
      reassign: makeNoopMutation() as never,
    });
  });

  it("renders both tab buttons", () => {
    renderPage();
    expect(screen.getByRole("tab", { name: /low confidence/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /pending drafts/i })).toBeInTheDocument();
  });

  it("renders Low Confidence tab badge with total count", () => {
    mockUseLowConfidenceEmails.mockReturnValue({
      emails: [],
      total: 5,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();
    const lowConfTab = screen.getByRole("tab", { name: /low confidence/i });
    expect(lowConfTab).toHaveTextContent("5");
  });

  it("renders Pending Drafts tab badge with total count", () => {
    mockUsePendingDrafts.mockReturnValue({
      drafts: [],
      total: 3,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();
    const draftsTab = screen.getByRole("tab", { name: /pending drafts/i });
    expect(draftsTab).toHaveTextContent("3");
  });

  it("Low Confidence tab is active by default", () => {
    renderPage();
    const lowConfTab = screen.getByRole("tab", { name: /low confidence/i });
    expect(lowConfTab).toHaveAttribute("aria-selected", "true");
  });

  it("clicking Pending Drafts tab switches to that tab", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("tab", { name: /pending drafts/i }));

    const draftsTab = screen.getByRole("tab", { name: /pending drafts/i });
    expect(draftsTab).toHaveAttribute("aria-selected", "true");

    const lowConfTab = screen.getByRole("tab", { name: /low confidence/i });
    expect(lowConfTab).toHaveAttribute("aria-selected", "false");
  });

  it("shows low-confidence emails in the Low Confidence tab", () => {
    mockUseLowConfidenceEmails.mockReturnValue({
      emails: [sampleEmail],
      total: 1,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();
    expect(screen.getByText("Low confidence email subject")).toBeInTheDocument();
    expect(screen.getByText("sender@example.com")).toBeInTheDocument();
  });

  it("shows empty message when no low-confidence emails", () => {
    mockUseLowConfidenceEmails.mockReturnValue({
      emails: [],
      total: 0,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();
    expect(screen.getByText(/no low-confidence emails found/i)).toBeInTheDocument();
  });

  it("shows pending drafts in the Pending Drafts tab", async () => {
    mockUsePendingDrafts.mockReturnValue({
      drafts: [sampleDraft],
      total: 1,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("tab", { name: /pending drafts/i }));
    expect(screen.getByText("Pending draft subject")).toBeInTheDocument();
  });

  it("shows empty message when no pending drafts", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("tab", { name: /pending drafts/i }));
    expect(screen.getByText(/no pending drafts in the queue/i)).toBeInTheDocument();
  });

  it("shows loading indicator in low-confidence tab while fetching", () => {
    mockUseLowConfidenceEmails.mockReturnValue({
      emails: [],
      total: 0,
      isLoading: true,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();
    // Loading state renders Skeleton components
    const skeletons = document.querySelectorAll('[data-slot="skeleton"]');
    expect(skeletons.length).toBeGreaterThanOrEqual(1);
  });

  it("shows loading indicator in pending drafts tab while fetching", async () => {
    mockUsePendingDrafts.mockReturnValue({
      drafts: [],
      total: 0,
      isLoading: true,
      error: null,
      refetch: vi.fn(),
    });

    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("tab", { name: /pending drafts/i }));
    const skeletons = document.querySelectorAll('[data-slot="skeleton"]');
    expect(skeletons.length).toBeGreaterThanOrEqual(1);
  });

  it("shows error alert when low-confidence fetch fails", () => {
    mockUseLowConfidenceEmails.mockReturnValue({
      emails: [],
      total: 0,
      isLoading: false,
      error: new Error("API error"),
      refetch: vi.fn(),
    });

    renderPage();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/failed to load emails/i)).toBeInTheDocument();
  });

  it("shows the page title", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: /review queue/i })).toBeInTheDocument();
  });

  it("tab badges show ... while loading", () => {
    mockUseLowConfidenceEmails.mockReturnValue({
      emails: [],
      total: 0,
      isLoading: true,
      error: null,
      refetch: vi.fn(),
    });
    mockUsePendingDrafts.mockReturnValue({
      drafts: [],
      total: 0,
      isLoading: true,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();
    // Both tabs show "..." while loading
    const ellipsis = screen.getAllByText("...");
    expect(ellipsis.length).toBeGreaterThanOrEqual(1);
  });
});
