// src/components/RuleBuilder.tsx
// Modal form for creating/editing routing rules.
// Create mode: empty form. Edit mode: pre-populated with rule data.
// Does NOT fetch — receives callbacks from the parent page.
import { useState } from "react";
import type {
  RoutingRuleResponse,
  RoutingRuleCreate,
  RoutingConditionSchema,
  RoutingActionSchema,
} from "@/types/generated/api";

interface RuleBuilderProps {
  rule?: RoutingRuleResponse;
  onSubmit: (data: RoutingRuleCreate) => Promise<void>;
  onClose: () => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// Condition row
// ─────────────────────────────────────────────────────────────────────────────

interface ConditionRowProps {
  condition: RoutingConditionSchema;
  index: number;
  onChange: (index: number, field: keyof RoutingConditionSchema, value: string) => void;
  onRemove: (index: number) => void;
}

const CONDITION_FIELDS = [
  { value: "action_slug", label: "Action Slug" },
  { value: "type_slug", label: "Type Slug" },
  { value: "sender_domain", label: "Sender Domain" },
  { value: "confidence", label: "Confidence" },
];

const CONDITION_OPERATORS = [
  { value: "eq", label: "equals" },
  { value: "in", label: "in (comma-separated)" },
  { value: "contains", label: "contains" },
  { value: "matches", label: "matches (regex)" },
];

function ConditionRow({ condition, index, onChange, onRemove }: ConditionRowProps) {
  const valueStr = Array.isArray(condition.value)
    ? condition.value.join(", ")
    : condition.value;

  return (
    <div className="rule-builder__condition-row">
      <select
        className="form-input rule-builder__select"
        value={condition.field}
        onChange={(e) => onChange(index, "field", e.target.value)}
        aria-label={`Condition ${index + 1} field`}
      >
        {CONDITION_FIELDS.map((f) => (
          <option key={f.value} value={f.value}>
            {f.label}
          </option>
        ))}
      </select>

      <select
        className="form-input rule-builder__select"
        value={condition.operator}
        onChange={(e) => onChange(index, "operator", e.target.value)}
        aria-label={`Condition ${index + 1} operator`}
      >
        {CONDITION_OPERATORS.map((op) => (
          <option key={op.value} value={op.value}>
            {op.label}
          </option>
        ))}
      </select>

      <input
        type="text"
        className="form-input rule-builder__condition-value"
        value={valueStr}
        onChange={(e) => onChange(index, "value", e.target.value)}
        placeholder="Value"
        aria-label={`Condition ${index + 1} value`}
      />

      <button
        type="button"
        className="btn btn--danger btn--sm rule-builder__remove-btn"
        onClick={() => onRemove(index)}
        aria-label={`Remove condition ${index + 1}`}
      >
        Remove
      </button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Action row
// ─────────────────────────────────────────────────────────────────────────────

interface ActionRowProps {
  action: RoutingActionSchema;
  index: number;
  onChange: (index: number, field: keyof RoutingActionSchema, value: string) => void;
  onRemove: (index: number) => void;
}

function ActionRow({ action, index, onChange, onRemove }: ActionRowProps) {
  return (
    <div className="rule-builder__action-row">
      <input
        type="text"
        className="form-input"
        value={action.channel}
        onChange={(e) => onChange(index, "channel", e.target.value)}
        placeholder="Channel (e.g. slack, email)"
        aria-label={`Action ${index + 1} channel`}
      />
      <input
        type="text"
        className="form-input"
        value={action.destination}
        onChange={(e) => onChange(index, "destination", e.target.value)}
        placeholder="Destination (e.g. #channel, email@example.com)"
        aria-label={`Action ${index + 1} destination`}
      />
      <button
        type="button"
        className="btn btn--danger btn--sm rule-builder__remove-btn"
        onClick={() => onRemove(index)}
        aria-label={`Remove action ${index + 1}`}
      >
        Remove
      </button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// RuleBuilder modal (main export)
// ─────────────────────────────────────────────────────────────────────────────

function makeDefaultCondition(): RoutingConditionSchema {
  return { field: "action_slug", operator: "eq", value: "" };
}

function makeDefaultAction(): RoutingActionSchema {
  return { channel: "", destination: "" };
}

export function RuleBuilder({ rule, onSubmit, onClose }: RuleBuilderProps) {
  const isEditMode = rule !== undefined;

  const [name, setName] = useState(rule?.name ?? "");
  const [isActive, setIsActive] = useState(rule?.is_active ?? true);
  const [conditions, setConditions] = useState<RoutingConditionSchema[]>(
    rule?.conditions && rule.conditions.length > 0
      ? rule.conditions
      : [makeDefaultCondition()],
  );
  const [actions, setActions] = useState<RoutingActionSchema[]>(
    rule?.actions && rule.actions.length > 0 ? rule.actions : [makeDefaultAction()],
  );
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // ── Condition handlers ──

  function handleConditionChange(
    index: number,
    field: keyof RoutingConditionSchema,
    rawValue: string,
  ) {
    setConditions((prev) =>
      prev.map((cond, i) => {
        if (i !== index) return cond;
        if (field === "value") {
          // For "in" operator, parse comma-separated values into array
          const value =
            cond.operator === "in"
              ? rawValue.split(",").map((v) => v.trim()).filter(Boolean)
              : rawValue;
          return { ...cond, value };
        }
        if (field === "operator") {
          // Reset value when operator changes
          const newValue = rawValue === "in" ? [] : "";
          return { ...cond, operator: rawValue, value: newValue };
        }
        return { ...cond, [field]: rawValue };
      }),
    );
  }

  function handleAddCondition() {
    setConditions((prev) => [...prev, makeDefaultCondition()]);
  }

  function handleRemoveCondition(index: number) {
    setConditions((prev) => prev.filter((_, i) => i !== index));
  }

  // ── Action handlers ──

  function handleActionChange(
    index: number,
    field: keyof RoutingActionSchema,
    value: string,
  ) {
    setActions((prev) =>
      prev.map((action, i) => (i === index ? { ...action, [field]: value } : action)),
    );
  }

  function handleAddAction() {
    setActions((prev) => [...prev, makeDefaultAction()]);
  }

  function handleRemoveAction(index: number) {
    setActions((prev) => prev.filter((_, i) => i !== index));
  }

  // ── Submit ──

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitError(null);
    setSubmitting(true);
    try {
      await onSubmit({ name: name.trim(), is_active: isActive, conditions, actions });
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Failed to save rule");
    } finally {
      setSubmitting(false);
    }
  }

  const isValid =
    name.trim().length > 0 &&
    conditions.length > 0 &&
    conditions.every((c) => c.field && c.operator && (Array.isArray(c.value) ? c.value.length > 0 : c.value.trim().length > 0)) &&
    actions.length > 0 &&
    actions.every((a) => a.channel.trim().length > 0 && a.destination.trim().length > 0);

  return (
    <div className="rule-builder__overlay" role="dialog" aria-modal="true" aria-label={isEditMode ? "Edit routing rule" : "Create routing rule"}>
      <div className="rule-builder">
        <div className="rule-builder__header">
          <h2 className="rule-builder__title">
            {isEditMode ? "Edit Routing Rule" : "New Routing Rule"}
          </h2>
          <button
            type="button"
            className="btn btn--ghost rule-builder__close"
            onClick={onClose}
            aria-label="Close"
            disabled={submitting}
          >
            &#x2715;
          </button>
        </div>

        <form className="rule-builder__form" onSubmit={handleSubmit} noValidate>
          {/* Rule name */}
          <div className="form-group">
            <label className="form-label" htmlFor="rule-name">
              Rule Name <span aria-hidden="true">*</span>
            </label>
            <input
              id="rule-name"
              type="text"
              className="form-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Slack notification for urgent emails"
              required
              disabled={submitting}
            />
          </div>

          {/* Active toggle */}
          <div className="form-group rule-builder__active-group">
            <label className="rule-builder__active-label">
              <input
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                disabled={submitting}
              />
              <span>Active</span>
            </label>
          </div>

          {/* Conditions */}
          <section className="rule-builder__section" aria-labelledby="conditions-label">
            <div className="rule-builder__section-header">
              <h3 className="rule-builder__section-title" id="conditions-label">
                Conditions <span aria-hidden="true">*</span>
              </h3>
              <button
                type="button"
                className="btn btn--secondary btn--sm"
                onClick={handleAddCondition}
                disabled={submitting}
              >
                Add Condition
              </button>
            </div>
            {conditions.length === 0 && (
              <p className="rule-builder__empty-hint">
                At least one condition is required.
              </p>
            )}
            {conditions.map((cond, i) => (
              <ConditionRow
                key={i}
                condition={cond}
                index={i}
                onChange={handleConditionChange}
                onRemove={handleRemoveCondition}
              />
            ))}
          </section>

          {/* Actions */}
          <section className="rule-builder__section" aria-labelledby="actions-label">
            <div className="rule-builder__section-header">
              <h3 className="rule-builder__section-title" id="actions-label">
                Actions <span aria-hidden="true">*</span>
              </h3>
              <button
                type="button"
                className="btn btn--secondary btn--sm"
                onClick={handleAddAction}
                disabled={submitting}
              >
                Add Action
              </button>
            </div>
            {actions.length === 0 && (
              <p className="rule-builder__empty-hint">
                At least one action is required.
              </p>
            )}
            {actions.map((action, i) => (
              <ActionRow
                key={i}
                action={action}
                index={i}
                onChange={handleActionChange}
                onRemove={handleRemoveAction}
              />
            ))}
          </section>

          {submitError && (
            <div className="rule-builder__error" role="alert">
              {submitError}
            </div>
          )}

          <div className="rule-builder__form-actions">
            <button
              type="submit"
              className="btn btn--primary"
              disabled={submitting || !isValid}
            >
              {submitting ? "Saving..." : isEditMode ? "Update Rule" : "Create Rule"}
            </button>
            <button
              type="button"
              className="btn btn--secondary"
              onClick={onClose}
              disabled={submitting}
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
