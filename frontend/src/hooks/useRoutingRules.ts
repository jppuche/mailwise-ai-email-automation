// src/hooks/useRoutingRules.ts
// TanStack Query hooks for routing rule CRUD, reorder, toggle active, and dry-run test.
// All types imported from generated schema — no manual duplication (tighten-types D4).
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchRoutingRules,
  createRoutingRule,
  updateRoutingRule,
  deleteRoutingRule,
  reorderRoutingRules,
  testRoutingRules,
} from "@/api/routing-rules";
import type {
  RoutingRuleResponse,
  RoutingRuleCreate,
  RoutingRuleUpdate,
  RuleTestRequest,
  RuleTestResponse,
} from "@/types/generated/api";

// ─────────────────────────────────────────────────────────────────────────────
// Query hooks
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch all routing rules, sorted by priority ascending.
 *
 * Query key: ["routing-rules"]
 * Data: RoutingRuleResponse[] sorted by priority (lowest first = highest priority)
 */
export function useRoutingRules() {
  return useQuery<RoutingRuleResponse[]>({
    queryKey: ["routing-rules"],
    queryFn: async () => {
      const rules = await fetchRoutingRules();
      return [...rules].sort((a, b) => a.priority - b.priority);
    },
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Mutation hook
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Returns routing rule mutation functions for CRUD, reorder, toggle active, and test.
 *
 * - create: POST /routing-rules — creates a rule. Invalidates ["routing-rules"].
 * - update: PUT /routing-rules/{id} — partial update. Invalidates ["routing-rules"].
 * - remove: DELETE /routing-rules/{id} — hard delete. Invalidates ["routing-rules"].
 * - reorder: PUT /routing-rules/reorder — sends ordered_ids[]. Invalidates ["routing-rules"].
 * - toggleActive: convenience wrapper around update — sets { is_active }. Invalidates ["routing-rules"].
 * - test: POST /routing-rules/test — dry-run evaluation. No cache invalidation (read-only).
 */
export function useRoutingRuleMutations() {
  const queryClient = useQueryClient();

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["routing-rules"] });

  const create = useMutation<RoutingRuleResponse, Error, RoutingRuleCreate>({
    mutationFn: (body) => createRoutingRule(body),
    onSuccess: () => {
      void invalidate();
    },
  });

  const update = useMutation<
    RoutingRuleResponse,
    Error,
    { id: string; body: RoutingRuleUpdate }
  >({
    mutationFn: ({ id, body }) => updateRoutingRule(id, body),
    onSuccess: () => {
      void invalidate();
    },
  });

  const remove = useMutation<void, Error, string>({
    mutationFn: (id) => deleteRoutingRule(id),
    onSuccess: () => {
      void invalidate();
    },
  });

  const reorder = useMutation<RoutingRuleResponse[], Error, string[]>({
    mutationFn: (orderedIds) => reorderRoutingRules(orderedIds),
    onSuccess: () => {
      void invalidate();
    },
  });

  /**
   * Toggle a rule's is_active flag.
   * Convenience wrapper around the update mutation.
   */
  const toggleActive = useMutation<
    RoutingRuleResponse,
    Error,
    { id: string; isActive: boolean }
  >({
    mutationFn: ({ id, isActive }) => updateRoutingRule(id, { is_active: isActive }),
    onSuccess: () => {
      void invalidate();
    },
  });

  const test = useMutation<RuleTestResponse, Error, RuleTestRequest>({
    mutationFn: (body) => testRoutingRules(body),
    // No cache invalidation — dry-run is read-only
  });

  return { create, update, remove, reorder, toggleActive, test } as const;
}
