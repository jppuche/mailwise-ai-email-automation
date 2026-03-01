// src/pages/AnalyticsPage.tsx
// Route: /analytics (reviewer + admin)
// DateRangeSelector + 4 chart sections + CSV export (admin only).
import { useState } from "react";
import {
  useVolume,
  useDistribution,
  useAccuracy,
  useRoutingAnalytics,
  useExportCsv,
} from "@/hooks/useAnalytics";
import { useAuth } from "@/contexts/AuthContext";
import { Chart } from "@/components/Chart";
import { StatCard } from "@/components/StatCard";
import { DateRangeSelector } from "@/components/DateRangeSelector";
import type { DateRange } from "@/components/DateRangeSelector";
import type { ChartDataPoint } from "@/components/Chart";
import type { DistributionItem, RoutingChannelStat } from "@/types/generated/api";
import { DEFAULT_DATE_PRESET } from "@/utils/constants";

// ─────────────────────────────────────────────────────────────────────────────
// Default date range computation
// ─────────────────────────────────────────────────────────────────────────────

function formatDate(d: Date): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function computeInitialRange(): DateRange {
  const today = new Date();
  const from = new Date(today);
  from.setDate(today.getDate() - 29); // 30d preset → last 30 days inclusive
  return {
    from: formatDate(from),
    to: formatDate(today),
    preset: DEFAULT_DATE_PRESET,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Data transformers — page is responsible for shaping data to ChartDataPoint[]
// ─────────────────────────────────────────────────────────────────────────────

function volumeToChartData(
  dataPoints: { date: string; count: number }[],
): ChartDataPoint[] {
  return dataPoints.map((p) => ({ name: p.date, value: p.count }));
}

function distributionToChartData(items: DistributionItem[]): ChartDataPoint[] {
  return items.map((item) => ({
    name: item.display_name,
    value: item.count,
  }));
}

function routingToChartData(channels: RoutingChannelStat[]): ChartDataPoint[] {
  return channels.map((ch) => ({
    name: ch.channel,
    value: ch.dispatched,
  }));
}

// ─────────────────────────────────────────────────────────────────────────────
// AnalyticsPage (main export)
// ─────────────────────────────────────────────────────────────────────────────

export default function AnalyticsPage() {
  const [dateRange, setDateRange] = useState<DateRange>(computeInitialRange);
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const { data: volume, isLoading: volumeLoading, error: volumeError } = useVolume(
    dateRange.from,
    dateRange.to,
  );
  const {
    data: distribution,
    isLoading: distLoading,
    error: distError,
  } = useDistribution(dateRange.from, dateRange.to);
  const { data: accuracy, isLoading: accuracyLoading } = useAccuracy(
    dateRange.from,
    dateRange.to,
  );
  const {
    data: routing,
    isLoading: routingLoading,
    error: routingError,
  } = useRoutingAnalytics(dateRange.from, dateRange.to);
  const exportCsv = useExportCsv();

  // Derived chart data — transform in page, not in hooks
  const volumeChartData = volume ? volumeToChartData(volume.data_points) : [];
  const actionsChartData = distribution ? distributionToChartData(distribution.actions) : [];
  const routingChartData = routing ? routingToChartData(routing.channels) : [];

  function handleExport() {
    exportCsv.mutate({ startDate: dateRange.from, endDate: dateRange.to });
  }

  return (
    <div className="analytics-page">
      <div className="analytics-page__header">
        <h1 className="analytics-page__title">Analytics</h1>
        <div className="analytics-page__controls">
          <DateRangeSelector value={dateRange} onChange={setDateRange} />
          {isAdmin && (
            <button
              type="button"
              className="btn btn--secondary"
              onClick={handleExport}
              disabled={exportCsv.isPending}
            >
              {exportCsv.isPending ? "Exporting..." : "Export CSV"}
            </button>
          )}
        </div>
      </div>

      {exportCsv.error && (
        <div className="analytics-page__error" role="alert">
          Export failed: {exportCsv.error.message}
        </div>
      )}

      {/* ── Accuracy stat card ── */}
      <div className="analytics-page__stats">
        <StatCard
          label="Total Emails"
          value={volume?.total_emails ?? 0}
          isLoading={volumeLoading}
        />
        <StatCard
          label="Total Classified"
          value={distribution?.total_classified ?? 0}
          isLoading={distLoading}
        />
        <StatCard
          label="Accuracy"
          value={accuracy ? `${accuracy.accuracy_pct.toFixed(1)}%` : "—"}
          isLoading={accuracyLoading}
        />
        <StatCard
          label="Total Dispatched"
          value={routing?.total_dispatched ?? 0}
          isLoading={routingLoading}
        />
      </div>

      {/* ── Volume chart (line) ── */}
      <section className="analytics-page__section" aria-labelledby="section-volume">
        <h2 className="analytics-page__section-title" id="section-volume">
          Email Volume
        </h2>
        {volumeError && (
          <div className="analytics-page__error" role="alert">
            Failed to load volume data: {volumeError.message}
          </div>
        )}
        {volumeLoading ? (
          <div className="analytics-page__chart-skeleton" aria-busy="true" />
        ) : (
          <Chart
            type="line"
            data={volumeChartData}
            xKey="name"
            yKey="value"
            height={280}
          />
        )}
      </section>

      {/* ── Classification distribution chart (bar) ── */}
      <section className="analytics-page__section" aria-labelledby="section-distribution">
        <h2 className="analytics-page__section-title" id="section-distribution">
          Actions Distribution
        </h2>
        {distError && (
          <div className="analytics-page__error" role="alert">
            Failed to load distribution data: {distError.message}
          </div>
        )}
        {distLoading ? (
          <div className="analytics-page__chart-skeleton" aria-busy="true" />
        ) : (
          <Chart
            type="bar"
            data={actionsChartData}
            xKey="name"
            yKey="value"
            height={280}
          />
        )}
      </section>

      {/* ── Routing channels chart (pie) ── */}
      <section className="analytics-page__section" aria-labelledby="section-routing">
        <h2 className="analytics-page__section-title" id="section-routing">
          Routing Channels
        </h2>
        {routingError && (
          <div className="analytics-page__error" role="alert">
            Failed to load routing data: {routingError.message}
          </div>
        )}
        {routingLoading ? (
          <div className="analytics-page__chart-skeleton" aria-busy="true" />
        ) : (
          <Chart
            type="pie"
            data={routingChartData}
            xKey="name"
            yKey="value"
            height={300}
          />
        )}
      </section>

      {/* ── Accuracy detail ── */}
      {accuracy && !accuracyLoading && (
        <section className="analytics-page__section" aria-labelledby="section-accuracy">
          <h2 className="analytics-page__section-title" id="section-accuracy">
            Classification Accuracy
          </h2>
          <div className="analytics-page__accuracy-detail">
            <dl className="analytics-page__accuracy-dl">
              <div className="analytics-page__accuracy-row">
                <dt>Total Classified</dt>
                <dd>{accuracy.total_classified}</dd>
              </div>
              <div className="analytics-page__accuracy-row">
                <dt>Total Overridden</dt>
                <dd>{accuracy.total_overridden}</dd>
              </div>
              <div className="analytics-page__accuracy-row">
                <dt>Accuracy</dt>
                <dd>{accuracy.accuracy_pct.toFixed(2)}%</dd>
              </div>
              <div className="analytics-page__accuracy-row">
                <dt>Period</dt>
                <dd>{accuracy.period_start} → {accuracy.period_end}</dd>
              </div>
            </dl>
          </div>
        </section>
      )}
    </div>
  );
}
