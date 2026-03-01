import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import EmailBrowserPage from "../EmailBrowserPage";
import type { AuthUser } from "@/contexts/AuthContext";
import type {
  PaginatedResponse,
  EmailListItem,
  ReclassifyResponse,
} from "@/types/generated/api";
import type { UseMutationResult } from "@tanstack/react-query";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/hooks/useEmails", () => ({
  useEmails: vi.fn(),
  useEmailMutations: vi.fn(),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));

import { useEmails, useEmailMutations } from "@/hooks/useEmails";
import { useAuth } from "@/contexts/AuthContext";

const mockUseEmails = vi.mocked(useEmails);
const mockUseEmailMutations = vi.mocked(useEmailMutations);
const mockUseAuth = vi.mocked(useAuth);

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderPage(client = makeQueryClient()) {
  return render(
    <MemoryRouter initialEntries={["/emails"]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="*" element={<EmailBrowserPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const emptyPaginatedData: PaginatedResponse<EmailListItem> = {
  items: [],
  total: 0,
  page: 1,
  page_size: 20,
  pages: 1,
};

function makeReclassifyMutation(overrides?: Partial<UseMutationResult<ReclassifyResponse, Error, string>>) {
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
    ...overrides,
  } as UseMutationResult<ReclassifyResponse, Error, string>;
}

// ── Tests ──────────────────────────────────────────────────────────────────────

describe("EmailBrowserPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders FilterBar (state select is present)", () => {
    mockUseAuth.mockReturnValue({
      user: { id: "u1", username: "admin", role: "admin" } as AuthUser,
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      getAccessToken: () => "tok",
    });
    mockUseEmails.mockReturnValue({
      data: emptyPaginatedData,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
      isSuccess: true,
      isFetching: false,
      isError: false,
      isPending: false,
      status: "success",
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);
    mockUseEmailMutations.mockReturnValue({
      reclassify: makeReclassifyMutation(),
      retry: makeReclassifyMutation() as never,
      submitFeedback: makeReclassifyMutation() as never,
    });

    renderPage();
    expect(screen.getByRole("combobox", { name: /state/i })).toBeInTheDocument();
  });

  it("renders EmailTable column headers", () => {
    mockUseAuth.mockReturnValue({
      user: { id: "u1", username: "admin", role: "admin" } as AuthUser,
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      getAccessToken: () => "tok",
    });
    mockUseEmails.mockReturnValue({
      data: emptyPaginatedData,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
      isSuccess: true,
      isFetching: false,
      isError: false,
      isPending: false,
      status: "success",
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);
    mockUseEmailMutations.mockReturnValue({
      reclassify: makeReclassifyMutation(),
      retry: makeReclassifyMutation() as never,
      submitFeedback: makeReclassifyMutation() as never,
    });

    renderPage();
    // EmailTable renders empty state message when no items
    expect(screen.getByText(/no emails found/i)).toBeInTheDocument();
  });

  it("shows page title", () => {
    mockUseAuth.mockReturnValue({
      user: { id: "u1", username: "admin", role: "admin" } as AuthUser,
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      getAccessToken: () => "tok",
    });
    mockUseEmails.mockReturnValue({
      data: emptyPaginatedData,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
      isSuccess: true,
      isFetching: false,
      isError: false,
      isPending: false,
      status: "success",
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);
    mockUseEmailMutations.mockReturnValue({
      reclassify: makeReclassifyMutation(),
      retry: makeReclassifyMutation() as never,
      submitFeedback: makeReclassifyMutation() as never,
    });

    renderPage();
    expect(screen.getByRole("heading", { name: /^emails$/i })).toBeInTheDocument();
  });

  it("shows loading spinner when data is loading", () => {
    mockUseAuth.mockReturnValue({
      user: { id: "u1", username: "reviewer", role: "reviewer" } as AuthUser,
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      getAccessToken: () => "tok",
    });
    mockUseEmails.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
      refetch: vi.fn(),
      isSuccess: false,
      isFetching: true,
      isError: false,
      isPending: true,
      status: "pending",
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);
    mockUseEmailMutations.mockReturnValue({
      reclassify: makeReclassifyMutation(),
      retry: makeReclassifyMutation() as never,
      submitFeedback: makeReclassifyMutation() as never,
    });

    renderPage();
    expect(screen.getByRole("status", { name: /loading emails/i })).toBeInTheDocument();
  });

  it("does NOT show Reclassify Selected button for reviewer users when no selection", () => {
    mockUseAuth.mockReturnValue({
      user: { id: "u2", username: "reviewer1", role: "reviewer" } as AuthUser,
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      getAccessToken: () => "tok",
    });
    mockUseEmails.mockReturnValue({
      data: emptyPaginatedData,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
      isSuccess: true,
      isFetching: false,
      isError: false,
      isPending: false,
      status: "success",
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);
    mockUseEmailMutations.mockReturnValue({
      reclassify: makeReclassifyMutation(),
      retry: makeReclassifyMutation() as never,
      submitFeedback: makeReclassifyMutation() as never,
    });

    renderPage();
    expect(screen.queryByRole("button", { name: /reclassify selected/i })).not.toBeInTheDocument();
  });

  it("shows error alert when fetch fails", () => {
    mockUseAuth.mockReturnValue({
      user: { id: "u1", username: "admin", role: "admin" } as AuthUser,
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      getAccessToken: () => "tok",
    });
    mockUseEmails.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Network failure"),
      refetch: vi.fn(),
      isSuccess: false,
      isFetching: false,
      isError: true,
      isPending: false,
      status: "error",
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);
    mockUseEmailMutations.mockReturnValue({
      reclassify: makeReclassifyMutation(),
      retry: makeReclassifyMutation() as never,
      submitFeedback: makeReclassifyMutation() as never,
    });

    renderPage();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/network failure/i)).toBeInTheDocument();
  });
});
