// src/pages/OverviewPage.tsx
// Route: / (reviewer + admin)
// Dashboard with stat cards, health status, volume chart, and activity feed.
import { useVolume, useDistribution, useAccuracy } from "@/hooks/useAnalytics";
import { useHealth } from "@/hooks/useHealth";
import { useEmails } from "@/hooks/useEmails";
import { StatCard } from "@/components/StatCard";
import { StatusIndicator } from "@/components/StatusIndicator";
import { Chart } from "@/components/Chart";
import { ActivityFeed } from "@/components/ActivityFeed";
import type { ActivityEvent } from "@/components/ActivityFeed";
import type { ChartDataPoint } from "@/components/Chart";
import type { EmailListItem } from "@/types/generated/api";
import { ACTIVITY_FEED_LIMIT } from "@/utils/constants";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Mail, CheckCircle, Target, ShieldCheck } from "lucide-react";

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function formatDate(d: Date): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/** Last 30 days date range for overview */
function getOverviewDateRange(): { from: string; to: string } {
  const today = new Date();
  const from = new Date(today);
  from.setDate(today.getDate() - 29);
  return { from: formatDate(from), to: formatDate(today) };
}

/** Map recent EmailListItem entries to ActivityEvent for ActivityFeed */
function emailsToActivity(emails: EmailListItem[]): ActivityEvent[] {
  return emails.map((email) => ({
    type: email.state,
    timestamp: email.received_at,
    description: `${email.subject} — ${email.sender_email}`,
    email_id: email.id,
  }));
}

/** Transform volume data_points to ChartDataPoint[] */
function volumeToChartData(
  dataPoints: { date: string; count: number }[],
): ChartDataPoint[] {
  return dataPoints.map((p) => ({ name: p.date, value: p.count }));
}

// ─────────────────────────────────────────────────────────────────────────────
// OverviewPage (main export)
// ─────────────────────────────────────────────────────────────────────────────

export default function OverviewPage() {
  const { from, to } = getOverviewDateRange();

  const { data: volume, isLoading: volumeLoading } = useVolume(from, to);
  const { data: distribution, isLoading: distLoading } = useDistribution(from, to);
  const { data: accuracy, isLoading: accuracyLoading } = useAccuracy(from, to);
  const { data: health } = useHealth();
  const { data: emailsPage, isLoading: emailsLoading } = useEmails(
    {},
    { page: 1, page_size: ACTIVITY_FEED_LIMIT },
  );

  // Derived data — transform in page, not in hooks
  const volumeChartData = volume ? volumeToChartData(volume.data_points) : [];
  const activityEvents = emailsPage ? emailsToActivity(emailsPage.items) : [];

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-300 fill-mode-both">
      <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>

      {/* ── Stat cards with staggered entry ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        {[
          { label: "Total Emails (30d)", value: volume?.total_emails ?? 0, icon: Mail, iconVariant: "primary" as const, isLoading: volumeLoading },
          { label: "Classified", value: distribution?.total_classified ?? 0, icon: CheckCircle, iconVariant: "success" as const, isLoading: distLoading },
          { label: "Accuracy", value: accuracy ? `${accuracy.accuracy_pct.toFixed(1)}%` : "—", icon: Target, iconVariant: "navy" as const, isLoading: accuracyLoading },
          { label: "Not Overridden", value: accuracy ? accuracy.total_classified - accuracy.total_overridden : 0, icon: ShieldCheck, iconVariant: "info" as const, isLoading: accuracyLoading },
        ].map((card, i) => (
          <div
            key={card.label}
            className="animate-in fade-in slide-in-from-bottom-2 fill-mode-both"
            style={{ animationDelay: `${i * 75}ms`, animationDuration: "400ms" }}
          >
            <StatCard {...card} />
          </div>
        ))}
      </div>

      {/* ── Health section ── */}
      {health && (
        <Card aria-labelledby="section-health">
          <CardHeader>
            <h2 id="section-health" className="text-lg font-medium leading-none">
              System Health
            </h2>
          </CardHeader>
          <CardContent>
            <div className="mb-3">
              <StatusIndicator status={health.status} label={`System: ${health.status}`} />
            </div>
            {health.adapters.length > 0 && (
              <ul className="space-y-2">
                {health.adapters.map((adapter) => (
                  <li key={adapter.name} className="flex items-center gap-3">
                    <StatusIndicator status={adapter.status} label={adapter.name} />
                    {adapter.latency_ms !== null && (
                      <span className="text-xs text-muted-foreground font-mono">
                        {adapter.latency_ms}ms
                      </span>
                    )}
                    {adapter.error && (
                      <span className={`text-xs ${adapter.status === "unavailable" ? "text-destructive" : "text-warning"}`} role="alert">
                        {adapter.error}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Volume chart ── */}
      <Card aria-labelledby="section-volume">
        <CardHeader>
          <h2 id="section-volume" className="text-lg font-medium leading-none">
            Email Volume (Last 30 Days)
          </h2>
        </CardHeader>
        <CardContent>
          {volumeLoading ? (
            <Skeleton className="h-60 w-full" />
          ) : (
            <Chart
              type="line"
              data={volumeChartData}
              xKey="name"
              yKey="value"
              height={240}
            />
          )}
        </CardContent>
      </Card>

      {/* ── Activity feed ── */}
      <Card aria-labelledby="section-activity">
        <CardHeader>
          <h2 id="section-activity" className="text-lg font-medium leading-none">
            Recent Activity
          </h2>
        </CardHeader>
        <CardContent>
          <ActivityFeed events={activityEvents} isLoading={emailsLoading} />
        </CardContent>
      </Card>
    </div>
  );
}
