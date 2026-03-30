// src/components/CategoryList.tsx
// Draggable list of action/type categories using @dnd-kit/sortable.
// Supports reorder (drag-to-sort), edit, delete (with confirm dialog), and active toggle.
//
// Categories are loaded from API — never hardcoded.
// Zero hardcoded colors — all via CSS custom properties.
import { useState } from "react";
import { GripVertical } from "lucide-react";
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
import type {
  ActionCategoryResponse,
  TypeCategoryResponse,
} from "@/types/generated/api";
import { Card } from "@/components/ui/card";
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

type CategoryItem = ActionCategoryResponse | TypeCategoryResponse;

interface CategoryListProps {
  categories: CategoryItem[];
  onReorder: (orderedIds: string[]) => void;
  onEdit: (category: CategoryItem) => void;
  onDelete: (id: string) => void;
  onToggleActive: (id: string, isActive: boolean) => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// SortableItem
// ─────────────────────────────────────────────────────────────────────────────

interface SortableItemProps {
  category: CategoryItem;
  onEdit: (category: CategoryItem) => void;
  onDeleteRequest: (id: string) => void;
  onToggleActive: (id: string, isActive: boolean) => void;
}

function SortableItem({ category, onEdit, onDeleteRequest, onToggleActive }: SortableItemProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: category.id,
  });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <li ref={setNodeRef} style={style} className="list-none">
      <Card
        className={cn(
          "flex items-center gap-3 px-3 py-2",
          isDragging && "shadow-lg opacity-90",
        )}
      >
        {/* Drag handle */}
        <span
          className="cursor-grab text-muted-foreground hover:text-foreground touch-none shrink-0"
          {...attributes}
          {...listeners}
          aria-label="Drag to reorder"
          title="Drag to reorder"
        >
          <GripVertical className="h-4 w-4" />
        </span>

        {/* Category info */}
        <div className="flex-1 min-w-0 flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-foreground truncate">
            {category.name}
          </span>
          <span className="text-xs text-muted-foreground font-mono">
            {category.slug}
          </span>
          {category.is_fallback && (
            <Badge variant="outline" className="text-xs">
              Fallback
            </Badge>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-muted-foreground">
              {category.is_active ? "Active" : "Inactive"}
            </span>
            <Switch
              checked={category.is_active}
              onCheckedChange={(checked) => onToggleActive(category.id, checked)}
              aria-label={`Toggle ${category.name} active`}
            />
          </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={() => onEdit(category)}
            aria-label={`Edit ${category.name}`}
          >
            Edit
          </Button>

          <Button
            variant="ghost"
            size="sm"
            className="text-destructive hover:text-destructive hover:bg-destructive/10"
            onClick={() => onDeleteRequest(category.id)}
            aria-label={`Delete ${category.name}`}
          >
            Delete
          </Button>
        </div>
      </Card>
    </li>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// CategoryList (main export)
// ─────────────────────────────────────────────────────────────────────────────

export function CategoryList({
  categories,
  onReorder,
  onEdit,
  onDelete,
  onToggleActive,
}: CategoryListProps) {
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);

  const deleteTarget = deleteTargetId
    ? categories.find((c) => c.id === deleteTargetId)
    : null;

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIndex = categories.findIndex((c) => c.id === active.id);
    const newIndex = categories.findIndex((c) => c.id === over.id);
    if (oldIndex === -1 || newIndex === -1) return;

    const reordered = arrayMove(categories, oldIndex, newIndex);
    onReorder(reordered.map((c) => c.id));
  }

  function handleDeleteRequest(id: string) {
    setDeleteTargetId(id);
  }

  function handleDeleteConfirm() {
    if (deleteTargetId) {
      onDelete(deleteTargetId);
      setDeleteTargetId(null);
    }
  }

  function handleDeleteCancel() {
    setDeleteTargetId(null);
  }

  if (categories.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">
        No categories defined yet.
      </div>
    );
  }

  return (
    <>
      <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext
          items={categories.map((c) => c.id)}
          strategy={verticalListSortingStrategy}
        >
          <ul className="space-y-2 p-0 m-0">
            {categories.map((category) => (
              <SortableItem
                key={category.id}
                category={category}
                onEdit={onEdit}
                onDeleteRequest={handleDeleteRequest}
                onToggleActive={onToggleActive}
              />
            ))}
          </ul>
        </SortableContext>
      </DndContext>

      <Dialog open={deleteTarget !== null && deleteTarget !== undefined} onOpenChange={(open) => { if (!open) handleDeleteCancel(); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Category</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete{" "}
              <strong>{deleteTarget?.name}</strong>? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="secondary" onClick={handleDeleteCancel}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDeleteConfirm}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
