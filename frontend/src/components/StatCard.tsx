// src/components/StatCard.tsx
// Metric card with icon badge, monospace value, delta indicator.

import { TrendingDown, TrendingUp } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const ICON_VARIANT_CLASSES: Record<string, string> = {
  primary: "bg-primary/10 text-primary",
  success: "bg-success/10 text-success",
  warning: "bg-warning/10 text-warning",
  info: "bg-info/10 text-info",
  destructive: "bg-destructive/10 text-destructive",
  navy: "bg-foreground/10 text-foreground",
};

interface StatCardProps {
  label: string;
  value: number | string;
  delta?: number;
  deltaLabel?: string;
  icon?: LucideIcon;
  iconVariant?: keyof typeof ICON_VARIANT_CLASSES;
  isLoading?: boolean;
}

export function StatCard({
  label,
  value,
  delta,
  deltaLabel,
  icon: Icon,
  iconVariant = "primary",
  isLoading,
}: StatCardProps) {
  if (isLoading) {
    return (
      <Card aria-busy="true">
        <CardContent className="pt-6 space-y-2">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-8 w-16" />
        </CardContent>
      </Card>
    );
  }

  const hasDelta = typeof delta === "number";
  const deltaPositive = hasDelta && delta > 0;
  const deltaNegative = hasDelta && delta < 0;

  return (
    <Card>
      <CardContent className="pt-4 sm:pt-6">
        <div className="flex items-start justify-between gap-3 sm:gap-4">
          <div className="min-w-0 flex-1">
            <p className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight text-foreground font-mono tabular-nums">
              {value}
            </p>
            <p className="mt-0.5 sm:mt-1 text-xs sm:text-sm font-medium text-muted-foreground">{label}</p>
          </div>
          {Icon && (
            <div
              className={cn(
                "flex size-8 sm:size-10 shrink-0 items-center justify-center rounded-lg sm:rounded-xl",
                ICON_VARIANT_CLASSES[iconVariant],
              )}
            >
              <Icon className="size-4 sm:size-5" aria-hidden="true" />
            </div>
          )}
        </div>
        {hasDelta && (
          <p
            className={cn(
              "mt-3 flex items-center gap-1 text-xs font-medium",
              deltaPositive && "text-success",
              deltaNegative && "text-destructive",
              !deltaPositive && !deltaNegative && "text-muted-foreground",
            )}
            aria-label={`Change: ${delta > 0 ? "+" : ""}${delta}`}
          >
            {deltaPositive && (
              <TrendingUp className="size-3.5" aria-hidden="true" />
            )}
            {deltaNegative && (
              <TrendingDown className="size-3.5" aria-hidden="true" />
            )}
            {delta > 0 ? "+" : ""}
            {delta}
            {deltaLabel && (
              <span className="text-muted-foreground font-normal ml-1">{deltaLabel}</span>
            )}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
