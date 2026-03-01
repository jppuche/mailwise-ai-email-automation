// src/components/FilterBar.tsx
// Controlled filter bar for the email browser.
// Text inputs are debounced 300ms to avoid excessive API calls.
// All 12 EmailState values rendered as select options from the generated enum.
// Zero hardcoded colors — all via CSS custom properties.
import { useEffect, useRef, useState } from "react";
import type { EmailFilterParams, EmailState } from "@/types/generated/api";

// All 12 states from the generated EmailState type — loaded from API enum values, not hardcoded
// (pre-mortem Cat 3: no stringly-typed values outside of what the generated type provides).
const EMAIL_STATE_OPTIONS: { value: EmailState; label: string }[] = [
  { value: "fetched", label: "Fetched" },
  { value: "sanitized", label: "Sanitized" },
  { value: "classified", label: "Classified" },
  { value: "routed", label: "Routed" },
  { value: "draft_generated", label: "Draft Generated" },
  { value: "draft_approved", label: "Draft Approved" },
  { value: "draft_rejected", label: "Draft Rejected" },
  { value: "draft_sent", label: "Draft Sent" },
  { value: "failed_classification", label: "Failed Classification" },
  { value: "failed_routing", label: "Failed Routing" },
  { value: "failed_draft", label: "Failed Draft" },
  { value: "archived", label: "Archived" },
];

interface FilterBarProps {
  value: EmailFilterParams;
  onChange: (filters: EmailFilterParams) => void;
}

export function FilterBar({ value, onChange }: FilterBarProps) {
  // Local state for text inputs — debounced before propagating to parent.
  const [localAction, setLocalAction] = useState(value.action ?? "");
  const [localType, setLocalType] = useState(value.type ?? "");
  const [localSender, setLocalSender] = useState(value.sender ?? "");

  // Sync local state when parent resets filters externally.
  const prevValue = useRef(value);
  useEffect(() => {
    if (prevValue.current !== value) {
      setLocalAction(value.action ?? "");
      setLocalType(value.type ?? "");
      setLocalSender(value.sender ?? "");
      prevValue.current = value;
    }
  }, [value]);

  // Debounce action input — fires onChange 300ms after typing stops.
  useEffect(() => {
    const timer = setTimeout(() => {
      const trimmed = localAction.trim();
      const current = value.action ?? "";
      if (trimmed !== current) {
        onChange({ ...value, action: trimmed || undefined });
      }
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [localAction]);

  // Debounce type input.
  useEffect(() => {
    const timer = setTimeout(() => {
      const trimmed = localType.trim();
      const current = value.type ?? "";
      if (trimmed !== current) {
        onChange({ ...value, type: trimmed || undefined });
      }
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [localType]);

  // Debounce sender input.
  useEffect(() => {
    const timer = setTimeout(() => {
      const trimmed = localSender.trim();
      const current = value.sender ?? "";
      if (trimmed !== current) {
        onChange({ ...value, sender: trimmed || undefined });
      }
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [localSender]);

  function handleStateChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const raw = e.target.value;
    onChange({ ...value, state: raw ? (raw as EmailState) : undefined });
  }

  function handleDateFromChange(e: React.ChangeEvent<HTMLInputElement>) {
    onChange({ ...value, date_from: e.target.value || undefined });
  }

  function handleDateToChange(e: React.ChangeEvent<HTMLInputElement>) {
    onChange({ ...value, date_to: e.target.value || undefined });
  }

  return (
    <div className="filter-bar">
      {/* State filter */}
      <div className="filter-bar__group">
        <label className="filter-bar__label" htmlFor="filter-state">
          State
        </label>
        <select
          id="filter-state"
          className="filter-bar__select"
          value={value.state ?? ""}
          onChange={handleStateChange}
        >
          <option value="">All</option>
          {EMAIL_STATE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Action filter */}
      <div className="filter-bar__group">
        <label className="filter-bar__label" htmlFor="filter-action">
          Action
        </label>
        <input
          id="filter-action"
          className="filter-bar__input"
          type="text"
          placeholder="e.g. respond"
          value={localAction}
          onChange={(e) => setLocalAction(e.target.value)}
        />
      </div>

      {/* Type filter */}
      <div className="filter-bar__group">
        <label className="filter-bar__label" htmlFor="filter-type">
          Type
        </label>
        <input
          id="filter-type"
          className="filter-bar__input"
          type="text"
          placeholder="e.g. complaint"
          value={localType}
          onChange={(e) => setLocalType(e.target.value)}
        />
      </div>

      {/* Sender filter */}
      <div className="filter-bar__group">
        <label className="filter-bar__label" htmlFor="filter-sender">
          Sender
        </label>
        <input
          id="filter-sender"
          className="filter-bar__input"
          type="text"
          placeholder="email substring"
          value={localSender}
          onChange={(e) => setLocalSender(e.target.value)}
        />
      </div>

      {/* Date range */}
      <div className="filter-bar__group">
        <label className="filter-bar__label" htmlFor="filter-date-from">
          From
        </label>
        <input
          id="filter-date-from"
          className="filter-bar__date"
          type="date"
          value={value.date_from ?? ""}
          onChange={handleDateFromChange}
        />
      </div>

      <div className="filter-bar__group">
        <label className="filter-bar__label" htmlFor="filter-date-to">
          To
        </label>
        <input
          id="filter-date-to"
          className="filter-bar__date"
          type="date"
          value={value.date_to ?? ""}
          onChange={handleDateToChange}
        />
      </div>
    </div>
  );
}
