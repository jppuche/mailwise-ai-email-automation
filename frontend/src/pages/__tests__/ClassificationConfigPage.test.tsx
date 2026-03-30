import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ClassificationConfigPage from "../ClassificationConfigPage";
import type {
  ActionCategoryResponse,
  TypeCategoryResponse,
  FewShotExampleResponse,
  LLMIntegrationConfig,
} from "@/types/generated/api";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/hooks/useCategories", () => ({
  useActionCategories: vi.fn(),
  useTypeCategories: vi.fn(),
  useCategoryMutations: vi.fn(),
  useFewShotExamples: vi.fn(),
  useFewShotMutations: vi.fn(),
  useLLMConfig: vi.fn(),
  useTestLLM: vi.fn(),
}));

import {
  useActionCategories,
  useTypeCategories,
  useCategoryMutations,
  useFewShotExamples,
  useFewShotMutations,
  useLLMConfig,
  useTestLLM,
} from "@/hooks/useCategories";

const mockUseActionCategories = vi.mocked(useActionCategories);
const mockUseTypeCategories = vi.mocked(useTypeCategories);
const mockUseCategoryMutations = vi.mocked(useCategoryMutations);
const mockUseFewShotExamples = vi.mocked(useFewShotExamples);
const mockUseFewShotMutations = vi.mocked(useFewShotMutations);
const mockUseLLMConfig = vi.mocked(useLLMConfig);
const mockUseTestLLM = vi.mocked(useTestLLM);

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderPage(client = makeQueryClient()) {
  return render(
    <MemoryRouter initialEntries={["/classification"]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="*" element={<ClassificationConfigPage />} />
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

function makeCategoryMutations() {
  return {
    create: makeNoopMutation() as never,
    update: makeNoopMutation() as never,
    remove: makeNoopMutation() as never,
    reorder: makeNoopMutation() as never,
  };
}

function makeFewShotMutations() {
  return {
    create: makeNoopMutation() as never,
    update: makeNoopMutation() as never,
    remove: makeNoopMutation() as never,
  };
}

// ── Mock data ─────────────────────────────────────────────────────────────────

const mockActionCategories: ActionCategoryResponse[] = [
  {
    id: "1",
    slug: "respond",
    name: "Respond",
    description: "Direct reply",
    is_fallback: false,
    is_active: true,
    display_order: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
];

const mockTypeCategories: TypeCategoryResponse[] = [
  {
    id: "3",
    slug: "complaint",
    name: "Complaint",
    description: "Customer complaint",
    is_fallback: false,
    is_active: true,
    display_order: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
];

const mockFewShotExamples: FewShotExampleResponse[] = [
  {
    id: "ex-1",
    email_snippet: "I am very unhappy with the service provided...",
    action_slug: "respond",
    type_slug: "complaint",
    rationale: "Clear complaint needing response",
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
];

const mockLLMConfig: LLMIntegrationConfig = {
  openai_api_key_configured: true,
  anthropic_api_key_configured: false,
  classify_model: "gpt-4o-mini",
  draft_model: "gpt-4o",
  temperature_classify: 0.1,
  temperature_draft: 0.7,
  fallback_model: "gpt-3.5-turbo",
  timeout_seconds: 30,
  base_url: "https://api.openai.com/v1",
};

// ── Tests ──────────────────────────────────────────────────────────────────────

describe("ClassificationConfigPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // Default: loaded data, no errors
    mockUseActionCategories.mockReturnValue({
      data: mockActionCategories,
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

    mockUseTypeCategories.mockReturnValue({
      data: mockTypeCategories,
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

    mockUseCategoryMutations.mockReturnValue(makeCategoryMutations());

    mockUseFewShotExamples.mockReturnValue({
      data: mockFewShotExamples,
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

    mockUseFewShotMutations.mockReturnValue(makeFewShotMutations());

    mockUseLLMConfig.mockReturnValue({
      data: mockLLMConfig,
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

    mockUseTestLLM.mockReturnValue(makeNoopMutation() as never);
  });

  it("renders the page title", () => {
    renderPage();
    expect(screen.getByRole("heading", { level: 1, name: /classification config/i })).toBeInTheDocument();
  });

  it("renders Action Categories section heading", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: /action categories/i })).toBeInTheDocument();
  });

  it("renders Type Categories section heading", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: /type categories/i })).toBeInTheDocument();
  });

  it("renders Few-Shot Examples section heading", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: /few-shot examples/i })).toBeInTheDocument();
  });

  it("renders LLM Configuration section heading", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: /llm configuration/i })).toBeInTheDocument();
  });

  it("renders action category names from hook data", () => {
    renderPage();
    expect(screen.getByText("Respond")).toBeInTheDocument();
  });

  it("renders type category names from hook data", () => {
    renderPage();
    expect(screen.getByText("Complaint")).toBeInTheDocument();
  });

  it("renders few-shot example snippets", () => {
    renderPage();
    expect(screen.getByText(/I am very unhappy with the service provided/)).toBeInTheDocument();
  });

  it("LLM Configuration section is collapsed by default (config fields not visible)", () => {
    renderPage();
    // LLM config fields only visible when expanded
    expect(screen.queryByText("gpt-4o-mini")).not.toBeInTheDocument();
  });

  it("clicking Show on LLM Configuration expands the section", async () => {
    const user = userEvent.setup();
    renderPage();

    const showButton = screen.getByRole("button", { name: /^show$/i });
    expect(showButton).toHaveAttribute("aria-expanded", "false");

    await user.click(showButton);

    expect(screen.getByText("gpt-4o-mini")).toBeInTheDocument();
    expect(showButton).toHaveAttribute("aria-expanded", "true");
  });

  it("clicking Hide after Show collapses the LLM section again", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /^show$/i }));
    expect(screen.getByText("gpt-4o-mini")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^hide$/i }));
    expect(screen.queryByText("gpt-4o-mini")).not.toBeInTheDocument();
  });

  it("shows loading state for action categories", () => {
    mockUseActionCategories.mockReturnValue({
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
    // Loading state renders Skeleton components (data-slot="skeleton")
    const skeletons = document.querySelectorAll('[data-slot="skeleton"]');
    expect(skeletons.length).toBeGreaterThanOrEqual(1);
  });

  it("shows loading state for type categories", () => {
    mockUseTypeCategories.mockReturnValue({
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
    const skeletons = document.querySelectorAll('[data-slot="skeleton"]');
    expect(skeletons.length).toBeGreaterThanOrEqual(1);
  });

  it("shows error alert when action categories fail to load", () => {
    mockUseActionCategories.mockReturnValue({
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
    expect(screen.getByText(/failed to load categories/i)).toBeInTheDocument();
  });

  it("renders Add Category button for action categories", () => {
    renderPage();
    // Two "Add Category" buttons — one per section
    const addButtons = screen.getAllByRole("button", { name: /add category/i });
    expect(addButtons.length).toBeGreaterThanOrEqual(1);
  });

  it("renders Add Example button for few-shot section", () => {
    renderPage();
    expect(screen.getByRole("button", { name: /add example/i })).toBeInTheDocument();
  });

  it("shows empty state message when no few-shot examples exist", () => {
    mockUseFewShotExamples.mockReturnValue({
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
    expect(screen.getByText(/no examples yet/i)).toBeInTheDocument();
  });

  it("read-only note is visible in LLM configuration section", () => {
    renderPage();
    expect(screen.getByText(/read-only/i)).toBeInTheDocument();
    expect(screen.getByText(/environment variables/i)).toBeInTheDocument();
  });
});
