// src/components/__tests__/Chart.test.tsx
// Tests for the Chart component — mocks recharts to avoid SVG rendering issues
// in jsdom. Verifies that line, bar, and pie chart types render without error
// and that the title is displayed when provided.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

// ─────────────────────────────────────────────────────────────────────────────
// recharts mock — SVG rendering is not supported in jsdom
// All recharts components are replaced with div stubs for test isolation.
// ─────────────────────────────────────────────────────────────────────────────

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  AreaChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="area-chart">{children}</div>
  ),
  Area: () => <div data-testid="area" />,
  BarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="bar-chart">{children}</div>
  ),
  PieChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="pie-chart">{children}</div>
  ),
  Bar: ({ children }: { children?: React.ReactNode }) => <div data-testid="bar">{children}</div>,
  Pie: ({ children }: { children?: React.ReactNode }) => <div data-testid="pie">{children}</div>,
  Cell: () => <div data-testid="cell" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  Tooltip: () => <div data-testid="tooltip" />,
  Legend: () => <div data-testid="legend" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
}));

import { Chart } from "../Chart";
import type { ChartDataPoint } from "../Chart";

// ─────────────────────────────────────────────────────────────────────────────
// Test data
// ─────────────────────────────────────────────────────────────────────────────

const lineData: ChartDataPoint[] = [
  { date: "2026-01-01", count: 5 },
  { date: "2026-01-02", count: 12 },
  { date: "2026-01-03", count: 8 },
];

const barData: ChartDataPoint[] = [
  { name: "respond", value: 10 },
  { name: "escalate", value: 5 },
];

const pieData: ChartDataPoint[] = [
  { name: "slack", value: 15 },
  { name: "email", value: 5 },
];

// ─────────────────────────────────────────────────────────────────────────────
// Chart tests
// ─────────────────────────────────────────────────────────────────────────────

describe("Chart", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders line chart without error", () => {
    render(
      <Chart type="line" data={lineData} xKey="date" yKey="count" />,
    );

    expect(screen.getByTestId("responsive-container")).toBeInTheDocument();
    expect(screen.getByTestId("area-chart")).toBeInTheDocument();
    expect(screen.getByTestId("area")).toBeInTheDocument();
  });

  it("renders bar chart without error", () => {
    render(
      <Chart type="bar" data={barData} xKey="name" yKey="value" />,
    );

    expect(screen.getByTestId("responsive-container")).toBeInTheDocument();
    expect(screen.getByTestId("bar-chart")).toBeInTheDocument();
    expect(screen.getByTestId("bar")).toBeInTheDocument();
  });

  it("renders pie chart without error", () => {
    render(
      <Chart type="pie" data={pieData} xKey="name" yKey="value" />,
    );

    expect(screen.getByTestId("responsive-container")).toBeInTheDocument();
    expect(screen.getByTestId("pie-chart")).toBeInTheDocument();
    expect(screen.getByTestId("pie")).toBeInTheDocument();
  });

  it("displays title when provided", () => {
    render(
      <Chart type="line" data={lineData} title="Email Volume" />,
    );

    expect(screen.getByText("Email Volume")).toBeInTheDocument();
  });

  it("does NOT render a title element when title is omitted", () => {
    render(
      <Chart type="bar" data={barData} />,
    );

    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
  });

  it("renders the chart wrapper container div", () => {
    const { container } = render(
      <Chart type="line" data={lineData} />,
    );

    // Chart is wrapped in a shadcn Card — verify container rendered
    expect(container.firstChild).toBeInTheDocument();
    expect(screen.getByTestId("responsive-container")).toBeInTheDocument();
  });

  it("renders x-axis and y-axis inside area chart", () => {
    render(
      <Chart type="line" data={lineData} xKey="date" yKey="count" />,
    );

    expect(screen.getByTestId("x-axis")).toBeInTheDocument();
    expect(screen.getByTestId("y-axis")).toBeInTheDocument();
  });

  it("renders x-axis and y-axis inside bar chart", () => {
    render(
      <Chart type="bar" data={barData} xKey="name" yKey="value" />,
    );

    expect(screen.getByTestId("x-axis")).toBeInTheDocument();
    expect(screen.getByTestId("y-axis")).toBeInTheDocument();
  });

  it("renders tooltip inside pie chart", () => {
    render(
      <Chart type="pie" data={pieData} xKey="name" yKey="value" />,
    );

    expect(screen.getByTestId("tooltip")).toBeInTheDocument();
  });

  it("renders legend inside pie chart", () => {
    render(
      <Chart type="pie" data={pieData} xKey="name" yKey="value" />,
    );

    expect(screen.getByTestId("legend")).toBeInTheDocument();
  });

  it("renders with empty data array without crashing", () => {
    expect(() => {
      render(<Chart type="line" data={[]} />);
    }).not.toThrow();
  });
});
