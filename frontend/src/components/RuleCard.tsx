// src/components/RuleCard.tsx
// Routing rule card with toggle and action buttons.
// Supports drag handle for @dnd-kit/sortable (handle passed as children by parent).
import { useState } from "react";
import { GripVertical } from "lucide-react";
import type { RoutingRuleResponse } from "@/types/generated/api";
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

interface RuleCardProps {
  rule: RoutingRuleResponse;
  onEdit: (rule: RoutingRuleResponse) => void;
  onDelete: (id: string) => void;
  onToggleActive: (id: string, isActive: boolean) => void;
  onTest?: (rule: RoutingRuleResponse) => void;
  dragHandleProps?: React.HTMLAttributes<HTMLSpanElement>;
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
      <Card className={cn(!rule.is_active && "opacity-60")}>
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2">
            {/* Drag handle */}
            <span
              className="cursor-grab text-muted-foreground hover:text-foreground touch-none"
              title="Drag to reorder"
              aria-label="Drag to reorder"
              {...dragHandleProps}
            >
              <GripVertical className="h-4 w-4" />
            </span>

            {/* Title group */}
            <div className="flex-1 min-w-0">
              <span className="font-medium text-sm text-foreground truncate block">
                {rule.name}
              </span>
              <span className="text-xs text-muted-foreground">
                Priority {rule.priority}
              </span>
            </div>

            {/* Active toggle */}
            <div className="flex items-center gap-2 shrink-0">
              <span className="text-xs text-muted-foreground">
                {rule.is_active ? "Active" : "Inactive"}
              </span>
              <Switch
                checked={rule.is_active}
                onCheckedChange={(checked) => onToggleActive(rule.id, checked)}
                aria-label={`Toggle ${rule.name} active`}
              />
            </div>
          </div>
        </CardHeader>

        <CardContent className="py-2 space-y-2">
          {/* Conditions chips */}
          {rule.conditions.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-muted-foreground font-medium">Conditions:</span>
              {visibleConditions.map((cond, i) => (
                <Badge
                  key={i}
                  variant="secondary"
                  className="text-xs font-normal"
                  title={`${cond.field} ${cond.operator} ${Array.isArray(cond.value) ? cond.value.join(", ") : cond.value}`}
                >
                  {cond.field} {cond.operator}{" "}
                  {Array.isArray(cond.value) ? cond.value.join(", ") : cond.value}
                </Badge>
              ))}
              {extraConditions > 0 && (
                <Badge variant="outline" className="text-xs font-normal">
                  +{extraConditions} more
                </Badge>
              )}
            </div>
          )}

          {/* Actions list */}
          {rule.actions.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-muted-foreground font-medium">Actions:</span>
              {rule.actions.map((action, i) => (
                <Badge key={i} variant="outline" className="text-xs font-normal">
                  {action.channel}: {action.destination}
                </Badge>
              ))}
            </div>
          )}
        </CardContent>

        <CardFooter className="pt-2 gap-1">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onEdit(rule)}
            aria-label={`Edit ${rule.name}`}
          >
            Edit
          </Button>
          {onTest && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => onTest(rule)}
              aria-label={`Test ${rule.name}`}
            >
              Test
            </Button>
          )}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="text-destructive hover:text-destructive hover:bg-destructive/10"
            onClick={() => setConfirmDelete(true)}
            aria-label={`Delete ${rule.name}`}
          >
            Delete
          </Button>
        </CardFooter>
      </Card>

      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Rule</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete <strong>{rule.name}</strong>? This action cannot be
              undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="secondary"
              onClick={() => setConfirmDelete(false)}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                onDelete(rule.id);
                setConfirmDelete(false);
              }}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
