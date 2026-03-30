// src/components/Chart.tsx
// Recharts wrapper — ALL imports from 'recharts' MUST stay in this file only.
// Other files must never import from 'recharts' directly.
import { useEffect, useState } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";
import { Card, CardHeader, CardContent } from "@/components/ui/card";

// ChartDataPoint is a documented exception to "no loose types":
// recharts requires a flexible record as data shape.
export type ChartDataPoint = Record<string, string | number>;

interface ChartProps {
  type: "line" | "bar" | "pie";
  data: ChartDataPoint[];
  xKey?: string;
  yKey?: string;
  title?: string;
  height?: number;
  colors?: string[];
}

// Default chart colors — using hex values since recharts needs direct color values,
// not CSS custom properties (recharts renders SVG, which doesn't resolve CSS vars).
// Mboard palette: navy + orange as primary dual series, then semantics.
const DEFAULT_COLORS = [
  "#1E2A5E", // accent-navy (chart series 1)
  "#FF8C42", // accent orange (chart series 2)
  "#22c55e", // success green
  "#3B82F6", // info blue
  "#EF4444", // destructive red
  "#8b5cf6", // violet
  "#ec4899", // pink
  "#14b8a6", // teal
];

// Theme-aware chart styling — recharts SVG can't use CSS vars, so we detect theme.
const CHART_THEME = {
  light: {
    axisTick: "#6B7280",
    axisLine: "#E8ECF4",
    grid: "#E8ECF4",
    lineStroke: "#1E2A5E",
    tooltip: { backgroundColor: "#1E2A5E", border: "none", borderRadius: "10px", color: "#ffffff", boxShadow: "0 8px 24px rgba(15, 21, 53, 0.15)" },
  },
  dark: {
    axisTick: "#8B92A9",
    axisLine: "rgba(255,255,255,0.08)",
    grid: "rgba(255,255,255,0.06)",
    lineStroke: "#60A5FA",
    tooltip: { backgroundColor: "#131831", border: "1px solid rgba(255,255,255,0.12)", borderRadius: "10px", color: "#E6EDF3", boxShadow: "0 8px 24px rgba(0, 0, 0, 0.4)" },
  },
} as const;

function useChartTheme() {
  const [isDark, setIsDark] = useState(() =>
    typeof document !== "undefined" && document.documentElement.classList.contains("dark"),
  );
  useEffect(() => {
    const observer = new MutationObserver(() => {
      setIsDark(document.documentElement.classList.contains("dark"));
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);
  return isDark ? CHART_THEME.dark : CHART_THEME.light;
}

/** Styled chart tooltip — replaces default "value : N" with formatted label. */
function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: { value?: number }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ backgroundColor: "var(--color-card, #fff)", border: "1px solid var(--color-border, #e5e7eb)", borderRadius: 8, padding: "8px 12px", boxShadow: "0 4px 12px rgba(0,0,0,0.1)", fontSize: 13 }}>
      <p style={{ fontWeight: 600, marginBottom: 2, color: "var(--color-foreground, #111)" }}>{label}</p>
      <p style={{ color: "var(--color-muted-foreground, #6b7280)" }}>{payload[0].value?.toLocaleString()}</p>
    </div>
  );
}

export function Chart({
  type,
  data,
  xKey = "name",
  yKey = "value",
  title,
  height = 300,
  colors = DEFAULT_COLORS,
}: ChartProps) {
  const theme = useChartTheme();

  const chartContent = (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        {type === "line" ? (
              <AreaChart data={data}>
                <defs>
                  <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={theme.lineStroke} stopOpacity={0.35} />
                    <stop offset="100%" stopColor={theme.lineStroke} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
                <XAxis
                  dataKey={xKey}
                  tick={{ fill: theme.axisTick, fontSize: 12 }}
                  axisLine={{ stroke: theme.axisLine }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fill: theme.axisTick, fontSize: 12 }}
                  axisLine={{ stroke: theme.axisLine }}
                  tickLine={false}
                />
                <Tooltip content={<ChartTooltip />} />
                <Area
                  type="monotone"
                  dataKey={yKey}
                  stroke={theme.lineStroke}
                  strokeWidth={2}
                  fill="url(#areaGradient)"
                  dot={false}
                  activeDot={{ r: 4 }}
                />
              </AreaChart>
            ) : type === "bar" ? (
              <BarChart data={data}>
                <XAxis
                  dataKey={xKey}
                  tick={{ fill: theme.axisTick, fontSize: 12 }}
                  axisLine={{ stroke: theme.axisLine }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fill: theme.axisTick, fontSize: 12 }}
                  axisLine={{ stroke: theme.axisLine }}
                  tickLine={false}
                />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey={yKey} radius={[4, 4, 0, 0]}>
                  {data.map((_, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={colors[index % colors.length]}
                    />
                  ))}
                </Bar>
              </BarChart>
            ) : (
              <PieChart>
                <Pie
                  data={data}
                  dataKey={yKey}
                  nameKey={xKey}
                  cx="50%"
                  cy="50%"
                  innerRadius={Math.min(height / 2 - 40, 120) * 0.55}
                  outerRadius={Math.min(height / 2 - 40, 120)}
                  label
                >
                  {data.map((_, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={colors[index % colors.length]}
                    />
                  ))}
                </Pie>
                <Tooltip content={<ChartTooltip />} />
                <Legend
                  wrapperStyle={{
                    fontSize: "12px",
                    color: theme.axisTick,
                  }}
                  formatter={(value: string) => (
                    <span style={{ color: theme.axisTick }}>{value}</span>
                  )}
                />
              </PieChart>
            )}
      </ResponsiveContainer>
    </div>
  );

  // When title is provided, Chart renders its own Card wrapper.
  // When no title, the parent page provides the Card — avoids double nesting.
  if (title) {
    return (
      <Card className="gap-0 py-0">
        <CardHeader className="px-6 pt-5 pb-2">
          <h2 className="text-lg font-medium leading-none text-foreground">
            {title}
          </h2>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          {chartContent}
        </CardContent>
      </Card>
    );
  }

  return chartContent;
}
