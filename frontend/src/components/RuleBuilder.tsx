// src/components/RuleBuilder.tsx
// Modal form for creating/editing routing rules.
// Create mode: empty form. Edit mode: pre-populated with rule data.
// Does NOT fetch — receives callbacks from the parent page.
import { useState } from "react";
import { X } from "lucide-react";
import type {
  RoutingRuleResponse,
  RoutingRuleCreate,
  RoutingConditionSchema,
  RoutingActionSchema,
} from "@/types/generated/api";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

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
    <div className="flex flex-wrap gap-2 items-center">
      <select
        className={cn(
          "flex h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm",
          "focus:outline-none focus:ring-1 focus:ring-ring",
          "disabled:cursor-not-allowed disabled:opacity-50",
          "min-w-[140px]",
        )}
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
        className={cn(
          "flex h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm",
          "focus:outline-none focus:ring-1 focus:ring-ring",
          "disabled:cursor-not-allowed disabled:opacity-50",
          "min-w-[160px]",
        )}
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

      <Input
        type="text"
        className="min-w-[140px] flex-1"
        value={valueStr}
        onChange={(e) => onChange(index, "value", e.target.value)}
        placeholder="Value"
        aria-label={`Condition ${index + 1} value`}
      />

      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-9 w-9 text-muted-foreground hover:text-destructive shrink-0"
        onClick={() => onRemove(index)}
        aria-label={`Remove condition ${index + 1}`}
      >
        <X className="h-4 w-4" />
      </Button>
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
    <div className="flex flex-wrap gap-2 items-center">
      <Input
        type="text"
        className="min-w-[140px] flex-1"
        value={action.channel}
        onChange={(e) => onChange(index, "channel", e.target.value)}
        placeholder="Channel (e.g. slack, email)"
        aria-label={`Action ${index + 1} channel`}
      />
      <Input
        type="text"
        className="min-w-[180px] flex-1"
        value={action.destination}
        onChange={(e) => onChange(index, "destination", e.target.value)}
        placeholder="Destination (e.g. #channel, email@example.com)"
        aria-label={`Action ${index + 1} destination`}
      />
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-9 w-9 text-muted-foreground hover:text-destructive shrink-0"
        onClick={() => onRemove(index)}
        aria-label={`Remove action ${index + 1}`}
      >
        <X className="h-4 w-4" />
      </Button>
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
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !submitting) onClose();
      }}
    >
      <DialogContent
        className="max-w-2xl max-h-[90vh] overflow-y-auto"
      >
        <DialogHeader>
          <DialogTitle>
            {isEditMode ? "Edit Routing Rule" : "New Routing Rule"}
          </DialogTitle>
        </DialogHeader>

        <form className="space-y-5" onSubmit={handleSubmit} noValidate>
          {/* Rule name */}
          <div className="space-y-1.5">
            <Label htmlFor="rule-name">
              Rule Name <span className="text-destructive" aria-hidden="true">*</span>
            </Label>
            <Input
              id="rule-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Slack notification for urgent emails"
              required
              disabled={submitting}
            />
          </div>

          {/* Active toggle */}
          <div className="flex items-center gap-3">
            <Switch
              id="rule-active"
              checked={isActive}
              onCheckedChange={setIsActive}
              disabled={submitting}
            />
            <Label htmlFor="rule-active" className="cursor-pointer">
              Active
            </Label>
          </div>

          {/* Conditions */}
          <section aria-labelledby="conditions-label">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold" id="conditions-label">
                Conditions <span className="text-destructive" aria-hidden="true">*</span>
              </h3>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleAddCondition}
                disabled={submitting}
              >
                Add Condition
              </Button>
            </div>
            {conditions.length === 0 && (
              <p className="text-sm text-muted-foreground">
                At least one condition is required.
              </p>
            )}
            <div className="space-y-2">
              {conditions.map((cond, i) => (
                <ConditionRow
                  key={i}
                  condition={cond}
                  index={i}
                  onChange={handleConditionChange}
                  onRemove={handleRemoveCondition}
                />
              ))}
            </div>
          </section>

          {/* Actions */}
          <section aria-labelledby="actions-label">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold" id="actions-label">
                Actions <span className="text-destructive" aria-hidden="true">*</span>
              </h3>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleAddAction}
                disabled={submitting}
              >
                Add Action
              </Button>
            </div>
            {actions.length === 0 && (
              <p className="text-sm text-muted-foreground">
                At least one action is required.
              </p>
            )}
            <div className="space-y-2">
              {actions.map((action, i) => (
                <ActionRow
                  key={i}
                  action={action}
                  index={i}
                  onChange={handleActionChange}
                  onRemove={handleRemoveAction}
                />
              ))}
            </div>
          </section>

          {submitError && (
            <p className="text-destructive text-sm" role="alert">
              {submitError}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={submitting || !isValid}
            >
              {submitting ? "Saving..." : isEditMode ? "Update Rule" : "Create Rule"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
