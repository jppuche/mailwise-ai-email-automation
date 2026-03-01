// src/hooks/useIntegrations.ts
// TanStack Query hooks for integration config queries and connection test mutations.
// LLM integration is handled by useCategories.ts — NOT duplicated here.
// All types imported from generated schema — no manual duplication (tighten-types D4).
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  fetchEmailConfig,
  testEmailConnection,
  fetchChannelConfig,
  testChannelConnection,
  fetchCrmConfig,
  testCrmConnection,
} from "@/api/integrations";
import { testLLMConnection } from "@/api/categories";
import type {
  EmailIntegrationConfig,
  ChannelIntegrationConfig,
  CRMIntegrationConfig,
  ConnectionTestResult,
} from "@/types/generated/api";

// ─────────────────────────────────────────────────────────────────────────────
// Query hooks
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch email (Gmail) integration config — read-only.
 *
 * Query key: ["integrations", "email"]
 */
export function useEmailIntegration() {
  return useQuery<EmailIntegrationConfig>({
    queryKey: ["integrations", "email"],
    queryFn: fetchEmailConfig,
  });
}

/**
 * Fetch channel (Slack) integration config — read-only.
 *
 * Query key: ["integrations", "channels"]
 */
export function useChannelIntegration() {
  return useQuery<ChannelIntegrationConfig>({
    queryKey: ["integrations", "channels"],
    queryFn: fetchChannelConfig,
  });
}

/**
 * Fetch CRM (HubSpot) integration config — read-only.
 *
 * Query key: ["integrations", "crm"]
 */
export function useCrmIntegration() {
  return useQuery<CRMIntegrationConfig>({
    queryKey: ["integrations", "crm"],
    queryFn: fetchCrmConfig,
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Connection test mutation
// ─────────────────────────────────────────────────────────────────────────────

/** Integration types supported by the test connection mutation. */
export type IntegrationType = "email" | "channels" | "crm" | "llm";

/**
 * Returns a mutation that tests connectivity for any integration type.
 * HTTP 200 always — check result.success for actual connectivity status.
 *
 * Usage:
 *   const testConn = useTestConnection();
 *   testConn.mutate("email");
 *   testConn.mutate("llm");
 */
export function useTestConnection() {
  return useMutation<ConnectionTestResult, Error, IntegrationType>({
    mutationFn: (type) => {
      if (type === "email") return testEmailConnection();
      if (type === "channels") return testChannelConnection();
      if (type === "crm") return testCrmConnection();
      return testLLMConnection();
    },
  });
}
