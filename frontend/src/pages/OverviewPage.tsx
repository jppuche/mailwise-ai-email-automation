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
    <div className="overview-page">
      <h1 className="overview-page__title">Overview</h1>

      {/* ── Stat cards ── */}
      <div className="overview-page__stats">
        <StatCard
          label="Total Emails (30d)"
          value={volume?.total_emails ?? 0}
          isLoading={volumeLoading}
        />
        <StatCard
          label="Classified"
          value={distribution?.total_classified ?? 0}
          isLoading={distLoading}
        />
        <StatCard
          label="Accuracy"
          value={accuracy ? `${accuracy.accuracy_pct.toFixed(1)}%` : "—"}
          isLoading={accuracyLoading}
        />
        <StatCard
          label="Not Overridden"
          value={
            accuracy
              ? accuracy.total_classified - accuracy.total_overridden
              : 0
          }
          isLoading={accuracyLoading}
        />
      </div>

      {/* ── Health section ── */}
      {health && (
        <section className="overview-page__section" aria-labelledby="section-health">
          <h2 className="overview-page__section-title" id="section-health">
            System Health
          </h2>
          <div className="overview-page__health-row">
            <StatusIndicator status={health.status} label={`System: ${health.status}`} />
          </div>
          {health.adapters.length > 0 && (
            <ul className="overview-page__adapters">
              {health.adapters.map((adapter) => (
                <li key={adapter.name} className="overview-page__adapter-item">
                  <StatusIndicator status={adapter.status} label={adapter.name} />
                  {adapter.latency_ms !== null && (
                    <span className="overview-page__adapter-latency">
                      {adapter.latency_ms}ms
                    </span>
                  )}
                  {adapter.error && (
                    <span className="overview-page__adapter-error" role="alert">
                      {adapter.error}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {/* ── Volume chart ── */}
      <section className="overview-page__section" aria-labelledby="section-volume">
        <h2 className="overview-page__section-title" id="section-volume">
          Email Volume (Last 30 Days)
        </h2>
        {volumeLoading ? (
          <div className="overview-page__chart-skeleton" aria-busy="true" />
        ) : (
          <Chart
            type="line"
            data={volumeChartData}
            xKey="name"
            yKey="value"
            height={240}
          />
        )}
      </section>

      {/* ── Activity feed ── */}
      <section className="overview-page__section" aria-labelledby="section-activity">
        <h2 className="overview-page__section-title" id="section-activity">
          Recent Activity
        </h2>
        <ActivityFeed events={activityEvents} isLoading={emailsLoading} />
      </section>
    </div>
  );
}
