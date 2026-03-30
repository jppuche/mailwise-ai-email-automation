// src/hooks/__tests__/useLogs.test.tsx
// Tests for useLogs hook — offset/limit pagination and filter params.
// Mocks @/api/logs module.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type { LogListResponse, LogEntry } from "@/types/generated/api";

// ─────────────────────────────────────────────────────────────────────────────
// API module mock — must precede hook imports
// ─────────────────────────────────────────────────────────────────────────────

vi.mock("@/api/logs", () => ({
  fetchLogs: vi.fn(),
}));

import { fetchLogs } from "@/api/logs";
import { useLogs } from "../useLogs";

const mockFetchLogs = vi.mocked(fetchLogs);

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

function makeLogEntry(overrides: Partial<LogEntry> = {}): LogEntry {
  return {
    id: "log-1",
    timestamp: "2026-01-01T10:00:00Z",
    level: "INFO",
    source: "src.services.routing",
    message: "Rule matched and dispatched",
    email_id: "email-abc",
    context: { rule_id: "rule-1", channel: "slack" },
    ...overrides,
  };
}

function makeLogListResponse(
  items: LogEntry[] = [],
  overrides: Partial<LogListResponse> = {},
): LogListResponse {
  return {
    items,
    total: items.length,
    limit: 50,
    offset: 0,
    ...overrides,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// useLogs — empty params
// ─────────────────────────────────────────────────────────────────────────────

describe("useLogs({})", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls fetchLogs with empty params object", async () => {
    mockFetchLogs.mockResolvedValueOnce(makeLogListResponse([]));

    const wrapper = createWrapper();
    renderHook(() => useLogs({}), { wrapper });

    await waitFor(() => {
      expect(mockFetchLogs).toHaveBeenCalledOnce();
    });

    expect(mockFetchLogs).toHaveBeenCalledWith({});
  });

  it("returns isLoading true before fetch resolves", () => {
    mockFetchLogs.mockReturnValue(new Promise(() => {}));

    const wrapper = createWrapper();
    const { result } = renderHook(() => useLogs({}), { wrapper });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.data).toBeUndefined();
  });

  it("returns LogListResponse data after fetch resolves", async () => {
    const entries = [makeLogEntry({ id: "log-1" }), makeLogEntry({ id: "log-2" })];
    const response = makeLogListResponse(entries, { total: 2, limit: 50, offset: 0 });
    mockFetchLogs.mockResolvedValueOnce(response);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useLogs({}), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.data).toEqual(response);
    expect(result.current.data?.items).toHaveLength(2);
    expect(result.current.data?.total).toBe(2);
    expect(result.current.data?.limit).toBe(50);
    expect(result.current.data?.offset).toBe(0);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// useLogs — with filters
// ─────────────────────────────────────────────────────────────────────────────

describe("useLogs with filters", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("passes level filter to fetchLogs", async () => {
    mockFetchLogs.mockResolvedValueOnce(makeLogListResponse([]));

    const wrapper = createWrapper();
    renderHook(() => useLogs({ level: "ERROR" }), { wrapper });

    await waitFor(() => {
      expect(mockFetchLogs).toHaveBeenCalledOnce();
    });

    expect(mockFetchLogs).toHaveBeenCalledWith({ level: "ERROR" });
  });

  it("passes limit and offset for pagination", async () => {
    mockFetchLogs.mockResolvedValueOnce(makeLogListResponse([], { limit: 50, offset: 50 }));

    const wrapper = createWrapper();
    renderHook(() => useLogs({ limit: 50, offset: 50 }), { wrapper });

    await waitFor(() => {
      expect(mockFetchLogs).toHaveBeenCalledOnce();
    });

    expect(mockFetchLogs).toHaveBeenCalledWith({ limit: 50, offset: 50 });
  });

  it("passes all filter params together", async () => {
    mockFetchLogs.mockResolvedValueOnce(makeLogListResponse([]));

    const wrapper = createWrapper();
    renderHook(
      () => useLogs({ level: "ERROR", limit: 50, offset: 0 }),
      { wrapper },
    );

    await waitFor(() => {
      expect(mockFetchLogs).toHaveBeenCalledOnce();
    });

    expect(mockFetchLogs).toHaveBeenCalledWith({ level: "ERROR", limit: 50, offset: 0 });
  });

  it("passes source filter to fetchLogs", async () => {
    mockFetchLogs.mockResolvedValueOnce(makeLogListResponse([]));

    const wrapper = createWrapper();
    renderHook(() => useLogs({ source: "src.services.routing" }), { wrapper });

    await waitFor(() => {
      expect(mockFetchLogs).toHaveBeenCalledOnce();
    });

    expect(mockFetchLogs).toHaveBeenCalledWith({ source: "src.services.routing" });
  });

  it("passes email_id filter to fetchLogs", async () => {
    const entries = [makeLogEntry({ email_id: "email-xyz" })];
    mockFetchLogs.mockResolvedValueOnce(makeLogListResponse(entries, { total: 1 }));

    const wrapper = createWrapper();
    const { result } = renderHook(() => useLogs({ email_id: "email-xyz" }), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(mockFetchLogs).toHaveBeenCalledWith({ email_id: "email-xyz" });
    expect(result.current.data?.items[0].email_id).toBe("email-xyz");
  });

  it("re-fetches when params change (different query keys)", async () => {
    mockFetchLogs.mockResolvedValue(makeLogListResponse([]));

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result: r1 } = renderHook(() => useLogs({ level: "INFO" }), { wrapper });
    const { result: r2 } = renderHook(() => useLogs({ level: "ERROR" }), { wrapper });

    await waitFor(() => {
      expect(r1.current.isLoading).toBe(false);
      expect(r2.current.isLoading).toBe(false);
    });

    // Two distinct query key variants
    expect(mockFetchLogs).toHaveBeenCalledTimes(2);
    expect(mockFetchLogs).toHaveBeenCalledWith({ level: "INFO" });
    expect(mockFetchLogs).toHaveBeenCalledWith({ level: "ERROR" });
  });
});
