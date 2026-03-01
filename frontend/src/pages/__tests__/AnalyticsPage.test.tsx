import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AnalyticsPage from "../AnalyticsPage";
import type { AuthUser } from "@/contexts/AuthContext";
import type {
  VolumeResponse,
  ClassificationDistributionResponse,
  AccuracyResponse,
  RoutingResponse,
} from "@/types/generated/api";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/hooks/useAnalytics", () => ({
  useVolume: vi.fn(),
  useDistribution: vi.fn(),
  useAccuracy: vi.fn(),
  useRoutingAnalytics: vi.fn(),
  useExportCsv: vi.fn(),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));

// Mock Chart to avoid recharts issues in jsdom
vi.mock("@/components/Chart", () => ({
  Chart: ({ title }: { title?: string }) => (
    <div data-testid="chart">{title ?? "chart"}</div>
  ),
}));

import {
  useVolume,
  useDistribution,
  useAccuracy,
  useRoutingAnalytics,
  useExportCsv,
} from "@/hooks/useAnalytics";
import { useAuth } from "@/contexts/AuthContext";

const mockUseVolume = vi.mocked(useVolume);
const mockUseDistribution = vi.mocked(useDistribution);
const mockUseAccuracy = vi.mocked(useAccuracy);
const mockUseRoutingAnalytics = vi.mocked(useRoutingAnalytics);
const mockUseExportCsv = vi.mocked(useExportCsv);
const mockUseAuth = vi.mocked(useAuth);

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderPage(client = makeQueryClient()) {
  return render(
    <MemoryRouter initialEntries={["/analytics"]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="*" element={<AnalyticsPage />} />
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

// ── Mock data ─────────────────────────────────────────────────────────────────

const mockVolume: VolumeResponse = {
  data_points: [
    { date: "2026-02-01", count: 25 },
    { date: "2026-02-02", count: 30 },
  ],
  total_emails: 1250,
  start_date: "2026-02-01",
  end_date: "2026-03-02",
};

const mockDistribution: ClassificationDistributionResponse = {
  actions: [
    { category: "respond", display_name: "Respond", count: 500, percentage: 55 },
    { category: "forward", display_name: "Forward", count: 200, percentage: 22 },
  ],
  types: [
    { category: "complaint", display_name: "Complaint", count: 300, percentage: 33 },
  ],
  total_classified: 900,
};

const mockAccuracy: AccuracyResponse = {
  total_classified: 900,
  total_overridden: 45,
  accuracy_pct: 95.0,
  period_start: "2026-02-01",
  period_end: "2026-03-02",
};

const mockRouting: RoutingResponse = {
  channels: [
    { channel: "slack", dispatched: 600, failed: 5, success_rate: 99.2 },
    { channel: "email", dispatched: 200, failed: 10, success_rate: 95.2 },
  ],
  total_dispatched: 800,
  total_failed: 15,
  unrouted_count: 50,
};

const mockAdminUser: AuthUser = {
  id: "u1",
  username: "admin",
  role: "admin",
};

const mockReviewerUser: AuthUser = {
  id: "u2",
  username: "reviewer",
  role: "reviewer",
};

// ── Tests ──────────────────────────────────────────────────────────────────────

describe("AnalyticsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockUseAuth.mockReturnValue({
      user: mockAdminUser,
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      getAccessToken: () => "tok",
    });

    mockUseVolume.mockReturnValue({
      data: mockVolume,
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

    mockUseDistribution.mockReturnValue({
      data: mockDistribution,
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

    mockUseAccuracy.mockReturnValue({
      data: mockAccuracy,
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

    mockUseRoutingAnalytics.mockReturnValue({
      data: mockRouting,
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

    mockUseExportCsv.mockReturnValue(makeNoopMutation() as never);
  });

  it("renders the page title", () => {
    renderPage();
    expect(screen.getByRole("heading", { level: 1, name: /^analytics$/i })).toBeInTheDocument();
  });

  it("renders DateRangeSelector with preset buttons", () => {
    renderPage();
    expect(screen.getByRole("button", { name: /7 days/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /30 days/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /90 days/i })).toBeInTheDocument();
  });

  it("renders 30 days preset as active by default (DEFAULT_DATE_PRESET = '30d')", () => {
    renderPage();
    // The active preset button has class date-range-selector__btn--active
    const thirtyDayBtn = screen.getByRole("button", { name: /30 days/i });
    expect(thirtyDayBtn.className).toContain("active");
  });

  it("renders Total Emails StatCard with value from volume data", () => {
    renderPage();
    expect(screen.getByText("Total Emails")).toBeInTheDocument();
    expect(screen.getByText("1250")).toBeInTheDocument();
  });

  it("renders Total Classified StatCard with value from distribution data", () => {
    renderPage();
    // "Total Classified" appears in both the StatCard label and the accuracy detail dl
    const labels = screen.getAllByText("Total Classified");
    expect(labels.length).toBeGreaterThanOrEqual(1);
    // "900" appears in both StatCard value and accuracy detail dd
    const values = screen.getAllByText("900");
    expect(values.length).toBeGreaterThanOrEqual(1);
  });

  it("renders Accuracy StatCard with formatted percentage", () => {
    renderPage();
    // "Accuracy" appears in both the StatCard label and the accuracy detail dl
    const labels = screen.getAllByText("Accuracy");
    expect(labels.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("95.0%")).toBeInTheDocument();
  });

  it("renders Total Dispatched StatCard with routing data value", () => {
    renderPage();
    expect(screen.getByText("Total Dispatched")).toBeInTheDocument();
    expect(screen.getByText("800")).toBeInTheDocument();
  });

  it("renders Email Volume chart section", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: /email volume/i })).toBeInTheDocument();
    expect(screen.getAllByTestId("chart").length).toBeGreaterThanOrEqual(1);
  });

  it("renders Actions Distribution chart section", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: /actions distribution/i })).toBeInTheDocument();
  });

  it("renders Routing Channels chart section", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: /routing channels/i })).toBeInTheDocument();
  });

  it("renders Classification Accuracy detail section when data is loaded", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: /classification accuracy/i })).toBeInTheDocument();
    expect(screen.getByText("45")).toBeInTheDocument();
  });

  it("shows Export CSV button for admin user", () => {
    renderPage();
    expect(screen.getByRole("button", { name: /export csv/i })).toBeInTheDocument();
  });

  it("does NOT show Export CSV button for reviewer user", () => {
    mockUseAuth.mockReturnValue({
      user: mockReviewerUser,
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      getAccessToken: () => "tok",
    });

    renderPage();
    expect(screen.queryByRole("button", { name: /export csv/i })).not.toBeInTheDocument();
  });

  it("Export CSV button is disabled while exporting", () => {
    mockUseExportCsv.mockReturnValue({
      ...makeNoopMutation(),
      isPending: true,
    } as never);

    renderPage();
    const exportBtn = screen.getByRole("button", { name: /exporting/i });
    expect(exportBtn).toBeDisabled();
  });

  it("clicking Export CSV calls exportCsv.mutate with current date range", async () => {
    const mutateFn = vi.fn();
    mockUseExportCsv.mockReturnValue({
      ...makeNoopMutation(),
      mutate: mutateFn,
    } as never);

    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /export csv/i }));

    // mutate is called with { startDate, endDate } only (no second callback arg)
    expect(mutateFn).toHaveBeenCalledWith(
      expect.objectContaining({ startDate: expect.any(String), endDate: expect.any(String) }),
    );
  });

  it("shows error alert when export fails", () => {
    mockUseExportCsv.mockReturnValue({
      ...makeNoopMutation(),
      error: new Error("Export failed — please try again"),
      isError: true,
    } as never);

    renderPage();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/export failed/i)).toBeInTheDocument();
  });

  it("shows chart skeleton when volume data is loading", () => {
    mockUseVolume.mockReturnValue({
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
    const busyElements = document.querySelectorAll('[aria-busy="true"]');
    expect(busyElements.length).toBeGreaterThanOrEqual(1);
  });

  it("shows volume error alert when volume fetch fails", () => {
    mockUseVolume.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Volume fetch error"),
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
    expect(screen.getByText(/failed to load volume data/i)).toBeInTheDocument();
  });

  it("clicking 7 days preset updates active state on button", async () => {
    const user = userEvent.setup();
    renderPage();

    const sevenDayBtn = screen.getByRole("button", { name: /7 days/i });
    await user.click(sevenDayBtn);

    expect(sevenDayBtn.className).toContain("active");
    // 30d is no longer active
    const thirtyDayBtn = screen.getByRole("button", { name: /30 days/i });
    expect(thirtyDayBtn.className).not.toContain("active");
  });

  it("shows — for accuracy when accuracy data is undefined", () => {
    mockUseAccuracy.mockReturnValue({
      data: undefined,
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
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
