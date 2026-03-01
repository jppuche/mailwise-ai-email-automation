// src/api/routing-rules.ts
// Typed API functions for routing rules CRUD + reorder + test.
// Types from generated schema (tighten-types D4).
import apiClient from "./client";
import type {
  RoutingRuleResponse,
  RoutingRuleCreate,
  RoutingRuleUpdate,
  RuleTestRequest,
  RuleTestResponse,
} from "@/types/generated/api";

/**
 * GET /routing-rules — list all routing rules.
 * Auth: Admin only.
 */
export async function fetchRoutingRules(): Promise<RoutingRuleResponse[]> {
  const { data } = await apiClient.get<RoutingRuleResponse[]>("/routing-rules");
  return data;
}

/**
 * GET /routing-rules/{id} — fetch a single routing rule by ID.
 * Auth: Admin only.
 */
export async function fetchRoutingRule(id: string): Promise<RoutingRuleResponse> {
  const { data } = await apiClient.get<RoutingRuleResponse>(`/routing-rules/${id}`);
  return data;
}

/**
 * POST /routing-rules — create a new routing rule.
 * Returns HTTP 201 Created.
 * Auth: Admin only.
 */
export async function createRoutingRule(body: RoutingRuleCreate): Promise<RoutingRuleResponse> {
  const { data } = await apiClient.post<RoutingRuleResponse>("/routing-rules", body);
  return data;
}

/**
 * PUT /routing-rules/{id} — update a routing rule (all fields optional).
 * Auth: Admin only.
 */
export async function updateRoutingRule(
  id: string,
  body: RoutingRuleUpdate,
): Promise<RoutingRuleResponse> {
  const { data } = await apiClient.put<RoutingRuleResponse>(`/routing-rules/${id}`, body);
  return data;
}

/**
 * DELETE /routing-rules/{id} — delete a routing rule.
 * Returns HTTP 204 No Content.
 * Auth: Admin only.
 */
export async function deleteRoutingRule(id: string): Promise<void> {
  await apiClient.delete(`/routing-rules/${id}`);
}

/**
 * PUT /routing-rules/reorder — reorder rules by providing full ordered ID list.
 * ordered_ids[0] → priority 1, ordered_ids[1] → priority 2, etc.
 * Note: literal path /reorder is registered BEFORE /{rule_id} in the backend router.
 * Auth: Admin only.
 */
export async function reorderRoutingRules(orderedIds: string[]): Promise<RoutingRuleResponse[]> {
  const { data } = await apiClient.put<RoutingRuleResponse[]>("/routing-rules/reorder", {
    ordered_ids: orderedIds,
  });
  return data;
}

/**
 * POST /routing-rules/test — dry-run rule evaluation against a synthetic email context.
 * Note: literal path /test is registered BEFORE /{rule_id} in the backend router.
 * Auth: Admin only.
 */
export async function testRoutingRules(body: RuleTestRequest): Promise<RuleTestResponse> {
  const { data } = await apiClient.post<RuleTestResponse>("/routing-rules/test", body);
  return data;
}
