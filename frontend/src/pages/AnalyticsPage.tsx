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
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Download, Mail, Tags, Target, Route as RouteIcon } from "lucide-react";

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
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-300 fill-mode-both">
      {/* ── Page header ── */}
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-semibold tracking-tight">Analytics</h1>
        <div className="flex items-center gap-3">
          <DateRangeSelector value={dateRange} onChange={setDateRange} />
          {isAdmin && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleExport}
              disabled={exportCsv.isPending}
            >
              <Download className="mr-2 h-4 w-4" />
              {exportCsv.isPending ? "Exporting..." : "Export CSV"}
            </Button>
          )}
        </div>
      </div>

      {/* ── Export error ── */}
      {exportCsv.error && (
        <Alert variant="destructive">
          <AlertDescription>
            Export failed: {exportCsv.error.message}
          </AlertDescription>
        </Alert>
      )}

      {/* ── Stat cards ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Emails"
          value={volume?.total_emails ?? 0}
          icon={Mail}
          iconVariant="primary"
          isLoading={volumeLoading}
        />
        <StatCard
          label="Total Classified"
          value={distribution?.total_classified ?? 0}
          icon={Tags}
          iconVariant="success"
          isLoading={distLoading}
        />
        <StatCard
          label="Accuracy"
          value={accuracy ? `${accuracy.accuracy_pct.toFixed(1)}%` : "—"}
          icon={Target}
          iconVariant="navy"
          isLoading={accuracyLoading}
        />
        <StatCard
          label="Total Dispatched"
          value={routing?.total_dispatched ?? 0}
          icon={RouteIcon}
          iconVariant="info"
          isLoading={routingLoading}
        />
      </div>

      {/* ── Volume chart (line) ── */}
      <Card aria-labelledby="section-volume">
        <CardHeader>
          <h2 id="section-volume" className="text-lg font-medium leading-none">
            Email Volume
          </h2>
        </CardHeader>
        <CardContent>
          {volumeError && (
            <Alert variant="destructive" className="mb-4">
              <AlertDescription>
                Failed to load volume data: {volumeError.message}
              </AlertDescription>
            </Alert>
          )}
          {volumeLoading ? (
            <Skeleton className="h-[280px] w-full" />
          ) : (
            <Chart
              type="line"
              data={volumeChartData}
              xKey="name"
              yKey="value"
              height={280}
            />
          )}
        </CardContent>
      </Card>

      {/* ── Classification distribution chart (bar) ── */}
      <Card aria-labelledby="section-distribution">
        <CardHeader>
          <h2 id="section-distribution" className="text-lg font-medium leading-none">
            Actions Distribution
          </h2>
        </CardHeader>
        <CardContent>
          {distError && (
            <Alert variant="destructive" className="mb-4">
              <AlertDescription>
                Failed to load distribution data: {distError.message}
              </AlertDescription>
            </Alert>
          )}
          {distLoading ? (
            <Skeleton className="h-[280px] w-full" />
          ) : (
            <Chart
              type="bar"
              data={actionsChartData}
              xKey="name"
              yKey="value"
              height={280}
            />
          )}
        </CardContent>
      </Card>

      {/* ── Routing channels chart (pie) ── */}
      <Card aria-labelledby="section-routing">
        <CardHeader>
          <h2 id="section-routing" className="text-lg font-medium leading-none">
            Routing Channels
          </h2>
        </CardHeader>
        <CardContent>
          {routingError && (
            <Alert variant="destructive" className="mb-4">
              <AlertDescription>
                Failed to load routing data: {routingError.message}
              </AlertDescription>
            </Alert>
          )}
          {routingLoading ? (
            <Skeleton className="h-[300px] w-full" />
          ) : (
            <Chart
              type="pie"
              data={routingChartData}
              xKey="name"
              yKey="value"
              height={300}
            />
          )}
        </CardContent>
      </Card>

      {/* ── Accuracy detail ── */}
      {accuracy && !accuracyLoading && (
        <Card aria-labelledby="section-accuracy">
          <CardHeader>
            <h2 id="section-accuracy" className="text-lg font-medium leading-none">
              Classification Accuracy
            </h2>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <div className="contents">
                <dt className="text-muted-foreground">Total Classified</dt>
                <dd className="font-medium tabular-nums">{accuracy.total_classified}</dd>
              </div>
              <div className="contents">
                <dt className="text-muted-foreground">Total Overridden</dt>
                <dd className="font-medium tabular-nums">{accuracy.total_overridden}</dd>
              </div>
              <div className="contents">
                <dt className="text-muted-foreground">Accuracy</dt>
                <dd className="font-medium tabular-nums">{accuracy.accuracy_pct.toFixed(2)}%</dd>
              </div>
              <div className="contents">
                <dt className="text-muted-foreground">Period</dt>
                <dd className="font-medium font-mono text-xs">
                  {accuracy.period_start} &rarr; {accuracy.period_end}
                </dd>
              </div>
            </dl>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
