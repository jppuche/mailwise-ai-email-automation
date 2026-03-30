// src/components/FewShotEditor.tsx
// Form for creating/editing few-shot classification examples.
// In create mode: example prop is undefined.
// In edit mode: example prop pre-populates all fields.
//
// Action/type slugs come from loaded categories, not hardcoded arrays.
// Zero hardcoded colors — all via CSS custom properties.
import { useState } from "react";
import type {
  FewShotExampleResponse,
  FewShotExampleCreate,
  ActionCategoryResponse,
  TypeCategoryResponse,
} from "@/types/generated/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

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
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">
          {isEditMode ? "Edit Example" : "New Example"}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={handleSubmit} noValidate>
          {/* Email snippet */}
          <div className="space-y-1.5">
            <Label htmlFor="fse-snippet">
              Email Snippet{" "}
              <span className="text-destructive" aria-hidden="true">*</span>
            </Label>
            <Textarea
              id="fse-snippet"
              rows={4}
              placeholder="Paste a representative email excerpt..."
              value={emailSnippet}
              onChange={(e) => setEmailSnippet(e.target.value)}
              required
              disabled={isSaving}
            />
          </div>

          {/* Action select — populated from API categories */}
          <div className="space-y-1.5">
            <Label htmlFor="fse-action">
              Action{" "}
              <span className="text-destructive" aria-hidden="true">*</span>
            </Label>
            <select
              id="fse-action"
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
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

          {/* Type select — populated from API categories */}
          <div className="space-y-1.5">
            <Label htmlFor="fse-type">
              Type{" "}
              <span className="text-destructive" aria-hidden="true">*</span>
            </Label>
            <select
              id="fse-type"
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
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
          <div className="space-y-1.5">
            <Label htmlFor="fse-rationale">Rationale</Label>
            <Textarea
              id="fse-rationale"
              rows={2}
              placeholder="Why does this example illustrate the action/type? (optional)"
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
              disabled={isSaving}
            />
          </div>

          {/* Form actions */}
          <div className="flex gap-2 pt-1">
            <Button
              type="submit"
              disabled={isSaving || !isValid}
            >
              {isSaving ? "Saving..." : isEditMode ? "Save Changes" : "Create Example"}
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={isSaving}
              onClick={onCancel}
            >
              Cancel
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
