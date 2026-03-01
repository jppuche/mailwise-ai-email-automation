// src/components/FewShotEditor.tsx
// Form for creating/editing few-shot classification examples.
// In create mode: example prop is undefined.
// In edit mode: example prop pre-populates all fields.
//
// pre-mortem Cat 3: action/type slugs come from loaded categories, not hardcoded arrays.
// Zero hardcoded colors — all via CSS custom properties.
import { useState } from "react";
import type {
  FewShotExampleResponse,
  FewShotExampleCreate,
  ActionCategoryResponse,
  TypeCategoryResponse,
} from "@/types/generated/api";

interface FewShotEditorProps {
  example?: FewShotExampleResponse;
  actionCategories: ActionCategoryResponse[];
  typeCategories: TypeCategoryResponse[];
  onSave: (data: FewShotExampleCreate) => void;
  onCancel: () => void;
  isSaving: boolean;
}

export function FewShotEditor({
  example,
  actionCategories,
  typeCategories,
  onSave,
  onCancel,
  isSaving,
}: FewShotEditorProps) {
  const isEditMode = example !== undefined;

  const [emailSnippet, setEmailSnippet] = useState(example?.email_snippet ?? "");
  const [actionSlug, setActionSlug] = useState(example?.action_slug ?? "");
  const [typeSlug, setTypeSlug] = useState(example?.type_slug ?? "");
  const [rationale, setRationale] = useState(example?.rationale ?? "");

  const isValid =
    emailSnippet.trim().length > 0 &&
    actionSlug.trim().length > 0 &&
    typeSlug.trim().length > 0;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!isValid) return;

    const data: FewShotExampleCreate = {
      email_snippet: emailSnippet.trim(),
      action_slug: actionSlug.trim(),
      type_slug: typeSlug.trim(),
      ...(rationale.trim() ? { rationale: rationale.trim() } : {}),
    };

    onSave(data);
  }

  return (
    <form className="few-shot-editor" onSubmit={handleSubmit} noValidate>
      <h3 className="few-shot-editor__title">
        {isEditMode ? "Edit Example" : "New Example"}
      </h3>

      {/* Email snippet */}
      <div className="form-group">
        <label className="form-label" htmlFor="fse-snippet">
          Email Snippet <span className="form-required" aria-hidden="true">*</span>
        </label>
        <textarea
          id="fse-snippet"
          className="form-input"
          rows={4}
          placeholder="Paste a representative email excerpt..."
          value={emailSnippet}
          onChange={(e) => setEmailSnippet(e.target.value)}
          required
          disabled={isSaving}
        />
      </div>

      {/* Action select — populated from API categories (pre-mortem Cat 3) */}
      <div className="form-group">
        <label className="form-label" htmlFor="fse-action">
          Action <span className="form-required" aria-hidden="true">*</span>
        </label>
        <select
          id="fse-action"
          className="form-input"
          value={actionSlug}
          onChange={(e) => setActionSlug(e.target.value)}
          required
          disabled={isSaving}
        >
          <option value="">Select action...</option>
          {actionCategories.map((cat) => (
            <option key={cat.id} value={cat.slug}>
              {cat.name} ({cat.slug})
            </option>
          ))}
        </select>
      </div>

      {/* Type select — populated from API categories (pre-mortem Cat 3) */}
      <div className="form-group">
        <label className="form-label" htmlFor="fse-type">
          Type <span className="form-required" aria-hidden="true">*</span>
        </label>
        <select
          id="fse-type"
          className="form-input"
          value={typeSlug}
          onChange={(e) => setTypeSlug(e.target.value)}
          required
          disabled={isSaving}
        >
          <option value="">Select type...</option>
          {typeCategories.map((cat) => (
            <option key={cat.id} value={cat.slug}>
              {cat.name} ({cat.slug})
            </option>
          ))}
        </select>
      </div>

      {/* Rationale (optional) */}
      <div className="form-group">
        <label className="form-label" htmlFor="fse-rationale">
          Rationale
        </label>
        <textarea
          id="fse-rationale"
          className="form-input"
          rows={2}
          placeholder="Why does this example illustrate the action/type? (optional)"
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
          disabled={isSaving}
        />
      </div>

      {/* Form actions */}
      <div className="few-shot-editor__actions">
        <button
          type="submit"
          className="btn btn--primary"
          disabled={isSaving || !isValid}
        >
          {isSaving ? "Saving..." : isEditMode ? "Save Changes" : "Create Example"}
        </button>
        <button
          type="button"
          className="btn btn--secondary"
          disabled={isSaving}
          onClick={onCancel}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
