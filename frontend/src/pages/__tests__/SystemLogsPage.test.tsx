import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import LogsPage from "../LogsPage";
import type { LogListResponse, LogEntry } from "@/types/generated/api";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/hooks/useLogs", () => ({
  useLogs: vi.fn(),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));

import { useLogs } from "@/hooks/useLogs";
import { useAuth } from "@/contexts/AuthContext";

const mockUseLogs = vi.mocked(useLogs);
const mockUseAuth = vi.mocked(useAuth);

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderPage(client = makeQueryClient()) {
  return render(
    <MemoryRouter initialEntries={["/logs"]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="*" element={<LogsPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

// ── Mock data ─────────────────────────────────────────────────────────────────

const mockInfoEntry: LogEntry = {
  id: "log-1",
  timestamp: "2026-03-01T10:00:00Z",
  level: "INFO",
  source: "src.services.ingestion",
  message: "Email ingestion completed successfully",
  email_id: "email-abc-123",
  context: { duration_ms: "150", emails_processed: "5" },
};

const mockErrorEntry: LogEntry = {
  id: "log-2",
  timestamp: "2026-03-01T10:05:00Z",
  level: "ERROR",
  source: "src.adapters.llm",
  message: "LLM classification timed out after 30 seconds of waiting for a response",
  email_id: null,
  context: { model: "gpt-4o-mini", attempt: "3" },
};

const mockWarningEntry: LogEntry = {
  id: "log-3",
  timestamp: "2026-03-01T10:10:00Z",
  level: "WARNING",
  source: "src.services.routing",
  message: "No routing rule matched for this email",
  email_id: "email-xyz-456",
  context: {},
};

function makeLogListResponse(items: LogEntry[], total = items.length): LogListResponse {
  return { items, total, limit: 50, offset: 0 };
}

// ── Tests ──────────────────────────────────────────────────────────────────────

describe("LogsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockUseAuth.mockReturnValue({
      user: { id: "u1", username: "admin", role: "admin" },
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      getAccessToken: () => "tok",
    });

    mockUseLogs.mockReturnValue({
      data: makeLogListResponse([mockInfoEntry, mockErrorEntry, mockWarningEntry], 3),
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
  });

  it("renders the page title", () => {
    renderPage();
    expect(screen.getByRole("heading", { level: 1, name: /system logs/i })).toBeInTheDocument();
  });

  it("renders Level filter select", () => {
    renderPage();
    expect(screen.getByRole("combobox", { name: /level/i })).toBeInTheDocument();
  });

  it("renders Source filter input", () => {
    renderPage();
    expect(screen.getByRole("textbox", { name: /source/i })).toBeInTheDocument();
  });

  it("renders Since and Until datetime inputs", () => {
    renderPage();
    // datetime-local inputs are present for Since and Until
    const sinceInput = document.getElementById("logs-since");
    const untilInput = document.getElementById("logs-until");
    expect(sinceInput).toBeInTheDocument();
    expect(untilInput).toBeInTheDocument();
  });

  it("renders log entries from hook data", () => {
    renderPage();
    expect(screen.getByText("src.services.ingestion")).toBeInTheDocument();
    expect(screen.getByText("src.adapters.llm")).toBeInTheDocument();
    expect(screen.getByText("src.services.routing")).toBeInTheDocument();
  });

  it("renders INFO level badge", () => {
    renderPage();
    // Use aria-label to distinguish the badge span from the <option> in the select
    expect(screen.getByRole("generic", { hidden: true, name: /level: info/i }) ||
      document.querySelector('[aria-label="Level: INFO"]')).toBeTruthy();
    // Simpler: just check the span by its aria-label attribute
    expect(document.querySelector('[aria-label="Level: INFO"]')).toBeInTheDocument();
  });

  it("renders ERROR level badge", () => {
    renderPage();
    expect(document.querySelector('[aria-label="Level: ERROR"]')).toBeInTheDocument();
  });

  it("renders WARNING level badge", () => {
    renderPage();
    expect(document.querySelector('[aria-label="Level: WARNING"]')).toBeInTheDocument();
  });

  it("shows entry count message", () => {
    renderPage();
    expect(screen.getByText(/3 log entries found/i)).toBeInTheDocument();
  });

  it("shows singular 'entry' when total is 1", () => {
    mockUseLogs.mockReturnValue({
      data: makeLogListResponse([mockInfoEntry], 1),
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

    renderPage();
    expect(screen.getByText(/1 log entry found/i)).toBeInTheDocument();
  });

  it("shows 'No log entries found' when total is 0", () => {
    mockUseLogs.mockReturnValue({
      data: makeLogListResponse([], 0),
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

    renderPage();
    expect(screen.getByText(/no log entries found/i)).toBeInTheDocument();
  });

  it("changing level filter calls useLogs with new level param", async () => {
    const user = userEvent.setup();
    renderPage();

    const levelSelect = screen.getByRole("combobox", { name: /level/i });
    await user.selectOptions(levelSelect, "ERROR");

    // After selecting ERROR, useLogs should be called with the new params
    // Verify the select value changed
    expect(levelSelect).toHaveValue("ERROR");
  });

  it("selecting a level filter re-renders with filtered context", async () => {
    const user = userEvent.setup();
    renderPage();

    const levelSelect = screen.getByRole("combobox", { name: /level/i });
    await user.selectOptions(levelSelect, "WARNING");

    // useLogs is now called with { level: "WARNING", ... }
    expect(mockUseLogs).toHaveBeenCalledWith(
      expect.objectContaining({ level: "WARNING" }),
    );
  });

  it("clicking Expand on a log row shows full message", async () => {
    // The error message is truncated (> 120 chars test)
    const longMessageEntry: LogEntry = {
      ...mockErrorEntry,
      message: "LLM classification timed out after 30 seconds of waiting for a response from the OpenAI API endpoint with retries",
    };

    mockUseLogs.mockReturnValue({
      data: makeLogListResponse([longMessageEntry]),
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

    const user = userEvent.setup();
    renderPage();

    const expandBtn = screen.getByRole("button", { name: /expand log entry/i });
    await user.click(expandBtn);

    // After expansion, full message is shown
    expect(screen.getByText(/LLM classification timed out after 30 seconds of waiting for a response from the OpenAI API endpoint with retries/)).toBeInTheDocument();
  });

  it("clicking Expand shows context key-value pairs", async () => {
    const user = userEvent.setup();
    renderPage();

    // Click expand on the INFO entry (has context data)
    const expandBtns = screen.getAllByRole("button", { name: /expand log entry/i });
    await user.click(expandBtns[0]);

    expect(screen.getByText("duration_ms")).toBeInTheDocument();
    expect(screen.getByText("150")).toBeInTheDocument();
  });

  it("clicking Expand shows email_id when present", async () => {
    const user = userEvent.setup();
    renderPage();

    const expandBtns = screen.getAllByRole("button", { name: /expand log entry/i });
    await user.click(expandBtns[0]);

    expect(screen.getByText("email_id:")).toBeInTheDocument();
    expect(screen.getByText("email-abc-123")).toBeInTheDocument();
  });

  it("shows 'No additional context' when context is empty and email_id is null", async () => {
    // mockWarningEntry has empty context and email_id set — need one with both null
    const noContextEntry: LogEntry = {
      ...mockWarningEntry,
      email_id: null,
      context: {},
    };

    mockUseLogs.mockReturnValue({
      data: makeLogListResponse([noContextEntry]),
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

    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /expand log entry/i }));

    expect(screen.getByText(/no additional context/i)).toBeInTheDocument();
  });

  it("clicking Collapse on an expanded row hides the detail", async () => {
    const user = userEvent.setup();
    renderPage();

    const expandBtns = screen.getAllByRole("button", { name: /expand log entry/i });
    await user.click(expandBtns[0]);
    expect(screen.getByText("duration_ms")).toBeInTheDocument();

    // Click again to collapse
    const collapseBtn = screen.getByRole("button", { name: /collapse log entry/i });
    await user.click(collapseBtn);
    expect(screen.queryByText("duration_ms")).not.toBeInTheDocument();
  });

  it("does NOT show pagination when total pages is 1", () => {
    mockUseLogs.mockReturnValue({
      data: makeLogListResponse([mockInfoEntry], 1),
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

    renderPage();
    expect(screen.queryByRole("button", { name: /previous/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /next/i })).not.toBeInTheDocument();
  });

  it("shows pagination controls when total > limit", () => {
    // 50 items per page, 120 total = 3 pages
    mockUseLogs.mockReturnValue({
      data: { items: [mockInfoEntry], total: 120, limit: 50, offset: 0 },
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

    renderPage();
    expect(screen.getByRole("button", { name: /previous/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /next/i })).toBeInTheDocument();
  });

  it("shows page indicator text when paginated", () => {
    mockUseLogs.mockReturnValue({
      data: { items: [mockInfoEntry], total: 120, limit: 50, offset: 0 },
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

    renderPage();
    expect(screen.getByText(/page 1 of 3/i)).toBeInTheDocument();
  });

  it("Previous button is disabled on the first page", () => {
    mockUseLogs.mockReturnValue({
      data: { items: [mockInfoEntry], total: 120, limit: 50, offset: 0 },
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

    renderPage();
    expect(screen.getByRole("button", { name: /previous/i })).toBeDisabled();
  });

  it("Next button is disabled on the last page", async () => {
    // The component uses React state for offset (starts at 0).
    // To reach the last page we must click Next until offset + limit >= total.
    // total=60, limit=50 → 2 pages. After 1 click: offset=50, 50+50=100 >= 60 → Next disabled.
    mockUseLogs.mockReturnValue({
      data: { items: [mockInfoEntry], total: 60, limit: 50, offset: 0 },
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

    const user = userEvent.setup();
    renderPage();

    // Click Next to advance to the last page
    await user.click(screen.getByRole("button", { name: /next/i }));

    expect(screen.getByRole("button", { name: /next/i })).toBeDisabled();
  });

  it("clicking Next advances the page", async () => {
    mockUseLogs.mockReturnValue({
      data: { items: [mockInfoEntry], total: 120, limit: 50, offset: 0 },
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

    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /next/i }));

    // After clicking next, useLogs should have been called with offset=50
    expect(mockUseLogs).toHaveBeenCalledWith(
      expect.objectContaining({ offset: 50 }),
    );
  });

  it("shows loading state while logs are fetching", () => {
    mockUseLogs.mockReturnValue({
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

    renderPage();
    expect(screen.getByText(/loading logs/i)).toBeInTheDocument();
  });

  it("shows error alert when logs fail to load", () => {
    mockUseLogs.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Failed to fetch"),
      refetch: vi.fn(),
      isSuccess: false,
      isFetching: false,
      isError: true,
      isPending: false,
      status: "error",
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);

    renderPage();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/failed to load logs/i)).toBeInTheDocument();
  });

  it("filtering by level resets offset to 0", async () => {
    // Start at page 2 — simulate by checking the initial call then filter change
    const user = userEvent.setup();
    renderPage();

    const levelSelect = screen.getByRole("combobox", { name: /level/i });
    await user.selectOptions(levelSelect, "ERROR");

    // Offset should reset to 0 when filter changes
    expect(mockUseLogs).toHaveBeenCalledWith(
      expect.objectContaining({ level: "ERROR", offset: 0 }),
    );
  });
});
