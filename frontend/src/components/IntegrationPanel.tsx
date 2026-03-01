// src/components/IntegrationPanel.tsx
// Read-only config display + test connection button for each integration type.
// Config is from env vars — no PUT/PATCH (handoff delta #2/#8).
import type {
  EmailIntegrationConfig,
  ChannelIntegrationConfig,
  CRMIntegrationConfig,
  LLMIntegrationConfig,
  ConnectionTestResult,
} from "@/types/generated/api";

type IntegrationConfig =
  | EmailIntegrationConfig
  | ChannelIntegrationConfig
  | CRMIntegrationConfig
  | LLMIntegrationConfig;

interface IntegrationPanelProps {
  title: string;
  type: "email" | "channels" | "crm" | "llm";
  config: IntegrationConfig | undefined;
  isLoading: boolean;
  onTest: () => void;
  testResult?: ConnectionTestResult;
  isTesting?: boolean;
}

function renderConfigValue(value: unknown): React.ReactNode {
  if (typeof value === "boolean") {
    return value ? (
      <span className="integration-panel__bool integration-panel__bool--true">Yes</span>
    ) : (
      <span className="integration-panel__bool integration-panel__bool--false">No</span>
    );
  }
  if (typeof value === "number") {
    return <span className="integration-panel__field-value">{value}</span>;
  }
  return (
    <span className="integration-panel__field-value integration-panel__field-value--mono">
      {String(value)}
    </span>
  );
}

function humanizeKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function IntegrationPanel({
  title,
  config,
  isLoading,
  onTest,
  testResult,
  isTesting,
}: IntegrationPanelProps) {
  return (
    <div className="integration-panel">
      <div className="integration-panel__header">
        <h3 className="integration-panel__title">{title}</h3>
      </div>

      {isLoading && (
        <div className="integration-panel__loading" aria-busy="true">
          Loading config...
        </div>
      )}

      {!isLoading && !config && (
        <div className="integration-panel__empty">
          No configuration available.
        </div>
      )}

      {config && (
        <dl className="integration-panel__fields">
          {(Object.entries(config) as [string, unknown][]).map(([key, value]) => (
            <div key={key} className="integration-panel__field">
              <dt className="integration-panel__field-label">{humanizeKey(key)}</dt>
              <dd>{renderConfigValue(value)}</dd>
            </div>
          ))}
        </dl>
      )}

      <div className="integration-panel__test">
        <button
          type="button"
          className="btn btn--secondary integration-panel__test-btn"
          onClick={onTest}
          disabled={isTesting}
        >
          {isTesting ? "Testing..." : "Test Connection"}
        </button>

        {testResult && (
          <div
            className={`integration-panel__test-result${testResult.success ? " integration-panel__test-result--success" : " integration-panel__test-result--error"}`}
            role="status"
          >
            {testResult.success ? (
              <>
                Connection OK
                {testResult.latency_ms !== null && ` (${testResult.latency_ms}ms)`}
              </>
            ) : (
              <>Failed: {testResult.error_detail ?? "unknown error"}</>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
