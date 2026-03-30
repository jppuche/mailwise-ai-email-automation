// src/pages/IntegrationsPage.tsx
// Route: /integrations (admin only)
// 4 read-only integration panels with test connection buttons.
// No PUT/PATCH — all config from environment variables (handoff delta #2).
import { useState } from "react";
import {
  useEmailIntegration,
  useChannelIntegration,
  useCrmIntegration,
  useTestConnection,
  type IntegrationType,
} from "@/hooks/useIntegrations";
import { useLLMConfig } from "@/hooks/useCategories";
import { IntegrationPanel } from "@/components/IntegrationPanel";
import type { ConnectionTestResult } from "@/types/generated/api";

export default function IntegrationsPage() {
  const { data: emailConfig, isLoading: emailLoading } = useEmailIntegration();
  const { data: channelConfig, isLoading: channelLoading } = useChannelIntegration();
  const { data: crmConfig, isLoading: crmLoading } = useCrmIntegration();
  const { data: llmConfig, isLoading: llmLoading } = useLLMConfig();
  const testConnection = useTestConnection();

  // Store latest test result per integration type
  const [testResults, setTestResults] = useState<Partial<Record<IntegrationType, ConnectionTestResult>>>({});
  const [testingType, setTestingType] = useState<IntegrationType | null>(null);

  function handleTest(type: IntegrationType) {
    setTestingType(type);
    testConnection.mutate(type, {
      onSuccess: (result) => {
        setTestResults((prev) => ({ ...prev, [type]: result }));
        setTestingType(null);
      },
      onError: () => {
        setTestingType(null);
      },
    });
  }

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-300 fill-mode-both">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Integrations</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Configuration is read-only — settings are managed via environment variables.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <IntegrationPanel
          title="Email (Gmail)"
          type="email"
          config={emailConfig}
          isLoading={emailLoading}
          onTest={() => handleTest("email")}
          testResult={testResults["email"]}
          isTesting={testingType === "email"}
        />

        <IntegrationPanel
          title="Channels (Slack)"
          type="channels"
          config={channelConfig}
          isLoading={channelLoading}
          onTest={() => handleTest("channels")}
          testResult={testResults["channels"]}
          isTesting={testingType === "channels"}
        />

        <IntegrationPanel
          title="CRM (HubSpot)"
          type="crm"
          config={crmConfig}
          isLoading={crmLoading}
          onTest={() => handleTest("crm")}
          testResult={testResults["crm"]}
          isTesting={testingType === "crm"}
        />

        <IntegrationPanel
          title="LLM (LiteLLM)"
          type="llm"
          config={llmConfig}
          isLoading={llmLoading}
          onTest={() => handleTest("llm")}
          testResult={testResults["llm"]}
          isTesting={testingType === "llm"}
        />
      </div>
    </div>
  );
}
