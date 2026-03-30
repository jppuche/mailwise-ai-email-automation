// src/pages/ClassificationConfigPage.tsx
// Route: /classification (admin only)
// Three sections: Action Categories, Type Categories, Few-Shot Examples.
// LLM Config section: READ-ONLY (no PUT /classification-config endpoint — handoff delta #6).
import { useState } from "react";
import { Plus, Loader2, ChevronDown, ChevronUp, FlaskConical } from "lucide-react";
import {
  useActionCategories,
  useTypeCategories,
  useCategoryMutations,
  useFewShotExamples,
  useFewShotMutations,
  useLLMConfig,
  useTestLLM,
} from "@/hooks/useCategories";
import { CategoryList } from "@/components/CategoryList";
import { FewShotEditor } from "@/components/FewShotEditor";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type {
  FewShotExampleResponse,
  ActionCategoryResponse,
  TypeCategoryResponse,
  ActionCategoryCreate,
  TypeCategoryCreate,
  FewShotExampleCreate,
} from "@/types/generated/api";

// ─────────────────────────────────────────────────────────────────────────────
// Category add form (shared for action/type categories)
// ─────────────────────────────────────────────────────────────────────────────

interface CategoryAddFormProps {
  layer: "actions" | "types";
  onSave: (data: ActionCategoryCreate | TypeCategoryCreate) => void;
  onCancel: () => void;
  isSaving: boolean;
}

function CategoryAddForm({ layer, onSave, onCancel, isSaving }: CategoryAddFormProps) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");

  const isValid = name.trim().length > 0 && slug.trim().length > 0;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!isValid) return;
    onSave({
      name: name.trim(),
      slug: slug.trim(),
      description: description.trim() || undefined,
    });
  }

  return (
    <form className="mt-4 space-y-4" onSubmit={handleSubmit} noValidate>
      <p className="text-base font-medium">
        New {layer === "actions" ? "Action" : "Type"} Category
      </p>
      <div className="space-y-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`cat-name-${layer}`}>
            Name <span aria-hidden="true">*</span>
          </Label>
          <Input
            id={`cat-name-${layer}`}
            type="text"
            placeholder="e.g. Respond"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            disabled={isSaving}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`cat-slug-${layer}`}>
            Slug <span aria-hidden="true">*</span>
          </Label>
          <Input
            id={`cat-slug-${layer}`}
            type="text"
            placeholder="e.g. respond"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            required
            disabled={isSaving}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`cat-desc-${layer}`}>Description</Label>
          <Input
            id={`cat-desc-${layer}`}
            type="text"
            placeholder="Optional description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={isSaving}
          />
        </div>
      </div>
      <div className="flex gap-2">
        <Button type="submit" disabled={isSaving || !isValid}>
          {isSaving ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Saving...
            </>
          ) : (
            "Create"
          )}
        </Button>
        <Button type="button" variant="secondary" onClick={onCancel} disabled={isSaving}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Category edit form (inline)
// ─────────────────────────────────────────────────────────────────────────────

interface CategoryEditFormProps {
  category: ActionCategoryResponse | TypeCategoryResponse;
  isPending: boolean;
  onSave: (data: { name?: string; description?: string }) => void;
  onCancel: () => void;
}

function CategoryEditForm({ category, isPending, onSave, onCancel }: CategoryEditFormProps) {
  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    onSave({
      name: (fd.get("name") as string).trim() || undefined,
      description: (fd.get("description") as string).trim() || undefined,
    });
  }

  return (
    <form className="mt-4 space-y-4" onSubmit={handleSubmit}>
      <p className="text-base font-medium">Edit: {category.name}</p>
      <div className="space-y-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`edit-cat-name-${category.id}`}>Name</Label>
          <Input
            id={`edit-cat-name-${category.id}`}
            name="name"
            type="text"
            defaultValue={category.name}
            disabled={isPending}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`edit-cat-desc-${category.id}`}>Description</Label>
          <Input
            id={`edit-cat-desc-${category.id}`}
            name="description"
            type="text"
            defaultValue={category.description}
            disabled={isPending}
          />
        </div>
      </div>
      <div className="flex gap-2">
        <Button type="submit" disabled={isPending}>
          {isPending ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Saving...
            </>
          ) : (
            "Save"
          )}
        </Button>
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// LLM Config section (read-only)
// ─────────────────────────────────────────────────────────────────────────────

function LLMConfigSection() {
  const { data: config, isLoading, error } = useLLMConfig();
  const testLLM = useTestLLM();

  if (isLoading) {
    return <Skeleton className="h-20 w-full" />;
  }

  if (error) {
    return (
      <Alert variant="destructive" role="alert">
        <AlertDescription>Failed to load LLM config: {error.message}</AlertDescription>
      </Alert>
    );
  }

  if (!config) return null;

  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-3 text-sm">
        <dt className="text-muted-foreground">Classify Model</dt>
        <dd className="font-mono">{config.classify_model}</dd>

        <dt className="text-muted-foreground">Draft Model</dt>
        <dd className="font-mono">{config.draft_model}</dd>

        <dt className="text-muted-foreground">Fallback Model</dt>
        <dd className="font-mono">{config.fallback_model}</dd>

        <dt className="text-muted-foreground">Classification Temperature</dt>
        <dd>{config.temperature_classify}</dd>

        <dt className="text-muted-foreground">Draft Temperature</dt>
        <dd>{config.temperature_draft}</dd>

        <dt className="text-muted-foreground">Timeout (s)</dt>
        <dd>{config.timeout_seconds}</dd>

        <dt className="text-muted-foreground">OpenAI API Key</dt>
        <dd>
          {config.openai_api_key_configured ? (
            <Badge variant="outline" className="text-success border-success">
              Configured
            </Badge>
          ) : (
            <Badge variant="outline" className="text-destructive border-destructive">
              Not configured
            </Badge>
          )}
        </dd>

        <dt className="text-muted-foreground">Anthropic API Key</dt>
        <dd>
          {config.anthropic_api_key_configured ? (
            <Badge variant="outline" className="text-success border-success">
              Configured
            </Badge>
          ) : (
            <Badge variant="outline" className="text-destructive border-destructive">
              Not configured
            </Badge>
          )}
        </dd>

        <dt className="text-muted-foreground">Base URL</dt>
        <dd className="font-mono">{config.base_url}</dd>
      </dl>

      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={testLLM.isPending}
          onClick={() => testLLM.mutate()}
        >
          {testLLM.isPending ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Testing...
            </>
          ) : (
            <>
              <FlaskConical className="mr-2 h-4 w-4" />
              Test Connection
            </>
          )}
        </Button>

        {testLLM.data && (
          <Alert
            variant={testLLM.data.success ? "default" : "destructive"}
            className="flex-1"
            role="status"
          >
            <AlertDescription>
              {testLLM.data.success ? (
                <>
                  Connection OK
                  {testLLM.data.latency_ms !== null && ` (${testLLM.data.latency_ms}ms)`}
                </>
              ) : (
                <>Connection failed: {testLLM.data.error_detail ?? "unknown error"}</>
              )}
            </AlertDescription>
          </Alert>
        )}

        {testLLM.error && (
          <Alert variant="destructive" className="flex-1" role="alert">
            <AlertDescription>Test error: {testLLM.error.message}</AlertDescription>
          </Alert>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page component
// ─────────────────────────────────────────────────────────────────────────────

export default function ClassificationConfigPage() {
  // Action categories
  const { data: actionCategories, isLoading: actionsLoading, error: actionsError } =
    useActionCategories();
  const actionMutations = useCategoryMutations("actions");
  const [showAddAction, setShowAddAction] = useState(false);
  const [editingAction, setEditingAction] = useState<ActionCategoryResponse | null>(null);

  // Type categories
  const { data: typeCategories, isLoading: typesLoading, error: typesError } =
    useTypeCategories();
  const typeMutations = useCategoryMutations("types");
  const [showAddType, setShowAddType] = useState(false);
  const [editingType, setEditingType] = useState<TypeCategoryResponse | null>(null);

  // Few-shot examples
  const { data: examples, isLoading: examplesLoading, error: examplesError } =
    useFewShotExamples();
  const fewShotMutations = useFewShotMutations();
  const [editingExample, setEditingExample] = useState<FewShotExampleResponse | null>(null);
  const [showAddExample, setShowAddExample] = useState(false);

  // LLM config collapsible
  const [llmConfigOpen, setLlmConfigOpen] = useState(false);

  // ── Action category callbacks ──

  function handleActionReorder(orderedIds: string[]) {
    actionMutations.reorder.mutate({ ordered_ids: orderedIds });
  }

  function handleActionDelete(id: string) {
    actionMutations.remove.mutate(id);
  }

  function handleActionToggleActive(id: string, isActive: boolean) {
    actionMutations.update.mutate({ id, body: { is_active: isActive } });
  }

  function handleActionEdit(category: ActionCategoryResponse | TypeCategoryResponse) {
    setEditingAction(category as ActionCategoryResponse);
    setShowAddAction(false);
  }

  function handleActionSaveCreate(data: ActionCategoryCreate | TypeCategoryCreate) {
    actionMutations.create.mutate(data as ActionCategoryCreate, {
      onSuccess: () => setShowAddAction(false),
    });
  }

  // ── Type category callbacks ──

  function handleTypeReorder(orderedIds: string[]) {
    typeMutations.reorder.mutate({ ordered_ids: orderedIds });
  }

  function handleTypeDelete(id: string) {
    typeMutations.remove.mutate(id);
  }

  function handleTypeToggleActive(id: string, isActive: boolean) {
    typeMutations.update.mutate({ id, body: { is_active: isActive } });
  }

  function handleTypeEdit(category: ActionCategoryResponse | TypeCategoryResponse) {
    setEditingType(category as TypeCategoryResponse);
    setShowAddType(false);
  }

  function handleTypeSaveCreate(data: ActionCategoryCreate | TypeCategoryCreate) {
    typeMutations.create.mutate(data as TypeCategoryCreate, {
      onSuccess: () => setShowAddType(false),
    });
  }

  // ── Few-shot callbacks ──

  function handleFewShotSave(data: FewShotExampleCreate) {
    if (editingExample) {
      fewShotMutations.update.mutate(
        { id: editingExample.id, body: data },
        { onSuccess: () => setEditingExample(null) },
      );
    } else {
      fewShotMutations.create.mutate(data, {
        onSuccess: () => setShowAddExample(false),
      });
    }
  }

  function handleFewShotDelete(id: string) {
    fewShotMutations.remove.mutate(id);
  }

  const isFewShotSaving =
    fewShotMutations.create.isPending || fewShotMutations.update.isPending;

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-300 fill-mode-both">
      <h1 className="text-2xl font-semibold tracking-tight">Classification Config</h1>

      {/* ── Section 1: Action Categories ── */}
      <Card aria-labelledby="section-action-categories">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <h2 className="text-lg font-medium" id="section-action-categories">
            Action Categories
          </h2>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              setShowAddAction((v) => !v);
              setEditingAction(null);
            }}
          >
            {showAddAction ? (
              "Cancel"
            ) : (
              <>
                <Plus className="mr-2 h-4 w-4" />
                Add Category
              </>
            )}
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {actionsError && (
            <Alert variant="destructive" role="alert">
              <AlertDescription>
                Failed to load categories: {actionsError.message}
              </AlertDescription>
            </Alert>
          )}

          {actionsLoading && <Skeleton className="h-20 w-full" />}

          {showAddAction && (
            <CategoryAddForm
              layer="actions"
              onSave={handleActionSaveCreate}
              onCancel={() => setShowAddAction(false)}
              isSaving={actionMutations.create.isPending}
            />
          )}

          {editingAction && (
            <CategoryEditForm
              category={editingAction}
              isPending={actionMutations.update.isPending}
              onSave={(data) =>
                actionMutations.update.mutate(
                  { id: editingAction.id, body: data },
                  { onSuccess: () => setEditingAction(null) },
                )
              }
              onCancel={() => setEditingAction(null)}
            />
          )}

          {!actionsLoading && (
            <CategoryList
              categories={actionCategories ?? []}
              onReorder={handleActionReorder}
              onEdit={handleActionEdit}
              onDelete={handleActionDelete}
              onToggleActive={handleActionToggleActive}
            />
          )}
        </CardContent>
      </Card>

      {/* ── Section 2: Type Categories ── */}
      <Card aria-labelledby="section-type-categories">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <h2 className="text-lg font-medium" id="section-type-categories">
            Type Categories
          </h2>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              setShowAddType((v) => !v);
              setEditingType(null);
            }}
          >
            {showAddType ? (
              "Cancel"
            ) : (
              <>
                <Plus className="mr-2 h-4 w-4" />
                Add Category
              </>
            )}
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {typesError && (
            <Alert variant="destructive" role="alert">
              <AlertDescription>
                Failed to load categories: {typesError.message}
              </AlertDescription>
            </Alert>
          )}

          {typesLoading && <Skeleton className="h-20 w-full" />}

          {showAddType && (
            <CategoryAddForm
              layer="types"
              onSave={handleTypeSaveCreate}
              onCancel={() => setShowAddType(false)}
              isSaving={typeMutations.create.isPending}
            />
          )}

          {editingType && (
            <CategoryEditForm
              category={editingType}
              isPending={typeMutations.update.isPending}
              onSave={(data) =>
                typeMutations.update.mutate(
                  { id: editingType.id, body: data },
                  { onSuccess: () => setEditingType(null) },
                )
              }
              onCancel={() => setEditingType(null)}
            />
          )}

          {!typesLoading && (
            <CategoryList
              categories={typeCategories ?? []}
              onReorder={handleTypeReorder}
              onEdit={handleTypeEdit}
              onDelete={handleTypeDelete}
              onToggleActive={handleTypeToggleActive}
            />
          )}
        </CardContent>
      </Card>

      {/* ── Section 3: Few-Shot Examples ── */}
      <Card aria-labelledby="section-few-shot">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <h2 className="text-lg font-medium" id="section-few-shot">
            Few-Shot Examples
          </h2>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              setShowAddExample((v) => !v);
              setEditingExample(null);
            }}
          >
            {showAddExample ? (
              "Cancel"
            ) : (
              <>
                <Plus className="mr-2 h-4 w-4" />
                Add Example
              </>
            )}
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {examplesError && (
            <Alert variant="destructive" role="alert">
              <AlertDescription>
                Failed to load examples: {examplesError.message}
              </AlertDescription>
            </Alert>
          )}

          {examplesLoading && <Skeleton className="h-20 w-full" />}

          {showAddExample && !editingExample && (
            <FewShotEditor
              actionCategories={actionCategories ?? []}
              typeCategories={typeCategories ?? []}
              onSave={handleFewShotSave}
              onCancel={() => setShowAddExample(false)}
              isSaving={isFewShotSaving}
            />
          )}

          {editingExample && (
            <FewShotEditor
              example={editingExample}
              actionCategories={actionCategories ?? []}
              typeCategories={typeCategories ?? []}
              onSave={handleFewShotSave}
              onCancel={() => setEditingExample(null)}
              isSaving={isFewShotSaving}
            />
          )}

          {!examplesLoading && (
            <ul className="space-y-3 p-0 m-0 list-none">
              {(examples ?? []).length === 0 && (
                <li className="text-sm text-muted-foreground py-4 text-center">
                  No examples yet.
                </li>
              )}
              {(examples ?? []).map((ex) => (
                <li key={ex.id}>
                  <Card className={cn(!ex.is_active && "opacity-60")}>
                    <CardContent className="pt-4 space-y-3">
                      <pre className="bg-muted rounded-md p-3 text-xs font-mono whitespace-pre-wrap break-all">
                        {ex.email_snippet}
                      </pre>
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="outline">{ex.action_slug}</Badge>
                        <Badge variant="outline">{ex.type_slug}</Badge>
                        {ex.rationale && (
                          <span className="text-xs text-muted-foreground">{ex.rationale}</span>
                        )}
                        {ex.is_active ? (
                          <Badge className="bg-success hover:bg-success/90 text-success-foreground">
                            Active
                          </Badge>
                        ) : (
                          <Badge variant="secondary">Inactive</Badge>
                        )}
                      </div>
                      <div className="flex gap-2">
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setEditingExample(ex);
                            setShowAddExample(false);
                          }}
                        >
                          Edit
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="text-destructive hover:text-destructive hover:bg-destructive/10"
                          disabled={fewShotMutations.remove.isPending}
                          onClick={() => handleFewShotDelete(ex.id)}
                        >
                          Delete
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* ── Section 4: LLM Config (collapsible, read-only) ── */}
      <Card aria-labelledby="section-llm-config">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <h2 className="text-lg font-medium" id="section-llm-config">
            LLM Configuration
          </h2>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-expanded={llmConfigOpen}
            onClick={() => setLlmConfigOpen((v) => !v)}
          >
            {llmConfigOpen ? (
              <>
                <ChevronUp className="mr-1 h-4 w-4" />
                Hide
              </>
            ) : (
              <>
                <ChevronDown className="mr-1 h-4 w-4" />
                Show
              </>
            )}
          </Button>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-4">
            Read-only. Configuration is set via environment variables and cannot be edited here.
          </p>
          {llmConfigOpen && <LLMConfigSection />}
        </CardContent>
      </Card>
    </div>
  );
}
