// src/hooks/__tests__/useCategories.test.ts
// Tests for useActionCategories, useCategoryMutations, useFewShotExamples,
// and useFewShotMutations hooks.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type {
  ActionCategoryResponse,
  TypeCategoryResponse,
  FewShotExampleResponse,
  ReorderRequest,
} from "@/types/generated/api";

// ─────────────────────────────────────────────────────────────────────────────
// API module mock — must precede hook imports
// ─────────────────────────────────────────────────────────────────────────────

vi.mock("@/api/categories", () => ({
  fetchActionCategories: vi.fn(),
  createActionCategory: vi.fn(),
  updateActionCategory: vi.fn(),
  deleteActionCategory: vi.fn(),
  reorderActionCategories: vi.fn(),
  fetchTypeCategories: vi.fn(),
  createTypeCategory: vi.fn(),
  updateTypeCategory: vi.fn(),
  deleteTypeCategory: vi.fn(),
  reorderTypeCategories: vi.fn(),
  fetchFewShotExamples: vi.fn(),
  createFewShotExample: vi.fn(),
  updateFewShotExample: vi.fn(),
  deleteFewShotExample: vi.fn(),
  fetchLLMConfig: vi.fn(),
  testLLMConnection: vi.fn(),
}));

import {
  fetchActionCategories,
  createActionCategory,
  createTypeCategory,
  reorderActionCategories,
  reorderTypeCategories,
  createFewShotExample,
} from "@/api/categories";
import {
  useActionCategories,
  useCategoryMutations,
  useFewShotExamples,
  useFewShotMutations,
} from "../useCategories";

const mockFetchActionCategories = vi.mocked(fetchActionCategories);
const mockCreateActionCategory = vi.mocked(createActionCategory);
const mockCreateTypeCategory = vi.mocked(createTypeCategory);
const mockReorderActionCategories = vi.mocked(reorderActionCategories);
const mockReorderTypeCategories = vi.mocked(reorderTypeCategories);
const mockCreateFewShotExample = vi.mocked(createFewShotExample);

// ─────────────────────────────────────────────────────────────────────────────
// Wrapper factory — fresh QueryClient per test
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

function makeActionCategory(overrides: Partial<ActionCategoryResponse> = {}): ActionCategoryResponse {
  return {
    id: "cat-action-1",
    slug: "respond",
    name: "Respond",
    description: "Respond to the email",
    is_fallback: false,
    is_active: true,
    display_order: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeTypeCategory(overrides: Partial<TypeCategoryResponse> = {}): TypeCategoryResponse {
  return {
    id: "cat-type-1",
    slug: "inquiry",
    name: "Inquiry",
    description: "Customer inquiry",
    is_fallback: false,
    is_active: true,
    display_order: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeFewShotExample(overrides: Partial<FewShotExampleResponse> = {}): FewShotExampleResponse {
  return {
    id: "example-1",
    email_snippet: "I need help with my order",
    action_slug: "respond",
    type_slug: "inquiry",
    rationale: null,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// useActionCategories
// ─────────────────────────────────────────────────────────────────────────────

describe("useActionCategories", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns data from fetchActionCategories", async () => {
    const categories = [makeActionCategory({ id: "cat-1" }), makeActionCategory({ id: "cat-2" })];
    mockFetchActionCategories.mockResolvedValueOnce(categories);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useActionCategories(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.data).toEqual(categories);
    expect(result.current.data).toHaveLength(2);
  });

  it("returns isLoading true before data resolves", () => {
    mockFetchActionCategories.mockReturnValue(new Promise(() => {}));

    const wrapper = createWrapper();
    const { result } = renderHook(() => useActionCategories(), { wrapper });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.data).toBeUndefined();
  });

  it("calls fetchActionCategories once on mount", async () => {
    mockFetchActionCategories.mockResolvedValueOnce([]);

    const wrapper = createWrapper();
    renderHook(() => useActionCategories(), { wrapper });

    await waitFor(() => {
      expect(mockFetchActionCategories).toHaveBeenCalledOnce();
    });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// useCategoryMutations — actions layer
// ─────────────────────────────────────────────────────────────────────────────

describe("useCategoryMutations('actions')", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("create.mutate calls createActionCategory (not createTypeCategory)", async () => {
    const created = makeActionCategory({ id: "new-cat" });
    mockCreateActionCategory.mockResolvedValueOnce(created);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useCategoryMutations("actions"), { wrapper });

    result.current.create.mutate({ name: "New Action", slug: "new-action" });

    await waitFor(() => {
      expect(result.current.create.isSuccess).toBe(true);
    });

    expect(mockCreateActionCategory).toHaveBeenCalledWith({ name: "New Action", slug: "new-action" });
    expect(mockCreateTypeCategory).not.toHaveBeenCalled();
  });

  it("reorder.mutate calls reorderActionCategories with the ordered IDs", async () => {
    const reordered = [makeActionCategory({ id: "cat-2" }), makeActionCategory({ id: "cat-1" })];
    mockReorderActionCategories.mockResolvedValueOnce(reordered);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useCategoryMutations("actions"), { wrapper });

    const reorderPayload: ReorderRequest = { ordered_ids: ["cat-2", "cat-1"] };
    result.current.reorder.mutate(reorderPayload);

    await waitFor(() => {
      expect(result.current.reorder.isSuccess).toBe(true);
    });

    expect(mockReorderActionCategories).toHaveBeenCalledWith(reorderPayload);
    expect(mockReorderTypeCategories).not.toHaveBeenCalled();
  });

  it("update.mutate calls updateActionCategory with id and body", async () => {
    const { updateActionCategory: mockUpdateActionCategory } = await import("@/api/categories");
    vi.mocked(mockUpdateActionCategory).mockResolvedValueOnce(makeActionCategory({ name: "Updated" }));

    const wrapper = createWrapper();
    const { result } = renderHook(() => useCategoryMutations("actions"), { wrapper });

    result.current.update.mutate({ id: "cat-1", body: { name: "Updated" } });

    await waitFor(() => {
      expect(result.current.update.isSuccess).toBe(true);
    });

    expect(vi.mocked(mockUpdateActionCategory)).toHaveBeenCalledWith("cat-1", { name: "Updated" });
  });

  it("remove.mutate calls deleteActionCategory with the category id", async () => {
    const { deleteActionCategory: mockDeleteActionCategory } = await import("@/api/categories");
    vi.mocked(mockDeleteActionCategory).mockResolvedValueOnce(undefined);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useCategoryMutations("actions"), { wrapper });

    result.current.remove.mutate("cat-1");

    await waitFor(() => {
      expect(result.current.remove.isSuccess).toBe(true);
    });

    expect(vi.mocked(mockDeleteActionCategory)).toHaveBeenCalledWith("cat-1");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// useCategoryMutations — types layer
// ─────────────────────────────────────────────────────────────────────────────

describe("useCategoryMutations('types')", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("create.mutate calls createTypeCategory (not createActionCategory)", async () => {
    const created = makeTypeCategory({ id: "new-type" });
    mockCreateTypeCategory.mockResolvedValueOnce(created);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useCategoryMutations("types"), { wrapper });

    result.current.create.mutate({ name: "New Type", slug: "new-type" });

    await waitFor(() => {
      expect(result.current.create.isSuccess).toBe(true);
    });

    expect(mockCreateTypeCategory).toHaveBeenCalledWith({ name: "New Type", slug: "new-type" });
    expect(mockCreateActionCategory).not.toHaveBeenCalled();
  });

  it("reorder.mutate calls reorderTypeCategories with the ordered IDs", async () => {
    const reordered = [makeTypeCategory({ id: "type-2" }), makeTypeCategory({ id: "type-1" })];
    mockReorderTypeCategories.mockResolvedValueOnce(reordered);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useCategoryMutations("types"), { wrapper });

    const reorderPayload: ReorderRequest = { ordered_ids: ["type-2", "type-1"] };
    result.current.reorder.mutate(reorderPayload);

    await waitFor(() => {
      expect(result.current.reorder.isSuccess).toBe(true);
    });

    expect(mockReorderTypeCategories).toHaveBeenCalledWith(reorderPayload);
    expect(mockReorderActionCategories).not.toHaveBeenCalled();
  });

  it("update.mutate calls updateTypeCategory with id and body", async () => {
    const { updateTypeCategory: mockUpdateTypeCategory } = await import("@/api/categories");
    vi.mocked(mockUpdateTypeCategory).mockResolvedValueOnce(makeTypeCategory({ name: "Updated Type" }));

    const wrapper = createWrapper();
    const { result } = renderHook(() => useCategoryMutations("types"), { wrapper });

    result.current.update.mutate({ id: "type-1", body: { name: "Updated Type" } });

    await waitFor(() => {
      expect(result.current.update.isSuccess).toBe(true);
    });

    expect(vi.mocked(mockUpdateTypeCategory)).toHaveBeenCalledWith("type-1", { name: "Updated Type" });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// useFewShotExamples
// ─────────────────────────────────────────────────────────────────────────────

describe("useFewShotExamples", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns data from fetchFewShotExamples", async () => {
    const { fetchFewShotExamples: mockFetchExamples } = await import("@/api/categories");
    const examples = [makeFewShotExample({ id: "ex-1" }), makeFewShotExample({ id: "ex-2" })];
    vi.mocked(mockFetchExamples).mockResolvedValueOnce(examples);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useFewShotExamples(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.data).toEqual(examples);
    expect(result.current.data).toHaveLength(2);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// useFewShotMutations
// ─────────────────────────────────────────────────────────────────────────────

describe("useFewShotMutations", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("create.mutate calls createFewShotExample with the body", async () => {
    const created = makeFewShotExample({ id: "new-example" });
    mockCreateFewShotExample.mockResolvedValueOnce(created);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useFewShotMutations(), { wrapper });

    result.current.create.mutate({
      email_snippet: "I need help with my order",
      action_slug: "respond",
      type_slug: "inquiry",
    });

    await waitFor(() => {
      expect(result.current.create.isSuccess).toBe(true);
    });

    expect(mockCreateFewShotExample).toHaveBeenCalledWith({
      email_snippet: "I need help with my order",
      action_slug: "respond",
      type_slug: "inquiry",
    });
  });

  it("update.mutate calls updateFewShotExample with id and body", async () => {
    const { updateFewShotExample: mockUpdateExample } = await import("@/api/categories");
    vi.mocked(mockUpdateExample).mockResolvedValueOnce(makeFewShotExample({ rationale: "Updated" }));

    const wrapper = createWrapper();
    const { result } = renderHook(() => useFewShotMutations(), { wrapper });

    result.current.update.mutate({ id: "ex-1", body: { rationale: "Updated" } });

    await waitFor(() => {
      expect(result.current.update.isSuccess).toBe(true);
    });

    expect(vi.mocked(mockUpdateExample)).toHaveBeenCalledWith("ex-1", { rationale: "Updated" });
  });

  it("remove.mutate calls deleteFewShotExample with the example id", async () => {
    const { deleteFewShotExample: mockDeleteExample } = await import("@/api/categories");
    vi.mocked(mockDeleteExample).mockResolvedValueOnce(undefined);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useFewShotMutations(), { wrapper });

    result.current.remove.mutate("ex-1");

    await waitFor(() => {
      expect(result.current.remove.isSuccess).toBe(true);
    });

    expect(vi.mocked(mockDeleteExample)).toHaveBeenCalledWith("ex-1");
  });

  it("create.mutate includes optional rationale when provided", async () => {
    const created = makeFewShotExample({ rationale: "This is a clear inquiry" });
    mockCreateFewShotExample.mockResolvedValueOnce(created);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useFewShotMutations(), { wrapper });

    result.current.create.mutate({
      email_snippet: "What is your return policy?",
      action_slug: "respond",
      type_slug: "policy",
      rationale: "This is a clear inquiry",
    });

    await waitFor(() => {
      expect(result.current.create.isSuccess).toBe(true);
    });

    expect(mockCreateFewShotExample).toHaveBeenCalledWith(
      expect.objectContaining({ rationale: "This is a clear inquiry" }),
    );
  });
});
