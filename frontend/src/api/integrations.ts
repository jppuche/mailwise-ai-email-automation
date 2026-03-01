// src/api/integrations.ts
// Typed API functions for email, channel, and CRM integration config + test.
// LLM integration is already in api/categories.ts — NOT duplicated here (tighten-types D4).
// All config endpoints are READ-ONLY — no PUT/PATCH exists (config from env vars).
// Types from generated schema (tighten-types D4).
import apiClient from "./client";
import type {
  EmailIntegrationConfig,
  ChannelIntegrationConfig,
  CRMIntegrationConfig,
  ConnectionTestResult,
} from "@/types/generated/api";

// ----------------------------------------------------------------
// Email integration  (/integrations/email)
// ----------------------------------------------------------------

/**
 * GET /integrations/email — read-only Gmail integration config (admin only).
 * Never exposes credentials — returns boolean flags instead.
 */
export async function fetchEmailConfig(): Promise<EmailIntegrationConfig> {
  const { data } = await apiClient.get<EmailIntegrationConfig>("/integrations/email");
  return data;
}

/**
 * POST /integrations/email/test — test Gmail connectivity (admin only).
 * Always returns HTTP 200 — check result.success for actual outcome.
 */
export async function testEmailConnection(): Promise<ConnectionTestResult> {
  const { data } = await apiClient.post<ConnectionTestResult>("/integrations/email/test");
  return data;
}

// ----------------------------------------------------------------
// Channel integration  (/integrations/channels)
// ----------------------------------------------------------------

/**
 * GET /integrations/channels — read-only Slack integration config (admin only).
 * Never exposes credentials — returns boolean flags instead.
 */
export async function fetchChannelConfig(): Promise<ChannelIntegrationConfig> {
  const { data } = await apiClient.get<ChannelIntegrationConfig>("/integrations/channels");
  return data;
}

/**
 * POST /integrations/channels/test — test Slack connectivity (admin only).
 * Always returns HTTP 200 — check result.success for actual outcome.
 */
export async function testChannelConnection(): Promise<ConnectionTestResult> {
  const { data } = await apiClient.post<ConnectionTestResult>("/integrations/channels/test");
  return data;
}

// ----------------------------------------------------------------
// CRM integration  (/integrations/crm)
// ----------------------------------------------------------------

/**
 * GET /integrations/crm — read-only HubSpot CRM integration config (admin only).
 * Never exposes credentials — returns boolean flags instead.
 */
export async function fetchCrmConfig(): Promise<CRMIntegrationConfig> {
  const { data } = await apiClient.get<CRMIntegrationConfig>("/integrations/crm");
  return data;
}

/**
 * POST /integrations/crm/test — test HubSpot CRM connectivity (admin only).
 * Always returns HTTP 200 — check result.success for actual outcome.
 */
export async function testCrmConnection(): Promise<ConnectionTestResult> {
  const { data } = await apiClient.post<ConnectionTestResult>("/integrations/crm/test");
  return data;
}
