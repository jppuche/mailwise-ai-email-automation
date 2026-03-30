// src/hooks/__tests__/useAnalytics.test.tsx
// Tests for useVolume, useDistribution, useAccuracy, useRoutingAnalytics,
// and useExportCsv hooks.
// Mocks the API module — exercises date params, data shapes, and CSV blob download.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type {
  VolumeResponse,
  ClassificationDistributionResponse,
  AccuracyResponse,
  RoutingResponse,
} from "@/types/generated/api";

// ─────────────────────────────────────────────────────────────────────────────
// API module mock — must precede hook imports
// ─────────────────────────────────────────────────────────────────────────────

vi.mock("@/api/analytics", () => ({
  fetchVolume: vi.fn(),
  fetchDistribution: vi.fn(),
  fetchAccuracy: vi.fn(),
  fetchRouting: vi.fn(),
  exportAnalyticsCsv: vi.fn(),
}));

import {
  fetchVolume,
  fetchDistribution,
  fetchAccuracy,
  fetchRouting,
  exportAnalyticsCsv,
} from "@/api/analytics";
import {
  useVolume,
  useDistribution,
  useAccuracy,
  useRoutingAnalytics,
  useExportCsv,
} from "../useAnalytics";

const mockFetchVolume = vi.mocked(fetchVolume);
const mockFetchDistribution = vi.mocked(fetchDistribution);
const mockFetchAccuracy = vi.mocked(fetchAccuracy);
const mockFetchRouting = vi.mocked(fetchRouting);
const mockExportAnalyticsCsv = vi.mocked(exportAnalyticsCsv);

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

function makeVolumeResponse(overrides: Partial<VolumeResponse> = {}): VolumeResponse {
  return {
    data_points: [
      { date: "2026-01-01", count: 5 },
      { date: "2026-01-02", count: 12 },
    ],
    total_emails: 17,
    start_date: "2026-01-01",
    end_date: "2026-01-31",
    ...overrides,
  };
}

function makeDistributionResponse(
  overrides: Partial<ClassificationDistributionResponse> = {},
): ClassificationDistributionResponse {
  return {
    actions: [
      { category: "respond", display_name: "Respond", count: 10, percentage: 50 },
      { category: "escalate", display_name: "Escalate", count: 10, percentage: 50 },
    ],
    types: [
      { category: "inquiry", display_name: "Inquiry", count: 20, percentage: 100 },
    ],
    total_classified: 20,
    ...overrides,
  };
}

function makeAccuracyResponse(overrides: Partial<AccuracyResponse> = {}): AccuracyResponse {
  return {
    total_classified: 100,
    total_overridden: 5,
    accuracy_pct: 95.0,
    period_start: "2026-01-01",
    period_end: "2026-01-31",
    ...overrides,
  };
}

function makeRoutingResponse(overrides: Partial<RoutingResponse> = {}): RoutingResponse {
  return {
    channels: [
      { channel: "slack", dispatched: 15, failed: 1, success_rate: 93.75 },
      { channel: "email", dispatched: 5, failed: 0, success_rate: 100 },
    ],
    total_dispatched: 20,
    total_failed: 1,
    unrouted_count: 3,
    ...overrides,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// useVolume
// ─────────────────────────────────────────────────────────────────────────────

describe("useVolume", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("passes startDate and endDate to fetchVolume", async () => {
    const response = makeVolumeResponse();
    mockFetchVolume.mockResolvedValueOnce(response);

    const wrapper = createWrapper();
    renderHook(() => useVolume("2026-01-01", "2026-01-31"), { wrapper });

    await waitFor(() => {
      expect(mockFetchVolume).toHaveBeenCalledOnce();
    });

    expect(mockFetchVolume).toHaveBeenCalledWith("2026-01-01", "2026-01-31");
  });

  it("returns volume data after fetch resolves", async () => {
    const response = makeVolumeResponse();
    mockFetchVolume.mockResolvedValueOnce(response);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useVolume("2026-01-01", "2026-01-31"), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.data).toEqual(response);
    expect(result.current.data?.total_emails).toBe(17);
    expect(result.current.data?.data_points).toHaveLength(2);
  });

  it("uses different query keys for different date ranges", async () => {
    mockFetchVolume.mockResolvedValue(makeVolumeResponse());

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result: r1 } = renderHook(() => useVolume("2026-01-01", "2026-01-31"), { wrapper });
    const { result: r2 } = renderHook(() => useVolume("2026-02-01", "2026-02-28"), { wrapper });

    await waitFor(() => {
      expect(r1.current.isLoading).toBe(false);
      expect(r2.current.isLoading).toBe(false);
    });

    // Two distinct calls — one per date range
    expect(mockFetchVolume).toHaveBeenCalledTimes(2);
    expect(mockFetchVolume).toHaveBeenCalledWith("2026-01-01", "2026-01-31");
    expect(mockFetchVolume).toHaveBeenCalledWith("2026-02-01", "2026-02-28");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// useDistribution
// ─────────────────────────────────────────────────────────────────────────────

describe("useDistribution", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("passes startDate and endDate to fetchDistribution", async () => {
    mockFetchDistribution.mockResolvedValueOnce(makeDistributionResponse());

    const wrapper = createWrapper();
    renderHook(() => useDistribution("2026-01-01", "2026-01-31"), { wrapper });

    await waitFor(() => {
      expect(mockFetchDistribution).toHaveBeenCalledOnce();
    });

    expect(mockFetchDistribution).toHaveBeenCalledWith("2026-01-01", "2026-01-31");
  });

  it("returns distribution data correctly", async () => {
    const response = makeDistributionResponse();
    mockFetchDistribution.mockResolvedValueOnce(response);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useDistribution("2026-01-01", "2026-01-31"), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.data?.actions).toHaveLength(2);
    expect(result.current.data?.types).toHaveLength(1);
    expect(result.current.data?.total_classified).toBe(20);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// useAccuracy
// ─────────────────────────────────────────────────────────────────────────────

describe("useAccuracy", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("passes startDate and endDate to fetchAccuracy", async () => {
    mockFetchAccuracy.mockResolvedValueOnce(makeAccuracyResponse());

    const wrapper = createWrapper();
    renderHook(() => useAccuracy("2026-01-01", "2026-01-31"), { wrapper });

    await waitFor(() => {
      expect(mockFetchAccuracy).toHaveBeenCalledOnce();
    });

    expect(mockFetchAccuracy).toHaveBeenCalledWith("2026-01-01", "2026-01-31");
  });

  it("returns accuracy data with accuracy_pct", async () => {
    const response = makeAccuracyResponse({ accuracy_pct: 87.5 });
    mockFetchAccuracy.mockResolvedValueOnce(response);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useAccuracy("2026-01-01", "2026-01-31"), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.data?.accuracy_pct).toBe(87.5);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// useRoutingAnalytics
// ─────────────────────────────────────────────────────────────────────────────

describe("useRoutingAnalytics", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("passes startDate and endDate to fetchRouting", async () => {
    mockFetchRouting.mockResolvedValueOnce(makeRoutingResponse());

    const wrapper = createWrapper();
    renderHook(() => useRoutingAnalytics("2026-01-01", "2026-01-31"), { wrapper });

    await waitFor(() => {
      expect(mockFetchRouting).toHaveBeenCalledOnce();
    });

    expect(mockFetchRouting).toHaveBeenCalledWith("2026-01-01", "2026-01-31");
  });

  it("returns routing stats with channel data", async () => {
    const response = makeRoutingResponse();
    mockFetchRouting.mockResolvedValueOnce(response);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useRoutingAnalytics("2026-01-01", "2026-01-31"), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.data?.channels).toHaveLength(2);
    expect(result.current.data?.total_dispatched).toBe(20);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// useExportCsv
// ─────────────────────────────────────────────────────────────────────────────

describe("useExportCsv", () => {
  // jsdom does not implement URL.createObjectURL or URL.revokeObjectURL.
  // Define them directly on the URL object (configurable) before each test.
  let createObjectURLMock: ReturnType<typeof vi.fn>;
  let revokeObjectURLMock: ReturnType<typeof vi.fn>;

  beforeAll(() => {
    // Define the stubs once — they will be replaced per-test via mock.mockReturnValue
    Object.defineProperty(URL, "createObjectURL", {
      value: vi.fn(),
      writable: true,
      configurable: true,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      value: vi.fn(),
      writable: true,
      configurable: true,
    });
  });

  beforeEach(() => {
    vi.clearAllMocks();
    // Reassign fresh mocks each test
    createObjectURLMock = vi.fn().mockReturnValue("blob:http://localhost/mock-url");
    revokeObjectURLMock = vi.fn();
    (URL.createObjectURL as ReturnType<typeof vi.fn>) = createObjectURLMock;
    (URL.revokeObjectURL as ReturnType<typeof vi.fn>) = revokeObjectURLMock;
  });

  it("calls exportAnalyticsCsv with startDate and endDate", async () => {
    const mockBlob = new Blob(["col1,col2\nval1,val2"], { type: "text/csv" });
    mockExportAnalyticsCsv.mockResolvedValueOnce(mockBlob);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useExportCsv(), { wrapper });

    result.current.mutate({ startDate: "2026-01-01", endDate: "2026-01-31" });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockExportAnalyticsCsv).toHaveBeenCalledWith("2026-01-01", "2026-01-31");
  });

  it("calls URL.createObjectURL with the blob from the API", async () => {
    const mockBlob = new Blob(["data"], { type: "text/csv" });
    mockExportAnalyticsCsv.mockResolvedValueOnce(mockBlob);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useExportCsv(), { wrapper });

    result.current.mutate({ startDate: "2026-01-01", endDate: "2026-01-31" });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(createObjectURLMock).toHaveBeenCalledWith(mockBlob);
  });

  it("calls URL.revokeObjectURL after download completes", async () => {
    const mockBlob = new Blob(["data"], { type: "text/csv" });
    mockExportAnalyticsCsv.mockResolvedValueOnce(mockBlob);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useExportCsv(), { wrapper });

    result.current.mutate({ startDate: "2026-01-01", endDate: "2026-01-31" });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(revokeObjectURLMock).toHaveBeenCalledWith("blob:http://localhost/mock-url");
  });

  it("triggers download with correct filename for the date range", async () => {
    const mockBlob = new Blob(["data"], { type: "text/csv" });
    mockExportAnalyticsCsv.mockResolvedValueOnce(mockBlob);

    // Capture the anchor element that the hook creates and clicks
    const anchors: HTMLAnchorElement[] = [];
    const originalAppendChild = document.body.appendChild.bind(document.body);
    vi.spyOn(document.body, "appendChild").mockImplementation((node) => {
      if (node instanceof HTMLAnchorElement) anchors.push(node);
      return originalAppendChild(node);
    });

    const wrapper = createWrapper();
    const { result } = renderHook(() => useExportCsv(), { wrapper });

    result.current.mutate({ startDate: "2026-01-01", endDate: "2026-01-31" });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    vi.restoreAllMocks();

    // Verify the anchor had the right filename
    expect(anchors).toHaveLength(1);
    expect(anchors[0].download).toBe("emails_2026-01-01_2026-01-31.csv");
  });
});
