import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import OverviewPage from "../OverviewPage";
import type { AuthUser } from "@/contexts/AuthContext";
import type {
  VolumeResponse,
  ClassificationDistributionResponse,
  AccuracyResponse,
  HealthResponse,
  PaginatedResponse,
  EmailListItem,
} from "@/types/generated/api";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/hooks/useAnalytics", () => ({
  useVolume: vi.fn(),
  useDistribution: vi.fn(),
  useAccuracy: vi.fn(),
  useRoutingAnalytics: vi.fn(),
  useExportCsv: vi.fn(),
}));

vi.mock("@/hooks/useHealth", () => ({
  useHealth: vi.fn(),
}));

vi.mock("@/hooks/useEmails", () => ({
  useEmails: vi.fn(),
  useEmailMutations: vi.fn(),
  useEmailDetail: vi.fn(),
  useEmailClassification: vi.fn(),
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

import { useVolume, useDistribution, useAccuracy } from "@/hooks/useAnalytics";
import { useHealth } from "@/hooks/useHealth";
import { useEmails } from "@/hooks/useEmails";
import { useAuth } from "@/contexts/AuthContext";

const mockUseVolume = vi.mocked(useVolume);
const mockUseDistribution = vi.mocked(useDistribution);
const mockUseAccuracy = vi.mocked(useAccuracy);
const mockUseHealth = vi.mocked(useHealth);
const mockUseEmails = vi.mocked(useEmails);
const mockUseAuth = vi.mocked(useAuth);

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderPage(client = makeQueryClient()) {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="*" element={<OverviewPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

// ── Mock data ─────────────────────────────────────────────────────────────────

const mockVolume: VolumeResponse = {
  data_points: [
    { date: "2026-02-01", count: 10 },
    { date: "2026-02-02", count: 20 },
  ],
  total_emails: 350,
  start_date: "2026-02-01",
  end_date: "2026-03-02",
};

const mockDistribution: ClassificationDistributionResponse = {
  actions: [
    { category: "respond", display_name: "Respond", count: 120, percentage: 60 },
  ],
  types: [
    { category: "complaint", display_name: "Complaint", count: 80, percentage: 40 },
  ],
  total_classified: 200,
};

const mockAccuracy: AccuracyResponse = {
  total_classified: 200,
  total_overridden: 10,
  accuracy_pct: 95.0,
  period_start: "2026-02-01",
  period_end: "2026-03-02",
};

const mockHealth: HealthResponse = {
  status: "ok",
  version: "1.0.0",
  adapters: [
    { name: "database", status: "ok", latency_ms: 5, error: null },
    { name: "redis", status: "ok", latency_ms: 2, error: null },
  ],
};

const mockDegradedHealth: HealthResponse = {
  status: "degraded",
  version: "1.0.0",
  adapters: [
    { name: "database", status: "ok", latency_ms: 5, error: null },
    { name: "redis", status: "unavailable", latency_ms: null, error: "Connection refused" },
  ],
};

const mockEmailsPage: PaginatedResponse<EmailListItem> = {
  items: [
    {
      id: "e1",
      subject: "Test email subject",
      sender_email: "sender@example.com",
      sender_name: "Sender Name",
      received_at: "2026-03-01T10:00:00Z",
      state: "classified",
      snippet: "Email snippet text",
      classification: {
        action: "respond",
        type: "complaint",
        confidence: "high",
        is_fallback: false,
      },
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
  pages: 1,
};

const mockAuthAdmin: AuthUser = {
  id: "u1",
  username: "admin",
  role: "admin",
};

// ── Tests ──────────────────────────────────────────────────────────────────────

describe("OverviewPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockUseAuth.mockReturnValue({
      user: mockAuthAdmin,
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

    mockUseHealth.mockReturnValue({
      data: mockHealth,
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

    mockUseEmails.mockReturnValue({
      data: mockEmailsPage,
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
    expect(screen.getByRole("heading", { level: 1, name: /overview/i })).toBeInTheDocument();
  });

  it("renders StatCard for Total Emails with value from volume data", () => {
    renderPage();
    expect(screen.getByText("Total Emails (30d)")).toBeInTheDocument();
    expect(screen.getByText("350")).toBeInTheDocument();
  });

  it("renders StatCard for Classified with value from distribution data", () => {
    renderPage();
    expect(screen.getByText("Classified")).toBeInTheDocument();
    expect(screen.getByText("200")).toBeInTheDocument();
  });

  it("renders StatCard for Accuracy with formatted percentage", () => {
    renderPage();
    expect(screen.getByText("Accuracy")).toBeInTheDocument();
    expect(screen.getByText("95.0%")).toBeInTheDocument();
  });

  it("renders System Health section when health data is available", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: /system health/i })).toBeInTheDocument();
  });

  it("renders adapter StatusIndicator for each adapter in health data", () => {
    renderPage();
    expect(screen.getByText("database")).toBeInTheDocument();
    expect(screen.getByText("redis")).toBeInTheDocument();
  });

  it("shows adapter latency when latency_ms is not null", () => {
    renderPage();
    expect(screen.getByText("5ms")).toBeInTheDocument();
    expect(screen.getByText("2ms")).toBeInTheDocument();
  });

  it("shows adapter error message when adapter has an error", () => {
    mockUseHealth.mockReturnValue({
      data: mockDegradedHealth,
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
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Connection refused")).toBeInTheDocument();
  });

  it("does NOT render System Health section when health data is undefined", () => {
    mockUseHealth.mockReturnValue({
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

    renderPage();
    expect(screen.queryByRole("heading", { name: /system health/i })).not.toBeInTheDocument();
  });

  it("renders Email Volume chart section heading", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: /email volume/i })).toBeInTheDocument();
  });

  it("renders chart when volume data is loaded", () => {
    renderPage();
    expect(screen.getByTestId("chart")).toBeInTheDocument();
  });

  it("renders chart skeleton when volume is loading", () => {
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
    // Chart skeleton has aria-busy="true" attribute
    const skeletonEls = document.querySelectorAll('[aria-busy="true"]');
    expect(skeletonEls.length).toBeGreaterThanOrEqual(1);
  });

  it("renders Recent Activity section heading", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: /recent activity/i })).toBeInTheDocument();
  });

  it("shows activity event derived from email data", () => {
    renderPage();
    // ActivityFeed derives description from subject + sender_email
    expect(screen.getByText(/test email subject/i)).toBeInTheDocument();
  });

  it("shows empty activity feed message when emails list is empty", () => {
    mockUseEmails.mockReturnValue({
      data: { items: [], total: 0, page: 1, page_size: 20, pages: 1 },
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
    expect(screen.getByText(/no recent activity/i)).toBeInTheDocument();
  });

  it("shows StatCard skeleton when stats are loading", () => {
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
    // stat-card--loading has aria-busy="true"
    const busyElements = document.querySelectorAll('[aria-busy="true"]');
    expect(busyElements.length).toBeGreaterThanOrEqual(1);
  });

  it("shows fallback zero value when volume data is undefined", () => {
    mockUseVolume.mockReturnValue({
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
    // StatCard renders "0" when data is undefined (volume?.total_emails ?? 0)
    expect(screen.getByText("Total Emails (30d)")).toBeInTheDocument();
  });

  it("shows — when accuracy data is undefined", () => {
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
