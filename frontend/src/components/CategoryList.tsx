// src/components/CategoryList.tsx
// Draggable list of action/type categories using @dnd-kit/sortable.
// Supports reorder (drag-to-sort), edit, delete (with confirm dialog), and active toggle.
//
// pre-mortem Cat 3: categories are loaded from API — never hardcoded.
// Zero hardcoded colors — all via CSS custom properties.
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
import type {
  ActionCategoryResponse,
  TypeCategoryResponse,
} from "@/types/generated/api";

type CategoryItem = ActionCategoryResponse | TypeCategoryResponse;

interface CategoryListProps {
  categories: CategoryItem[];
  onReorder: (orderedIds: string[]) => void;
  onEdit: (category: CategoryItem) => void;
  onDelete: (id: string) => void;
  onToggleActive: (id: string, isActive: boolean) => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// Confirm Delete Modal
// ─────────────────────────────────────────────────────────────────────────────

interface ConfirmDeleteModalProps {
  categoryName: string;
  onConfirm: () => void;
  onCancel: () => void;
}

function ConfirmDeleteModal({ categoryName, onConfirm, onCancel }: ConfirmDeleteModalProps) {
  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Confirm delete">
      <div className="modal">
        <h3 className="modal__title">Delete Category</h3>
        <p className="modal__body">
          Are you sure you want to delete <strong>{categoryName}</strong>? This action cannot be
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
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <li
      ref={setNodeRef}
      style={style}
      className={`category-item${isDragging ? " category-item--dragging" : ""}`}
    >
      {/* Drag handle — uses braille pattern dots as the standard dnd-kit handle icon */}
      <span
        className="category-item__drag-handle"
        {...attributes}
        {...listeners}
        aria-label="Drag to reorder"
        title="Drag to reorder"
      >
        &#10271;
      </span>

      <div className="category-item__info">
        <span className="category-item__name">{category.name}</span>
        <span className="category-item__slug">{category.slug}</span>
        {category.is_fallback && (
          <span className="category-item__fallback-badge" title="Fallback category">
            fallback
          </span>
        )}
      </div>

      <div className="category-item__actions">
        {/* Active toggle */}
        <label className="category-item__toggle" title="Toggle active">
          <input
            type="checkbox"
            checked={category.is_active}
            onChange={(e) => onToggleActive(category.id, e.target.checked)}
            aria-label={`Toggle ${category.name} active`}
          />
          <span className="category-item__toggle-label">
            {category.is_active ? "Active" : "Inactive"}
          </span>
        </label>

        {/* Edit button */}
        <button
          className="btn btn--ghost btn--sm"
          onClick={() => onEdit(category)}
          aria-label={`Edit ${category.name}`}
        >
          Edit
        </button>

        {/* Delete button */}
        <button
          className="btn btn--danger btn--sm"
          onClick={() => onDeleteRequest(category.id)}
          aria-label={`Delete ${category.name}`}
        >
          Delete
        </button>
      </div>
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
      <div className="category-list category-list--empty">
        <p className="category-list__empty-text">No categories defined yet.</p>
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
          <ul className="category-list">
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

      {deleteTarget && (
        <ConfirmDeleteModal
          categoryName={deleteTarget.name}
          onConfirm={handleDeleteConfirm}
          onCancel={handleDeleteCancel}
        />
      )}
    </>
  );
}
