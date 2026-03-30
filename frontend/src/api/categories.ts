// src/api/categories.ts
// Typed API functions for categories, few-shot examples, and LLM integration
// Types from generated schema
import apiClient from "./client";
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

// ----------------------------------------------------------------
// Action categories  (/categories/actions)
// ----------------------------------------------------------------

/**
 * GET /categories/actions — list all action categories ordered by display_order.
 */
export async function fetchActionCategories(): Promise<ActionCategoryResponse[]> {
  const { data } = await apiClient.get<ActionCategoryResponse[]>("/categories/actions");
  return data;
}

/**
 * POST /categories/actions — create a new action category (admin only).
 * Returns HTTP 201 Created.
 */
export async function createActionCategory(
  body: ActionCategoryCreate,
): Promise<ActionCategoryResponse> {
  const { data } = await apiClient.post<ActionCategoryResponse>("/categories/actions", body);
  return data;
}

/**
 * PUT /categories/actions/{id} — update an action category (admin only).
 * Slug is immutable — do not include in body.
 */
export async function updateActionCategory(
  id: string,
  body: ActionCategoryUpdate,
): Promise<ActionCategoryResponse> {
  const { data } = await apiClient.put<ActionCategoryResponse>(
    `/categories/actions/${id}`,
    body,
  );
  return data;
}

/**
 * DELETE /categories/actions/{id} — delete an action category (admin only).
 * Returns HTTP 204 No Content.
 * Throws ApiError with status 409 if the category is referenced by existing emails.
 */
export async function deleteActionCategory(id: string): Promise<void> {
  await apiClient.delete(`/categories/actions/${id}`);
}

/**
 * PUT /categories/actions/reorder — reorder action categories by providing full ordered ID list.
 * ordered_ids[0] → display_order 1.
 */
export async function reorderActionCategories(
  body: ReorderRequest,
): Promise<ActionCategoryResponse[]> {
  const { data } = await apiClient.put<ActionCategoryResponse[]>(
    "/categories/actions/reorder",
    body,
  );
  return data;
}

// ----------------------------------------------------------------
// Type categories  (/categories/types)
// ----------------------------------------------------------------

/**
 * GET /categories/types — list all type categories ordered by display_order.
 */
export async function fetchTypeCategories(): Promise<TypeCategoryResponse[]> {
  const { data } = await apiClient.get<TypeCategoryResponse[]>("/categories/types");
  return data;
}

/**
 * POST /categories/types — create a new type category (admin only).
 * Returns HTTP 201 Created.
 */
export async function createTypeCategory(
  body: TypeCategoryCreate,
): Promise<TypeCategoryResponse> {
  const { data } = await apiClient.post<TypeCategoryResponse>("/categories/types", body);
  return data;
}

/**
 * PUT /categories/types/{id} — update a type category (admin only).
 * Slug is immutable — do not include in body.
 */
export async function updateTypeCategory(
  id: string,
  body: TypeCategoryUpdate,
): Promise<TypeCategoryResponse> {
  const { data } = await apiClient.put<TypeCategoryResponse>(
    `/categories/types/${id}`,
    body,
  );
  return data;
}

/**
 * DELETE /categories/types/{id} — delete a type category (admin only).
 * Returns HTTP 204 No Content.
 * Throws ApiError with status 409 if the category is referenced by existing emails.
 */
export async function deleteTypeCategory(id: string): Promise<void> {
  await apiClient.delete(`/categories/types/${id}`);
}

/**
 * PUT /categories/types/reorder — reorder type categories by providing full ordered ID list.
 * ordered_ids[0] → display_order 1.
 */
export async function reorderTypeCategories(
  body: ReorderRequest,
): Promise<TypeCategoryResponse[]> {
  const { data } = await apiClient.put<TypeCategoryResponse[]>(
    "/categories/types/reorder",
    body,
  );
  return data;
}

// ----------------------------------------------------------------
// Few-shot examples  (/classification/examples)
// ----------------------------------------------------------------

/**
 * GET /classification/examples — list all few-shot examples.
 */
export async function fetchFewShotExamples(): Promise<FewShotExampleResponse[]> {
  const { data } = await apiClient.get<FewShotExampleResponse[]>("/classification/examples");
  return data;
}

/**
 * POST /classification/examples — create a new few-shot example (admin only).
 * Returns HTTP 201 Created.
 */
export async function createFewShotExample(
  body: FewShotExampleCreate,
): Promise<FewShotExampleResponse> {
  const { data } = await apiClient.post<FewShotExampleResponse>(
    "/classification/examples",
    body,
  );
  return data;
}

/**
 * PUT /classification/examples/{id} — update a few-shot example (admin only).
 */
export async function updateFewShotExample(
  id: string,
  body: FewShotExampleUpdate,
): Promise<FewShotExampleResponse> {
  const { data } = await apiClient.put<FewShotExampleResponse>(
    `/classification/examples/${id}`,
    body,
  );
  return data;
}

/**
 * DELETE /classification/examples/{id} — delete a few-shot example (admin only).
 * Returns HTTP 204 No Content.
 */
export async function deleteFewShotExample(id: string): Promise<void> {
  await apiClient.delete(`/classification/examples/${id}`);
}

// ----------------------------------------------------------------
// LLM integration config  (/integrations/llm)
// ----------------------------------------------------------------

/**
 * GET /integrations/llm — read-only LLM configuration from environment (admin only).
 * Never exposes API keys — returns *_configured booleans instead.
 */
export async function fetchLLMConfig(): Promise<LLMIntegrationConfig> {
  const { data } = await apiClient.get<LLMIntegrationConfig>("/integrations/llm");
  return data;
}

/**
 * POST /integrations/llm/test — test LLM connection (admin only).
 * Always returns HTTP 200 — success=false is a valid result (not a network error).
 */
export async function testLLMConnection(): Promise<LLMTestResult> {
  const { data } = await apiClient.post<LLMTestResult>("/integrations/llm/test");
  return data;
}
