// src/pages/RoutingRulesPage.tsx
// Route: /routing (admin only)
// Drag-to-reorder routing rules with create/edit modal and dry-run test panel.
import { useState } from "react";
import {
  DndContext,
  closestCenter,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
  useSortable,
  arrayMove,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useRoutingRules, useRoutingRuleMutations } from "@/hooks/useRoutingRules";
import { RuleCard } from "@/components/RuleCard";
import { RuleBuilder } from "@/components/RuleBuilder";
import { RuleTestPanel } from "@/components/RuleTestPanel";
import type {
  RoutingRuleResponse,
  RoutingRuleCreate,
  RuleTestRequest,
  RuleTestResponse,
} from "@/types/generated/api";

// ─────────────────────────────────────────────────────────────────────────────
// SortableRuleCard
// ─────────────────────────────────────────────────────────────────────────────

interface SortableRuleCardProps {
  rule: RoutingRuleResponse;
  onEdit: (rule: RoutingRuleResponse) => void;
  onDelete: (id: string) => void;
  onToggleActive: (id: string, isActive: boolean) => void;
  onTest: (rule: RoutingRuleResponse) => void;
}

function SortableRuleCard({
  rule,
  onEdit,
  onDelete,
  onToggleActive,
  onTest,
}: SortableRuleCardProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: rule.id,
  });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <li ref={setNodeRef} style={style}>
      <RuleCard
        rule={rule}
        onEdit={onEdit}
        onDelete={onDelete}
        onToggleActive={onToggleActive}
        onTest={onTest}
        dragHandleProps={{ ...attributes, ...listeners } as React.HTMLAttributes<HTMLSpanElement>}
      />
    </li>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// RoutingRulesPage (main export)
// ─────────────────────────────────────────────────────────────────────────────

export default function RoutingRulesPage() {
  const { data: rules, isLoading, error } = useRoutingRules();
  const mutations = useRoutingRuleMutations();

  const [editingRule, setEditingRule] = useState<RoutingRuleResponse | null>(null);
  const [showBuilder, setShowBuilder] = useState(false);
  const [showTestPanel, setShowTestPanel] = useState(false);

  // ── Drag-to-reorder ──

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id || !rules) return;

    const oldIndex = rules.findIndex((r) => r.id === active.id);
    const newIndex = rules.findIndex((r) => r.id === over.id);
    if (oldIndex === -1 || newIndex === -1) return;

    const reordered = arrayMove(rules, oldIndex, newIndex);
    mutations.reorder.mutate(reordered.map((r) => r.id));
  }

  // ── Create/edit callbacks ──

  function handleOpenCreate() {
    setEditingRule(null);
    setShowBuilder(true);
  }

  function handleOpenEdit(rule: RoutingRuleResponse) {
    setEditingRule(rule);
    setShowBuilder(true);
  }

  function handleCloseBuilder() {
    setEditingRule(null);
    setShowBuilder(false);
  }

  async function handleRuleSubmit(data: RoutingRuleCreate) {
    if (editingRule) {
      await new Promise<void>((resolve, reject) => {
        mutations.update.mutate(
          { id: editingRule.id, body: data },
          {
            onSuccess: () => {
              handleCloseBuilder();
              resolve();
            },
            onError: (err) => reject(err),
          },
        );
      });
    } else {
      await new Promise<void>((resolve, reject) => {
        mutations.create.mutate(data, {
          onSuccess: () => {
            handleCloseBuilder();
            resolve();
          },
          onError: (err) => reject(err),
        });
      });
    }
  }

  // ── Delete ──

  function handleDelete(id: string) {
    mutations.remove.mutate(id);
  }

  // ── Toggle active ──

  function handleToggleActive(id: string, isActive: boolean) {
    mutations.toggleActive.mutate({ id, isActive });
  }

  // ── Test ──
  // Opens the test panel; the panel tests all rules globally (dry-run).
  // The SortableRuleCard passes the rule to the callback but we don't use it here.

  const handleOpenTest: (rule: RoutingRuleResponse) => void = () => {
    setShowTestPanel(true);
  };

  async function handleRunTest(request: RuleTestRequest): Promise<RuleTestResponse> {
    return new Promise<RuleTestResponse>((resolve, reject) => {
      mutations.test.mutate(request, {
        onSuccess: (result) => resolve(result),
        onError: (err) => reject(err),
      });
    });
  }

  const sortedRules = rules ?? [];

  return (
    <div className="routing-rules-page">
      <div className="routing-rules-page__header">
        <h1 className="routing-rules-page__title">Routing Rules</h1>
        <div className="routing-rules-page__actions">
          <button
            type="button"
            className="btn btn--secondary"
            onClick={() => setShowTestPanel((v) => !v)}
          >
            {showTestPanel ? "Hide Test Panel" : "Test Rules"}
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={handleOpenCreate}
          >
            New Rule
          </button>
        </div>
      </div>

      {error && (
        <div className="routing-rules-page__error" role="alert">
          Failed to load routing rules: {error.message}
        </div>
      )}

      {isLoading && (
        <div className="routing-rules-page__loading" aria-busy="true">
          Loading routing rules...
        </div>
      )}

      {showTestPanel && (
        <RuleTestPanel
          onTest={handleRunTest}
          onClose={() => setShowTestPanel(false)}
        />
      )}

      {!isLoading && sortedRules.length === 0 && !error && (
        <div className="routing-rules-page__empty">
          <p>No routing rules defined yet.</p>
          <button
            type="button"
            className="btn btn--primary"
            onClick={handleOpenCreate}
          >
            Create First Rule
          </button>
        </div>
      )}

      {sortedRules.length > 0 && (
        <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext
            items={sortedRules.map((r) => r.id)}
            strategy={verticalListSortingStrategy}
          >
            <ul className="routing-rules-page__list">
              {sortedRules.map((rule) => (
                <SortableRuleCard
                  key={rule.id}
                  rule={rule}
                  onEdit={handleOpenEdit}
                  onDelete={handleDelete}
                  onToggleActive={handleToggleActive}
                  onTest={handleOpenTest}
                />
              ))}
            </ul>
          </SortableContext>
        </DndContext>
      )}

      {showBuilder && (
        <RuleBuilder
          rule={editingRule ?? undefined}
          onSubmit={handleRuleSubmit}
          onClose={handleCloseBuilder}
        />
      )}
    </div>
  );
}
