// src/components/DateRangeSelector.tsx
// Preset selector for date ranges (7d, 30d, 90d, custom).
// Exports DateRange and DatePreset types for consumers.
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export type DatePreset = "7d" | "30d" | "90d" | "custom";

export interface DateRange {
  from: string;
  to: string;
  preset: DatePreset;
}

interface DateRangeSelectorProps {
  value: DateRange;
  onChange: (range: DateRange) => void;
}

function formatDate(d: Date): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function computePresetRange(preset: Exclude<DatePreset, "custom">): DateRange {
  const today = new Date();
  const to = formatDate(today);
  const from = new Date(today);

  if (preset === "7d") {
    from.setDate(today.getDate() - 6);
  } else if (preset === "30d") {
    from.setDate(today.getDate() - 29);
  } else {
    from.setDate(today.getDate() - 89);
  }

  return { from: formatDate(from), to, preset };
}

const PRESETS: { label: string; value: Exclude<DatePreset, "custom"> }[] = [
  { label: "7 days", value: "7d" },
  { label: "30 days", value: "30d" },
  { label: "90 days", value: "90d" },
];

export function DateRangeSelector({ value, onChange }: DateRangeSelectorProps) {
  function handlePreset(preset: Exclude<DatePreset, "custom">) {
    onChange(computePresetRange(preset));
  }

  function handleCustomFrom(e: React.ChangeEvent<HTMLInputElement>) {
    onChange({ ...value, from: e.target.value, preset: "custom" });
  }

  function handleCustomTo(e: React.ChangeEvent<HTMLInputElement>) {
    onChange({ ...value, to: e.target.value, preset: "custom" });
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Preset buttons row */}
      <div className="flex flex-wrap items-center gap-2">
        {PRESETS.map(({ label, value: preset }) => (
          <Button
            key={preset}
            type="button"
            variant={value.preset === preset ? "default" : "outline"}
            size="sm"
            aria-pressed={value.preset === preset}
            onClick={() => handlePreset(preset)}
          >
            {label}
          </Button>
        ))}
        <Button
          type="button"
          variant={value.preset === "custom" ? "default" : "outline"}
          aria-pressed={value.preset === "custom"}
          size="sm"
          onClick={() => onChange({ ...value, preset: "custom" })}
        >
          Custom
        </Button>
      </div>

      {/* Custom date inputs — only shown when preset === "custom" */}
      {value.preset === "custom" && (
        <div className={cn("flex flex-wrap items-end gap-4")}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="date-range-from">From</Label>
            <Input
              id="date-range-from"
              type="date"
              value={value.from}
              onChange={handleCustomFrom}
              max={value.to}
              className="w-36"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="date-range-to">To</Label>
            <Input
              id="date-range-to"
              type="date"
              value={value.to}
              onChange={handleCustomTo}
              min={value.from}
              className="w-36"
            />
          </div>
        </div>
      )}
    </div>
  );
}
