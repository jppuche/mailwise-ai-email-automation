// src/components/RuleCard.tsx
// Routing rule card with toggle and action buttons.
// Supports drag handle for @dnd-kit/sortable (handle passed as children by parent).
import { useState } from "react";
import type { RoutingRuleResponse } from "@/types/generated/api";

interface RuleCardProps {
  rule: RoutingRuleResponse;
  onEdit: (rule: RoutingRuleResponse) => void;
  onDelete: (id: string) => void;
  onToggleActive: (id: string, isActive: boolean) => void;
  onTest?: (rule: RoutingRuleResponse) => void;
  dragHandleProps?: React.HTMLAttributes<HTMLSpanElement>;
}

// ─────────────────────────────────────────────────────────────────────────────
// Confirm Delete Modal
// ─────────────────────────────────────────────────────────────────────────────

interface ConfirmDeleteModalProps {
  ruleName: string;
  onConfirm: () => void;
  onCancel: () => void;
}

function ConfirmDeleteModal({ ruleName, onConfirm, onCancel }: ConfirmDeleteModalProps) {
  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Confirm delete rule">
      <div className="modal">
        <h3 className="modal__title">Delete Rule</h3>
        <p className="modal__body">
          Are you sure you want to delete <strong>{ruleName}</strong>? This action cannot be
          undone.
        </p>
        <div className="modal__actions">
          <button className="btn btn--danger" onClick={onConfirm}>
            Delete
          </button>
          <button className="btn btn--secondary" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// RuleCard (main export)
// ─────────────────────────────────────────────────────────────────────────────

export function RuleCard({
  rule,
  onEdit,
  onDelete,
  onToggleActive,
  onTest,
  dragHandleProps,
}: RuleCardProps) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  const visibleConditions = rule.conditions.slice(0, 2);
  const extraConditions = rule.conditions.length - 2;

  return (
    <>
      <div className={`rule-card${!rule.is_active ? " rule-card--inactive" : ""}`}>
        <div className="rule-card__header">
          <span
            className="rule-card__drag-handle"
            title="Drag to reorder"
            aria-label="Drag to reorder"
            {...dragHandleProps}
          >
            &#10271;
          </span>

          <div className="rule-card__title-group">
            <span className="rule-card__name">{rule.name}</span>
            <span className="rule-card__priority">Priority {rule.priority}</span>
          </div>

          <label className="rule-card__toggle" title="Toggle active">
            <input
              type="checkbox"
              checked={rule.is_active}
              onChange={(e) => onToggleActive(rule.id, e.target.checked)}
              aria-label={`Toggle ${rule.name} active`}
            />
            <span className="rule-card__toggle-label">
              {rule.is_active ? "Active" : "Inactive"}
            </span>
          </label>
        </div>

        <div className="rule-card__body">
          {/* Conditions chips */}
          {rule.conditions.length > 0 && (
            <div className="rule-card__conditions">
              <span className="rule-card__section-label">Conditions:</span>
              {visibleConditions.map((cond, i) => (
                <span
                  key={i}
                  className="rule-card__chip"
                  title={`${cond.field} ${cond.operator} ${Array.isArray(cond.value) ? cond.value.join(", ") : cond.value}`}
                >
                  {cond.field} {cond.operator}{" "}
                  {Array.isArray(cond.value) ? cond.value.join(", ") : cond.value}
                </span>
              ))}
              {extraConditions > 0 && (
                <span className="rule-card__chip rule-card__chip--more">
                  +{extraConditions} more
                </span>
              )}
            </div>
          )}

          {/* Actions list */}
          {rule.actions.length > 0 && (
            <div className="rule-card__actions-list">
              <span className="rule-card__section-label">Actions:</span>
              {rule.actions.map((action, i) => (
                <span key={i} className="rule-card__action-item">
                  {action.channel}: {action.destination}
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="rule-card__footer">
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => onEdit(rule)}
            aria-label={`Edit ${rule.name}`}
          >
            Edit
          </button>
          {onTest && (
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => onTest(rule)}
              aria-label={`Test ${rule.name}`}
            >
              Test
            </button>
          )}
          <button
            type="button"
            className="btn btn--danger btn--sm"
            onClick={() => setConfirmDelete(true)}
            aria-label={`Delete ${rule.name}`}
          >
            Delete
          </button>
        </div>
      </div>

      {confirmDelete && (
        <ConfirmDeleteModal
          ruleName={rule.name}
          onConfirm={() => {
            onDelete(rule.id);
            setConfirmDelete(false);
          }}
          onCancel={() => setConfirmDelete(false)}
        />
      )}
    </>
  );
}
