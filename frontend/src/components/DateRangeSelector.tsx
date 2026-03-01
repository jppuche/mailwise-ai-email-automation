// src/components/DateRangeSelector.tsx
// Preset selector for date ranges (7d, 30d, 90d, custom).
// Exports DateRange and DatePreset types for consumers.

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
    <div className="date-range-selector">
      <div className="date-range-selector__presets">
        {PRESETS.map(({ label, value: preset }) => (
          <button
            key={preset}
            type="button"
            className={`date-range-selector__btn${value.preset === preset ? " date-range-selector__btn--active" : ""}`}
            onClick={() => handlePreset(preset)}
          >
            {label}
          </button>
        ))}
        <button
          type="button"
          className={`date-range-selector__btn${value.preset === "custom" ? " date-range-selector__btn--active" : ""}`}
          onClick={() =>
            onChange({ ...value, preset: "custom" })
          }
        >
          Custom
        </button>
      </div>

      {value.preset === "custom" && (
        <div className="date-range-selector__custom">
          <label className="date-range-selector__custom-label">
            From
            <input
              type="date"
              className="form-input date-range-selector__custom-input"
              value={value.from}
              onChange={handleCustomFrom}
              max={value.to}
            />
          </label>
          <label className="date-range-selector__custom-label">
            To
            <input
              type="date"
              className="form-input date-range-selector__custom-input"
              value={value.to}
              onChange={handleCustomTo}
              min={value.from}
            />
          </label>
        </div>
      )}
    </div>
  );
}
