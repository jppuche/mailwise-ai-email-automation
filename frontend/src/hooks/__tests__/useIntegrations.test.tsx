// src/hooks/__tests__/useIntegrations.test.tsx
// Tests for useEmailIntegration, useChannelIntegration, useCrmIntegration,
// and useTestConnection hooks.
// Mocks @/api/integrations and @/api/categories (for testLLMConnection).
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type {
  EmailIntegrationConfig,
  ChannelIntegrationConfig,
  CRMIntegrationConfig,
  ConnectionTestResult,
} from "@/types/generated/api";

// ─────────────────────────────────────────────────────────────────────────────
// API module mocks — must precede hook imports
// ─────────────────────────────────────────────────────────────────────────────

vi.mock("@/api/integrations", () => ({
  fetchEmailConfig: vi.fn(),
  testEmailConnection: vi.fn(),
  fetchChannelConfig: vi.fn(),
  testChannelConnection: vi.fn(),
  fetchCrmConfig: vi.fn(),
  testCrmConnection: vi.fn(),
}));

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
  fetchEmailConfig,
  testEmailConnection,
  fetchChannelConfig,
  testChannelConnection,
  fetchCrmConfig,
  testCrmConnection,
} from "@/api/integrations";
import { testLLMConnection } from "@/api/categories";
import {
  useEmailIntegration,
  useChannelIntegration,
  useCrmIntegration,
  useTestConnection,
} from "../useIntegrations";

const mockFetchEmailConfig = vi.mocked(fetchEmailConfig);
const mockTestEmailConnection = vi.mocked(testEmailConnection);
const mockFetchChannelConfig = vi.mocked(fetchChannelConfig);
const mockTestChannelConnection = vi.mocked(testChannelConnection);
const mockFetchCrmConfig = vi.mocked(fetchCrmConfig);
const mockTestCrmConnection = vi.mocked(testCrmConnection);
const mockTestLLMConnection = vi.mocked(testLLMConnection);

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

function makeEmailConfig(overrides: Partial<EmailIntegrationConfig> = {}): EmailIntegrationConfig {
  return {
    oauth_configured: true,
    credentials_file: "credentials.json",
    token_file: "token.json",
    poll_interval_seconds: 300,
    max_results: 50,
    ...overrides,
  };
}

function makeChannelConfig(overrides: Partial<ChannelIntegrationConfig> = {}): ChannelIntegrationConfig {
  return {
    bot_token_configured: true,
    signing_secret_configured: false,
    default_channel: "#general",
    snippet_length: 200,
    timeout_seconds: 30,
    ...overrides,
  };
}

function makeCrmConfig(overrides: Partial<CRMIntegrationConfig> = {}): CRMIntegrationConfig {
  return {
    access_token_configured: true,
    auto_create_contacts: true,
    default_lead_status: "New",
    rate_limit_per_10s: 9,
    api_timeout_seconds: 10,
    ...overrides,
  };
}

function makeConnectionTestResult(overrides: Partial<ConnectionTestResult> = {}): ConnectionTestResult {
  return {
    success: true,
    latency_ms: 42,
    error_detail: null,
    adapter_type: "gmail",
    ...overrides,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// useEmailIntegration
// ─────────────────────────────────────────────────────────────────────────────

describe("useEmailIntegration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls fetchEmailConfig once on mount", async () => {
    mockFetchEmailConfig.mockResolvedValueOnce(makeEmailConfig());

    const wrapper = createWrapper();
    renderHook(() => useEmailIntegration(), { wrapper });

    await waitFor(() => {
      expect(mockFetchEmailConfig).toHaveBeenCalledOnce();
    });
  });

  it("returns email config data after fetch resolves", async () => {
    const config = makeEmailConfig({ poll_interval_seconds: 600 });
    mockFetchEmailConfig.mockResolvedValueOnce(config);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useEmailIntegration(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.data).toEqual(config);
    expect(result.current.data?.poll_interval_seconds).toBe(600);
  });

  it("returns isLoading true before fetch resolves", () => {
    mockFetchEmailConfig.mockReturnValue(new Promise(() => {}));

    const wrapper = createWrapper();
    const { result } = renderHook(() => useEmailIntegration(), { wrapper });

    expect(result.current.isLoading).toBe(true);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// useChannelIntegration
// ─────────────────────────────────────────────────────────────────────────────

describe("useChannelIntegration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls fetchChannelConfig once on mount", async () => {
    mockFetchChannelConfig.mockResolvedValueOnce(makeChannelConfig());

    const wrapper = createWrapper();
    renderHook(() => useChannelIntegration(), { wrapper });

    await waitFor(() => {
      expect(mockFetchChannelConfig).toHaveBeenCalledOnce();
    });
  });

  it("returns channel config data after fetch resolves", async () => {
    const config = makeChannelConfig({ default_channel: "#ops-alerts" });
    mockFetchChannelConfig.mockResolvedValueOnce(config);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useChannelIntegration(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.data?.default_channel).toBe("#ops-alerts");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// useCrmIntegration
// ─────────────────────────────────────────────────────────────────────────────

describe("useCrmIntegration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls fetchCrmConfig once on mount", async () => {
    mockFetchCrmConfig.mockResolvedValueOnce(makeCrmConfig());

    const wrapper = createWrapper();
    renderHook(() => useCrmIntegration(), { wrapper });

    await waitFor(() => {
      expect(mockFetchCrmConfig).toHaveBeenCalledOnce();
    });
  });

  it("returns CRM config data after fetch resolves", async () => {
    const config = makeCrmConfig({ auto_create_contacts: false });
    mockFetchCrmConfig.mockResolvedValueOnce(config);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useCrmIntegration(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.data?.auto_create_contacts).toBe(false);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// useTestConnection
// ─────────────────────────────────────────────────────────────────────────────

describe("useTestConnection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls testEmailConnection when type is 'email'", async () => {
    const testResult = makeConnectionTestResult({ adapter_type: "gmail" });
    mockTestEmailConnection.mockResolvedValueOnce(testResult);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useTestConnection(), { wrapper });

    result.current.mutate("email");

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockTestEmailConnection).toHaveBeenCalledOnce();
    expect(mockTestChannelConnection).not.toHaveBeenCalled();
    expect(mockTestCrmConnection).not.toHaveBeenCalled();
    expect(mockTestLLMConnection).not.toHaveBeenCalled();
  });

  it("calls testChannelConnection when type is 'channels'", async () => {
    const testResult = makeConnectionTestResult({ adapter_type: "slack" });
    mockTestChannelConnection.mockResolvedValueOnce(testResult);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useTestConnection(), { wrapper });

    result.current.mutate("channels");

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockTestChannelConnection).toHaveBeenCalledOnce();
    expect(mockTestEmailConnection).not.toHaveBeenCalled();
    expect(mockTestCrmConnection).not.toHaveBeenCalled();
    expect(mockTestLLMConnection).not.toHaveBeenCalled();
  });

  it("calls testCrmConnection when type is 'crm'", async () => {
    const testResult = makeConnectionTestResult({ adapter_type: "hubspot" });
    mockTestCrmConnection.mockResolvedValueOnce(testResult);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useTestConnection(), { wrapper });

    result.current.mutate("crm");

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockTestCrmConnection).toHaveBeenCalledOnce();
    expect(mockTestEmailConnection).not.toHaveBeenCalled();
    expect(mockTestChannelConnection).not.toHaveBeenCalled();
    expect(mockTestLLMConnection).not.toHaveBeenCalled();
  });

  it("calls testLLMConnection when type is 'llm'", async () => {
    const testResult = makeConnectionTestResult({ adapter_type: "litellm" });
    mockTestLLMConnection.mockResolvedValueOnce(testResult);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useTestConnection(), { wrapper });

    result.current.mutate("llm");

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockTestLLMConnection).toHaveBeenCalledOnce();
    expect(mockTestEmailConnection).not.toHaveBeenCalled();
    expect(mockTestChannelConnection).not.toHaveBeenCalled();
    expect(mockTestCrmConnection).not.toHaveBeenCalled();
  });

  it("returns success false in result when connection fails (HTTP 200 but success: false)", async () => {
    const failedResult = makeConnectionTestResult({
      success: false,
      latency_ms: null,
      error_detail: "Authentication failed",
      adapter_type: "gmail",
    });
    mockTestEmailConnection.mockResolvedValueOnce(failedResult);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useTestConnection(), { wrapper });

    result.current.mutate("email");

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // Mutation succeeds at HTTP level — check result.success for actual outcome
    expect(result.current.data?.success).toBe(false);
    expect(result.current.data?.error_detail).toBe("Authentication failed");
  });
});
