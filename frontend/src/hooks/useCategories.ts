// src/hooks/useCategories.ts
// TanStack Query hooks for action/type categories, few-shot examples, and LLM integration.
// All types imported from generated schema — no manual duplication (tighten-types D4).
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchActionCategories,
  createActionCategory,
  updateActionCategory,
  deleteActionCategory,
  reorderActionCategories,
  fetchTypeCategories,
  createTypeCategory,
  updateTypeCategory,
  deleteTypeCategory,
  reorderTypeCategories,
  fetchFewShotExamples,
  createFewShotExample,
  updateFewShotExample,
  deleteFewShotExample,
  fetchLLMConfig,
  testLLMConnection,
} from "@/api/categories";
import type {
  ActionCategoryResponse,
  ActionCategoryCreate,
  ActionCategoryUpdate,
  TypeCategoryResponse,
  TypeCategoryCreate,
  TypeCategoryUpdate,
  ReorderRequest,
  FewShotExampleResponse,
  FewShotExampleCreate,
  FewShotExampleUpdate,
  LLMIntegrationConfig,
  LLMTestResult,
} from "@/types/generated/api";

// ─────────────────────────────────────────────────────────────────────────────
// Category layer type
// ─────────────────────────────────────────────────────────────────────────────

/** Discriminates between action and type category tables — no layer field on the model (delta #11). */
export type CategoryLayer = "actions" | "types";

// ─────────────────────────────────────────────────────────────────────────────
// Action categories
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch all action categories ordered by display_order.
 *
 * Query key: ["categories", "actions"]
 */
export function useActionCategories() {
  return useQuery<ActionCategoryResponse[]>({
    queryKey: ["categories", "actions"],
    queryFn: fetchActionCategories,
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Type categories
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch all type categories ordered by display_order.
 *
 * Query key: ["categories", "types"]
 */
export function useTypeCategories() {
  return useQuery<TypeCategoryResponse[]>({
    queryKey: ["categories", "types"],
    queryFn: fetchTypeCategories,
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Category mutations (layer-parameterised)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Shared response shape — ActionCategoryResponse and TypeCategoryResponse are structurally
 * identical; this union lets the layer-parameterised hook return a single type.
 */
type AnyCategoryResponse = ActionCategoryResponse | TypeCategoryResponse;

/**
 * Shared create body — both create schemas have the same required/optional fields.
 */
type AnyCategoryCreate = ActionCategoryCreate | TypeCategoryCreate;

/**
 * Shared update body — both update schemas have the same optional fields.
 */
type AnyCategoryUpdate = ActionCategoryUpdate | TypeCategoryUpdate;

/**
 * Returns CRUD + reorder mutations for the given category layer.
 * All mutations invalidate ["categories", layer] on success.
 *
 * Hooks are always called unconditionally (Rules of Hooks).
 * The `layer` parameter selects which API function each mutationFn calls at runtime.
 *
 * Usage:
 *   const { create, update, remove, reorder } = useCategoryMutations("actions");
 *   const { create, update, remove, reorder } = useCategoryMutations("types");
 *
 * pre-mortem Cat 3: slugs are DB-backed enum values — the CategoryList UI must
 * load options from this hook, not from a hardcoded array.
 */
export function useCategoryMutations(layer: CategoryLayer) {
  const queryClient = useQueryClient();

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["categories", layer] });

  const create = useMutation<AnyCategoryResponse, Error, AnyCategoryCreate>({
    mutationFn: (body) =>
      layer === "actions"
        ? createActionCategory(body as ActionCategoryCreate)
        : createTypeCategory(body as TypeCategoryCreate),
    onSuccess: () => {
      void invalidate();
    },
  });

  const update = useMutation<
    AnyCategoryResponse,
    Error,
    { id: string; body: AnyCategoryUpdate }
  >({
    mutationFn: ({ id, body }) =>
      layer === "actions"
        ? updateActionCategory(id, body as ActionCategoryUpdate)
        : updateTypeCategory(id, body as TypeCategoryUpdate),
    onSuccess: () => {
      void invalidate();
    },
  });

  const remove = useMutation<void, Error, string>({
    mutationFn: (id) =>
      layer === "actions" ? deleteActionCategory(id) : deleteTypeCategory(id),
    onSuccess: () => {
      void invalidate();
    },
  });

  const reorder = useMutation<AnyCategoryResponse[], Error, ReorderRequest>({
    mutationFn: (body) =>
      layer === "actions" ? reorderActionCategories(body) : reorderTypeCategories(body),
    onSuccess: () => {
      void invalidate();
    },
  });

  return { create, update, remove, reorder } as const;
}

// ─────────────────────────────────────────────────────────────────────────────
// Few-shot examples
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch all few-shot classification examples.
 *
 * Query key: ["classification", "examples"]
 */
export function useFewShotExamples() {
  return useQuery<FewShotExampleResponse[]>({
    queryKey: ["classification", "examples"],
    queryFn: fetchFewShotExamples,
  });
}

/**
 * Returns create, update, and delete mutations for few-shot examples.
 * All mutations invalidate ["classification", "examples"] on success.
 */
export function useFewShotMutations() {
  const queryClient = useQueryClient();

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["classification", "examples"] });

  const create = useMutation<FewShotExampleResponse, Error, FewShotExampleCreate>({
    mutationFn: (body) => createFewShotExample(body),
    onSuccess: () => {
      void invalidate();
    },
  });

  const update = useMutation<
    FewShotExampleResponse,
    Error,
    { id: string; body: FewShotExampleUpdate }
  >({
    mutationFn: ({ id, body }) => updateFewShotExample(id, body),
    onSuccess: () => {
      void invalidate();
    },
  });

  const remove = useMutation<void, Error, string>({
    mutationFn: (id) => deleteFewShotExample(id),
    onSuccess: () => {
      void invalidate();
    },
  });

  return { create, update, remove } as const;
}

// ─────────────────────────────────────────────────────────────────────────────
// LLM integration (read-only config + connection test)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch LLM integration configuration (admin only, read-only).
 * No PUT endpoint exists — config comes from environment variables.
 *
 * Query key: ["integrations", "llm"]
 */
export function useLLMConfig() {
  return useQuery<LLMIntegrationConfig>({
    queryKey: ["integrations", "llm"],
    queryFn: fetchLLMConfig,
  });
}

/**
 * Test the LLM connection and return latency/status.
 * HTTP 200 regardless of success — check result.success.
 */
export function useTestLLM() {
  return useMutation<LLMTestResult, Error, void>({
    mutationFn: () => testLLMConnection(),
  });
}
