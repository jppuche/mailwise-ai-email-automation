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
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

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
      <Badge
        variant="outline"
        className="border-success/40 bg-success/10 text-success"
      >
        Yes
      </Badge>
    ) : (
      <Badge
        variant="outline"
        className="border-destructive/40 bg-destructive/10 text-destructive"
      >
        No
      </Badge>
    );
  }
  if (typeof value === "number") {
    return (
      <span className="font-mono text-sm text-foreground">{value}</span>
    );
  }
  return (
    <span className="font-mono text-sm text-foreground break-all">
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
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {/* Loading state */}
        {isLoading && (
          <div className="space-y-2" aria-busy="true">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        )}

        {/* Empty state */}
        {!isLoading && !config && (
          <p className="text-sm text-muted-foreground">
            No configuration available.
          </p>
        )}

        {/* Config fields */}
        {config && (
          <dl className="grid grid-cols-[auto_1fr] items-baseline gap-x-6 gap-y-2">
            {(Object.entries(config) as [string, unknown][]).map(
              ([key, value]) => (
                <div
                  key={key}
                  className="contents"
                >
                  <dt className="text-sm text-muted-foreground whitespace-nowrap">
                    {humanizeKey(key)}
                  </dt>
                  <dd>{renderConfigValue(value)}</dd>
                </div>
              )
            )}
          </dl>
        )}

        {/* Test connection */}
        <div className="flex flex-col gap-2 pt-2 border-t border-border">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={onTest}
            disabled={isTesting}
            className="w-fit"
          >
            {isTesting ? "Testing..." : "Test Connection"}
          </Button>

          {testResult && (
            <p
              role="status"
              className={cn(
                "text-sm",
                testResult.success
                  ? "text-success"
                  : "text-destructive"
              )}
            >
              {testResult.success ? (
                <>
                  Connection OK
                  {testResult.latency_ms !== null &&
                    ` (${testResult.latency_ms}ms)`}
                </>
              ) : (
                <>Failed: {testResult.error_detail ?? "unknown error"}</>
              )}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
