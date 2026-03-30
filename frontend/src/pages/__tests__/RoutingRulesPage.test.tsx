import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import RoutingRulesPage from "../RoutingRulesPage";
import type {
  RoutingRuleResponse,
} from "@/types/generated/api";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/hooks/useRoutingRules", () => ({
  useRoutingRules: vi.fn(),
  useRoutingRuleMutations: vi.fn(),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));

import { useRoutingRules, useRoutingRuleMutations } from "@/hooks/useRoutingRules";
import { useAuth } from "@/contexts/AuthContext";

const mockUseRoutingRules = vi.mocked(useRoutingRules);
const mockUseRoutingRuleMutations = vi.mocked(useRoutingRuleMutations);
const mockUseAuth = vi.mocked(useAuth);

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderPage(client = makeQueryClient()) {
  return render(
    <MemoryRouter initialEntries={["/routing"]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="*" element={<RoutingRulesPage />} />
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

function makeMockMutations() {
  return {
    create: makeNoopMutation() as never,
    update: makeNoopMutation() as never,
    remove: makeNoopMutation() as never,
    reorder: makeNoopMutation() as never,
    toggleActive: makeNoopMutation() as never,
    test: makeNoopMutation() as never,
  };
}

// ── Mock data ─────────────────────────────────────────────────────────────────

const mockRule1: RoutingRuleResponse = {
  id: "rule-1",
  name: "Slack Routing Rule",
  is_active: true,
  priority: 1,
  conditions: [
    { field: "action_slug", operator: "eq", value: "respond" },
  ],
  actions: [
    { channel: "slack", destination: "#support", template_id: null },
  ],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const mockRule2: RoutingRuleResponse = {
  id: "rule-2",
  name: "Email Escalation Rule",
  is_active: false,
  priority: 2,
  conditions: [
    { field: "type_slug", operator: "eq", value: "complaint" },
  ],
  actions: [
    { channel: "email", destination: "manager@example.com", template_id: null },
  ],
  created_at: "2026-01-02T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
};

// ── Tests ──────────────────────────────────────────────────────────────────────

describe("RoutingRulesPage", () => {
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

    mockUseRoutingRules.mockReturnValue({
      data: [mockRule1, mockRule2],
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

    mockUseRoutingRuleMutations.mockReturnValue(makeMockMutations());
  });

  it("renders the page title", () => {
    renderPage();
    expect(screen.getByRole("heading", { level: 1, name: /routing rules/i })).toBeInTheDocument();
  });

  it("renders 'New Rule' button", () => {
    renderPage();
    expect(screen.getByRole("button", { name: /new rule/i })).toBeInTheDocument();
  });

  it("renders 'Test Rules' toggle button", () => {
    renderPage();
    expect(screen.getByRole("button", { name: /test rules/i })).toBeInTheDocument();
  });

  it("renders rule cards from mock data", () => {
    renderPage();
    expect(screen.getByText("Slack Routing Rule")).toBeInTheDocument();
    expect(screen.getByText("Email Escalation Rule")).toBeInTheDocument();
  });

  it("renders rules with priority labels", () => {
    renderPage();
    expect(screen.getByText("Priority 1")).toBeInTheDocument();
    expect(screen.getByText("Priority 2")).toBeInTheDocument();
  });

  it("shows condition chips on rule cards", () => {
    renderPage();
    expect(screen.getByText(/action_slug eq respond/i)).toBeInTheDocument();
  });

  it("shows action items on rule cards", () => {
    renderPage();
    expect(screen.getByText(/slack: #support/i)).toBeInTheDocument();
  });

  it("toggle checkbox is checked for active rule", () => {
    renderPage();
    const toggle = screen.getByRole("switch", { name: /toggle slack routing rule active/i });
    expect(toggle).toBeChecked();
  });

  it("toggle checkbox is unchecked for inactive rule", () => {
    renderPage();
    const toggle = screen.getByRole("switch", { name: /toggle email escalation rule active/i });
    expect(toggle).not.toBeChecked();
  });

  it("clicking toggle calls toggleActive mutation", async () => {
    const toggleActiveFn = vi.fn();
    mockUseRoutingRuleMutations.mockReturnValue({
      ...makeMockMutations(),
      toggleActive: { ...makeNoopMutation(), mutate: toggleActiveFn } as never,
    });

    const user = userEvent.setup();
    renderPage();

    const toggle = screen.getByRole("switch", { name: /toggle slack routing rule active/i });
    await user.click(toggle);

    // Page calls mutations.toggleActive.mutate({ id, isActive }) without a callback
    expect(toggleActiveFn).toHaveBeenCalledWith({ id: "rule-1", isActive: false });
  });

  it("clicking Edit button opens RuleBuilder", async () => {
    const user = userEvent.setup();
    renderPage();

    const editBtn = screen.getByRole("button", { name: /edit slack routing rule/i });
    await user.click(editBtn);

    // RuleBuilder renders a modal-like form — at minimum, a close/cancel button appears
    expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
  });

  it("clicking Delete button shows confirmation dialog", async () => {
    const user = userEvent.setup();
    renderPage();

    const deleteBtn = screen.getByRole("button", { name: /delete slack routing rule/i });
    await user.click(deleteBtn);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/are you sure you want to delete/i)).toBeInTheDocument();
  });

  it("confirming delete calls remove mutation", async () => {
    const removeFn = vi.fn();
    mockUseRoutingRuleMutations.mockReturnValue({
      ...makeMockMutations(),
      remove: { ...makeNoopMutation(), mutate: removeFn } as never,
    });

    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /delete slack routing rule/i }));
    const confirmBtn = screen.getByRole("button", { name: /^delete$/i });
    await user.click(confirmBtn);

    // Page calls mutations.remove.mutate(id) without a callback
    expect(removeFn).toHaveBeenCalledWith("rule-1");
  });

  it("canceling delete dialog closes it without calling remove", async () => {
    const removeFn = vi.fn();
    mockUseRoutingRuleMutations.mockReturnValue({
      ...makeMockMutations(),
      remove: { ...makeNoopMutation(), mutate: removeFn } as never,
    });

    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /delete slack routing rule/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(removeFn).not.toHaveBeenCalled();
  });

  it("clicking 'New Rule' button opens RuleBuilder in create mode", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /new rule/i }));

    expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
  });

  it("clicking 'Test Rules' shows test panel", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /test rules/i }));

    // Test panel renders — button text changes to "Hide Test Panel"
    expect(screen.getByRole("button", { name: /hide test panel/i })).toBeInTheDocument();
  });

  it("shows loading state when rules are loading", () => {
    mockUseRoutingRules.mockReturnValue({
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
    // Loading state renders Skeleton components with aria-busy container
    const busyElements = document.querySelectorAll('[aria-busy="true"]');
    expect(busyElements.length).toBeGreaterThanOrEqual(1);
  });

  it("shows error alert when rules fail to load", () => {
    mockUseRoutingRules.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Server error"),
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
    expect(screen.getByText(/failed to load routing rules/i)).toBeInTheDocument();
  });

  it("shows empty state when no rules exist", () => {
    mockUseRoutingRules.mockReturnValue({
      data: [],
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
    expect(screen.getByText(/no routing rules defined yet/i)).toBeInTheDocument();
    // "Create First Rule" button also present in empty state
    expect(screen.getByRole("button", { name: /create first rule/i })).toBeInTheDocument();
  });
});
