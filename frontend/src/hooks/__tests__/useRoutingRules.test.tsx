// src/hooks/__tests__/useRoutingRules.test.tsx
// Tests for useRoutingRules and useRoutingRuleMutations hooks.
// Mocks the API module — exercises sort order, CRUD mutations,
// reorder payload shape, and toggleActive convenience wrapper.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type {
  RoutingRuleResponse,
  RoutingRuleCreate,
} from "@/types/generated/api";

// ─────────────────────────────────────────────────────────────────────────────
// API module mock — must precede hook imports
// ─────────────────────────────────────────────────────────────────────────────

vi.mock("@/api/routing-rules", () => ({
  fetchRoutingRules: vi.fn(),
  fetchRoutingRule: vi.fn(),
  createRoutingRule: vi.fn(),
  updateRoutingRule: vi.fn(),
  deleteRoutingRule: vi.fn(),
  reorderRoutingRules: vi.fn(),
  testRoutingRules: vi.fn(),
}));

import {
  fetchRoutingRules,
  createRoutingRule,
  updateRoutingRule,
  deleteRoutingRule,
  reorderRoutingRules,
} from "@/api/routing-rules";
import { useRoutingRules, useRoutingRuleMutations } from "../useRoutingRules";

const mockFetchRoutingRules = vi.mocked(fetchRoutingRules);
const mockCreateRoutingRule = vi.mocked(createRoutingRule);
const mockUpdateRoutingRule = vi.mocked(updateRoutingRule);
const mockDeleteRoutingRule = vi.mocked(deleteRoutingRule);
const mockReorderRoutingRules = vi.mocked(reorderRoutingRules);

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

function makeRule(overrides: Partial<RoutingRuleResponse> = {}): RoutingRuleResponse {
  return {
    id: "rule-1",
    name: "Test Rule",
    is_active: true,
    priority: 1,
    conditions: [{ field: "action_slug", operator: "eq", value: "urgent" }],
    actions: [{ channel: "slack", destination: "#alerts" }],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// useRoutingRules
// ─────────────────────────────────────────────────────────────────────────────

describe("useRoutingRules", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls fetchRoutingRules once on mount", async () => {
    mockFetchRoutingRules.mockResolvedValueOnce([]);

    const wrapper = createWrapper();
    renderHook(() => useRoutingRules(), { wrapper });

    await waitFor(() => {
      expect(mockFetchRoutingRules).toHaveBeenCalledOnce();
    });
  });

  it("returns rules sorted by priority ascending", async () => {
    const unsorted = [
      makeRule({ id: "rule-3", priority: 3, name: "Low Priority" }),
      makeRule({ id: "rule-1", priority: 1, name: "High Priority" }),
      makeRule({ id: "rule-2", priority: 2, name: "Mid Priority" }),
    ];
    mockFetchRoutingRules.mockResolvedValueOnce(unsorted);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useRoutingRules(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.data).toHaveLength(3);
    expect(result.current.data?.[0].priority).toBe(1);
    expect(result.current.data?.[1].priority).toBe(2);
    expect(result.current.data?.[2].priority).toBe(3);
    expect(result.current.data?.[0].name).toBe("High Priority");
  });

  it("returns isLoading true before fetch resolves", () => {
    mockFetchRoutingRules.mockReturnValue(new Promise(() => {}));

    const wrapper = createWrapper();
    const { result } = renderHook(() => useRoutingRules(), { wrapper });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.data).toBeUndefined();
  });

  it("does not mutate the original array from the API response", async () => {
    const original = [
      makeRule({ id: "rule-2", priority: 2 }),
      makeRule({ id: "rule-1", priority: 1 }),
    ];
    mockFetchRoutingRules.mockResolvedValueOnce(original);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useRoutingRules(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    // Original array order should be untouched
    expect(original[0].priority).toBe(2);
  });

  it("exposes isError when fetch rejects", async () => {
    mockFetchRoutingRules.mockRejectedValueOnce(new Error("Forbidden"));

    const wrapper = createWrapper();
    const { result } = renderHook(() => useRoutingRules(), { wrapper });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// useRoutingRuleMutations — create
// ─────────────────────────────────────────────────────────────────────────────

describe("useRoutingRuleMutations().create", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls createRoutingRule with the provided body", async () => {
    const created = makeRule({ id: "new-rule" });
    mockCreateRoutingRule.mockResolvedValueOnce(created);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useRoutingRuleMutations(), { wrapper });

    const body: RoutingRuleCreate = {
      name: "Slack Alerts",
      is_active: true,
      conditions: [{ field: "action_slug", operator: "eq", value: "urgent" }],
      actions: [{ channel: "slack", destination: "#alerts" }],
    };
    result.current.create.mutate(body);

    await waitFor(() => {
      expect(result.current.create.isSuccess).toBe(true);
    });

    expect(mockCreateRoutingRule).toHaveBeenCalledWith(body);
  });

  it("invalidates ['routing-rules'] cache on create success", async () => {
    const created = makeRule({ id: "new-rule" });
    mockCreateRoutingRule.mockResolvedValueOnce(created);
    mockFetchRoutingRules.mockResolvedValue([created]);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    await queryClient.prefetchQuery({
      queryKey: ["routing-rules"],
      queryFn: () => mockFetchRoutingRules(),
    });

    const { result } = renderHook(() => useRoutingRuleMutations(), { wrapper });

    result.current.create.mutate({
      name: "New Rule",
      conditions: [{ field: "action_slug", operator: "eq", value: "urgent" }],
      actions: [{ channel: "slack", destination: "#alerts" }],
    });

    await waitFor(() => {
      expect(result.current.create.isSuccess).toBe(true);
    });

    const queryState = queryClient.getQueryState(["routing-rules"]);
    expect(queryState?.isInvalidated).toBe(true);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// useRoutingRuleMutations — reorder
// ─────────────────────────────────────────────────────────────────────────────

describe("useRoutingRuleMutations().reorder", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("sends ordered_ids[] array to reorderRoutingRules", async () => {
    const reordered = [
      makeRule({ id: "rule-2", priority: 1 }),
      makeRule({ id: "rule-1", priority: 2 }),
    ];
    mockReorderRoutingRules.mockResolvedValueOnce(reordered);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useRoutingRuleMutations(), { wrapper });

    result.current.reorder.mutate(["rule-2", "rule-1"]);

    await waitFor(() => {
      expect(result.current.reorder.isSuccess).toBe(true);
    });

    expect(mockReorderRoutingRules).toHaveBeenCalledWith(["rule-2", "rule-1"]);
  });

  it("invalidates ['routing-rules'] cache on reorder success", async () => {
    const reordered = [makeRule({ id: "rule-1" })];
    mockReorderRoutingRules.mockResolvedValueOnce(reordered);
    mockFetchRoutingRules.mockResolvedValue(reordered);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    await queryClient.prefetchQuery({
      queryKey: ["routing-rules"],
      queryFn: () => mockFetchRoutingRules(),
    });

    const { result } = renderHook(() => useRoutingRuleMutations(), { wrapper });

    result.current.reorder.mutate(["rule-1"]);

    await waitFor(() => {
      expect(result.current.reorder.isSuccess).toBe(true);
    });

    const queryState = queryClient.getQueryState(["routing-rules"]);
    expect(queryState?.isInvalidated).toBe(true);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// useRoutingRuleMutations — toggleActive
// ─────────────────────────────────────────────────────────────────────────────

describe("useRoutingRuleMutations().toggleActive", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls updateRoutingRule with { is_active: true } when toggling on", async () => {
    const updated = makeRule({ id: "rule-1", is_active: true });
    mockUpdateRoutingRule.mockResolvedValueOnce(updated);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useRoutingRuleMutations(), { wrapper });

    result.current.toggleActive.mutate({ id: "rule-1", isActive: true });

    await waitFor(() => {
      expect(result.current.toggleActive.isSuccess).toBe(true);
    });

    expect(mockUpdateRoutingRule).toHaveBeenCalledWith("rule-1", { is_active: true });
  });

  it("calls updateRoutingRule with { is_active: false } when toggling off", async () => {
    const updated = makeRule({ id: "rule-1", is_active: false });
    mockUpdateRoutingRule.mockResolvedValueOnce(updated);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useRoutingRuleMutations(), { wrapper });

    result.current.toggleActive.mutate({ id: "rule-1", isActive: false });

    await waitFor(() => {
      expect(result.current.toggleActive.isSuccess).toBe(true);
    });

    expect(mockUpdateRoutingRule).toHaveBeenCalledWith("rule-1", { is_active: false });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// useRoutingRuleMutations — remove
// ─────────────────────────────────────────────────────────────────────────────

describe("useRoutingRuleMutations().remove", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls deleteRoutingRule with the rule id", async () => {
    mockDeleteRoutingRule.mockResolvedValueOnce(undefined);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useRoutingRuleMutations(), { wrapper });

    result.current.remove.mutate("rule-1");

    await waitFor(() => {
      expect(result.current.remove.isSuccess).toBe(true);
    });

    expect(mockDeleteRoutingRule).toHaveBeenCalledWith("rule-1");
  });
});
