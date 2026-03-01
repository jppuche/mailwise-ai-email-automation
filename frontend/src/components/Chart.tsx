// src/components/Chart.tsx
// Recharts wrapper — ALL imports from 'recharts' MUST stay in this file only.
// Other files must never import from 'recharts' directly.
import {
  ResponsiveContainer,
  LineChart,
  Line,
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
const DEFAULT_COLORS = [
  "#6366f1", // indigo (matches --color-primary in most themes)
  "#22c55e", // green (matches --color-success)
  "#f59e0b", // amber (matches --color-warning)
  "#ef4444", // red (matches --color-error)
  "#06b6d4", // cyan (matches --color-info)
  "#8b5cf6", // violet
  "#ec4899", // pink
  "#14b8a6", // teal
];

export function Chart({
  type,
  data,
  xKey = "name",
  yKey = "value",
  title,
  height = 300,
  colors = DEFAULT_COLORS,
}: ChartProps) {
  return (
    <div className="chart">
      {title && <h3 className="chart__title">{title}</h3>}
      <div className="chart__container" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          {type === "line" ? (
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis
                dataKey={xKey}
                tick={{ fill: "var(--color-text-muted)", fontSize: 12 }}
                axisLine={{ stroke: "var(--color-border)" }}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: "var(--color-text-muted)", fontSize: 12 }}
                axisLine={{ stroke: "var(--color-border)" }}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "var(--color-bg-elevated)",
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius-md)",
                  color: "var(--color-text)",
                }}
              />
              <Line
                type="monotone"
                dataKey={yKey}
                stroke={colors[0]}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
            </LineChart>
          ) : type === "bar" ? (
            <BarChart data={data}>
              <XAxis
                dataKey={xKey}
                tick={{ fill: "var(--color-text-muted)", fontSize: 12 }}
                axisLine={{ stroke: "var(--color-border)" }}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: "var(--color-text-muted)", fontSize: 12 }}
                axisLine={{ stroke: "var(--color-border)" }}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "var(--color-bg-elevated)",
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius-md)",
                  color: "var(--color-text)",
                }}
              />
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
              <Tooltip
                contentStyle={{
                  backgroundColor: "var(--color-bg-elevated)",
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius-md)",
                  color: "var(--color-text)",
                }}
              />
              <Legend
                wrapperStyle={{
                  fontSize: "12px",
                  color: "var(--color-text-muted)",
                }}
              />
            </PieChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
