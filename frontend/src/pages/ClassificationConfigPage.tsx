// src/pages/ClassificationConfigPage.tsx
// Route: /classification (admin only)
// Three sections: Action Categories, Type Categories, Few-Shot Examples.
// LLM Config section: READ-ONLY (no PUT /classification-config endpoint — handoff delta #6).
// Zero hardcoded colors — all via CSS custom properties.
import { useState } from "react";
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
    <form className="category-add-form" onSubmit={handleSubmit} noValidate>
      <h4 className="category-add-form__title">
        New {layer === "actions" ? "Action" : "Type"} Category
      </h4>
      <div className="form-group">
        <label className="form-label" htmlFor={`cat-name-${layer}`}>
          Name <span aria-hidden="true">*</span>
        </label>
        <input
          id={`cat-name-${layer}`}
          type="text"
          className="form-input"
          placeholder="e.g. Respond"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          disabled={isSaving}
        />
      </div>
      <div className="form-group">
        <label className="form-label" htmlFor={`cat-slug-${layer}`}>
          Slug <span aria-hidden="true">*</span>
        </label>
        <input
          id={`cat-slug-${layer}`}
          type="text"
          className="form-input"
          placeholder="e.g. respond"
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
          required
          disabled={isSaving}
        />
      </div>
      <div className="form-group">
        <label className="form-label" htmlFor={`cat-desc-${layer}`}>
          Description
        </label>
        <input
          id={`cat-desc-${layer}`}
          type="text"
          className="form-input"
          placeholder="Optional description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          disabled={isSaving}
        />
      </div>
      <div className="category-add-form__actions">
        <button
          type="submit"
          className="btn btn--primary"
          disabled={isSaving || !isValid}
        >
          {isSaving ? "Saving..." : "Create"}
        </button>
        <button type="button" className="btn btn--secondary" onClick={onCancel} disabled={isSaving}>
          Cancel
        </button>
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
    return <div className="llm-config__loading">Loading LLM config...</div>;
  }

  if (error) {
    return (
      <div className="llm-config__error" role="alert">
        Failed to load LLM config: {error.message}
      </div>
    );
  }

  if (!config) return null;

  return (
    <div className="llm-config">
      <dl className="llm-config__dl">
        <div className="llm-config__row">
          <dt className="llm-config__dt">Classify Model</dt>
          <dd className="llm-config__dd llm-config__dd--mono">{config.classify_model}</dd>
        </div>
        <div className="llm-config__row">
          <dt className="llm-config__dt">Draft Model</dt>
          <dd className="llm-config__dd llm-config__dd--mono">{config.draft_model}</dd>
        </div>
        <div className="llm-config__row">
          <dt className="llm-config__dt">Fallback Model</dt>
          <dd className="llm-config__dd llm-config__dd--mono">{config.fallback_model}</dd>
        </div>
        <div className="llm-config__row">
          <dt className="llm-config__dt">Classification Temperature</dt>
          <dd className="llm-config__dd">{config.temperature_classify}</dd>
        </div>
        <div className="llm-config__row">
          <dt className="llm-config__dt">Draft Temperature</dt>
          <dd className="llm-config__dd">{config.temperature_draft}</dd>
        </div>
        <div className="llm-config__row">
          <dt className="llm-config__dt">Timeout (s)</dt>
          <dd className="llm-config__dd">{config.timeout_seconds}</dd>
        </div>
        <div className="llm-config__row">
          <dt className="llm-config__dt">OpenAI API Key</dt>
          <dd className="llm-config__dd">
            {config.openai_api_key_configured ? (
              <span className="llm-config__configured">Configured</span>
            ) : (
              <span className="llm-config__not-configured">Not configured</span>
            )}
          </dd>
        </div>
        <div className="llm-config__row">
          <dt className="llm-config__dt">Anthropic API Key</dt>
          <dd className="llm-config__dd">
            {config.anthropic_api_key_configured ? (
              <span className="llm-config__configured">Configured</span>
            ) : (
              <span className="llm-config__not-configured">Not configured</span>
            )}
          </dd>
        </div>
        <div className="llm-config__row">
          <dt className="llm-config__dt">Base URL</dt>
          <dd className="llm-config__dd llm-config__dd--mono">{config.base_url}</dd>
        </div>
      </dl>

      {/* Test connection */}
      <div className="llm-config__test">
        <button
          type="button"
          className="btn btn--secondary"
          disabled={testLLM.isPending}
          onClick={() => testLLM.mutate()}
        >
          {testLLM.isPending ? "Testing..." : "Test Connection"}
        </button>

        {testLLM.data && (
          <div
            className={`llm-config__test-result${testLLM.data.success ? " llm-config__test-result--success" : " llm-config__test-result--error"}`}
            role="status"
          >
            {testLLM.data.success ? (
              <>
                Connection OK
                {testLLM.data.latency_ms !== null && ` (${testLLM.data.latency_ms}ms)`}
              </>
            ) : (
              <>Connection failed: {testLLM.data.error_detail ?? "unknown error"}</>
            )}
          </div>
        )}

        {testLLM.error && (
          <div className="llm-config__test-result llm-config__test-result--error" role="alert">
            Test error: {testLLM.error.message}
          </div>
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
    <div className="classification-config-page">
      <h1 className="classification-config-page__title">Classification Config</h1>

      {/* ── Section 1: Action Categories ── */}
      <section
        className="config-section"
        aria-labelledby="section-action-categories"
      >
        <div className="config-section__header">
          <h2 className="config-section__title" id="section-action-categories">
            Action Categories
          </h2>
          <button
            type="button"
            className="btn btn--secondary"
            onClick={() => {
              setShowAddAction((v) => !v);
              setEditingAction(null);
            }}
          >
            {showAddAction ? "Cancel" : "Add Category"}
          </button>
        </div>

        {actionsError && (
          <div className="config-section__error" role="alert">
            Failed to load categories: {actionsError.message}
          </div>
        )}

        {actionsLoading && (
          <div className="config-section__loading">Loading...</div>
        )}

        {showAddAction && (
          <CategoryAddForm
            layer="actions"
            onSave={handleActionSaveCreate}
            onCancel={() => setShowAddAction(false)}
            isSaving={actionMutations.create.isPending}
          />
        )}

        {/* Inline edit form */}
        {editingAction && (
          <form
            className="category-edit-form"
            onSubmit={(e) => {
              e.preventDefault();
              const fd = new FormData(e.currentTarget);
              actionMutations.update.mutate(
                {
                  id: editingAction.id,
                  body: {
                    name: (fd.get("name") as string).trim() || undefined,
                    description: (fd.get("description") as string).trim() || undefined,
                  },
                },
                { onSuccess: () => setEditingAction(null) },
              );
            }}
          >
            <h4 className="category-edit-form__title">Edit: {editingAction.name}</h4>
            <div className="form-group">
              <label className="form-label" htmlFor="edit-action-name">
                Name
              </label>
              <input
                id="edit-action-name"
                name="name"
                type="text"
                className="form-input"
                defaultValue={editingAction.name}
                disabled={actionMutations.update.isPending}
              />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="edit-action-desc">
                Description
              </label>
              <input
                id="edit-action-desc"
                name="description"
                type="text"
                className="form-input"
                defaultValue={editingAction.description}
                disabled={actionMutations.update.isPending}
              />
            </div>
            <div className="category-edit-form__actions">
              <button
                type="submit"
                className="btn btn--primary"
                disabled={actionMutations.update.isPending}
              >
                {actionMutations.update.isPending ? "Saving..." : "Save"}
              </button>
              <button
                type="button"
                className="btn btn--secondary"
                onClick={() => setEditingAction(null)}
              >
                Cancel
              </button>
            </div>
          </form>
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
      </section>

      {/* ── Section 2: Type Categories ── */}
      <section
        className="config-section"
        aria-labelledby="section-type-categories"
      >
        <div className="config-section__header">
          <h2 className="config-section__title" id="section-type-categories">
            Type Categories
          </h2>
          <button
            type="button"
            className="btn btn--secondary"
            onClick={() => {
              setShowAddType((v) => !v);
              setEditingType(null);
            }}
          >
            {showAddType ? "Cancel" : "Add Category"}
          </button>
        </div>

        {typesError && (
          <div className="config-section__error" role="alert">
            Failed to load categories: {typesError.message}
          </div>
        )}

        {typesLoading && (
          <div className="config-section__loading">Loading...</div>
        )}

        {showAddType && (
          <CategoryAddForm
            layer="types"
            onSave={handleTypeSaveCreate}
            onCancel={() => setShowAddType(false)}
            isSaving={typeMutations.create.isPending}
          />
        )}

        {/* Inline edit form */}
        {editingType && (
          <form
            className="category-edit-form"
            onSubmit={(e) => {
              e.preventDefault();
              const fd = new FormData(e.currentTarget);
              typeMutations.update.mutate(
                {
                  id: editingType.id,
                  body: {
                    name: (fd.get("name") as string).trim() || undefined,
                    description: (fd.get("description") as string).trim() || undefined,
                  },
                },
                { onSuccess: () => setEditingType(null) },
              );
            }}
          >
            <h4 className="category-edit-form__title">Edit: {editingType.name}</h4>
            <div className="form-group">
              <label className="form-label" htmlFor="edit-type-name">
                Name
              </label>
              <input
                id="edit-type-name"
                name="name"
                type="text"
                className="form-input"
                defaultValue={editingType.name}
                disabled={typeMutations.update.isPending}
              />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="edit-type-desc">
                Description
              </label>
              <input
                id="edit-type-desc"
                name="description"
                type="text"
                className="form-input"
                defaultValue={editingType.description}
                disabled={typeMutations.update.isPending}
              />
            </div>
            <div className="category-edit-form__actions">
              <button
                type="submit"
                className="btn btn--primary"
                disabled={typeMutations.update.isPending}
              >
                {typeMutations.update.isPending ? "Saving..." : "Save"}
              </button>
              <button
                type="button"
                className="btn btn--secondary"
                onClick={() => setEditingType(null)}
              >
                Cancel
              </button>
            </div>
          </form>
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
      </section>

      {/* ── Section 3: Few-Shot Examples ── */}
      <section
        className="config-section"
        aria-labelledby="section-few-shot"
      >
        <div className="config-section__header">
          <h2 className="config-section__title" id="section-few-shot">
            Few-Shot Examples
          </h2>
          <button
            type="button"
            className="btn btn--secondary"
            onClick={() => {
              setShowAddExample((v) => !v);
              setEditingExample(null);
            }}
          >
            {showAddExample ? "Cancel" : "Add Example"}
          </button>
        </div>

        {examplesError && (
          <div className="config-section__error" role="alert">
            Failed to load examples: {examplesError.message}
          </div>
        )}

        {examplesLoading && (
          <div className="config-section__loading">Loading...</div>
        )}

        {/* Add form */}
        {showAddExample && !editingExample && (
          <FewShotEditor
            actionCategories={actionCategories ?? []}
            typeCategories={typeCategories ?? []}
            onSave={handleFewShotSave}
            onCancel={() => setShowAddExample(false)}
            isSaving={isFewShotSaving}
          />
        )}

        {/* Edit form */}
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

        {/* Examples list */}
        {!examplesLoading && (
          <ul className="few-shot-list">
            {(examples ?? []).length === 0 && (
              <li className="few-shot-list__empty">No examples yet.</li>
            )}
            {(examples ?? []).map((ex) => (
              <li key={ex.id} className={`few-shot-list__item${!ex.is_active ? " few-shot-list__item--inactive" : ""}`}>
                <div className="few-shot-list__item-content">
                  <pre className="few-shot-list__snippet">{ex.email_snippet}</pre>
                  <div className="few-shot-list__item-meta">
                    <span className="few-shot-list__slug">
                      {ex.action_slug} / {ex.type_slug}
                    </span>
                    {ex.rationale && (
                      <span className="few-shot-list__rationale">{ex.rationale}</span>
                    )}
                    <span
                      className={`few-shot-list__active-badge${!ex.is_active ? " few-shot-list__active-badge--inactive" : ""}`}
                    >
                      {ex.is_active ? "Active" : "Inactive"}
                    </span>
                  </div>
                </div>
                <div className="few-shot-list__item-actions">
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    onClick={() => {
                      setEditingExample(ex);
                      setShowAddExample(false);
                    }}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    className="btn btn--danger btn--sm"
                    disabled={fewShotMutations.remove.isPending}
                    onClick={() => handleFewShotDelete(ex.id)}
                  >
                    Delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ── Section 4: LLM Config (collapsible, read-only) ── */}
      <section className="config-section" aria-labelledby="section-llm-config">
        <div className="config-section__header">
          <h2 className="config-section__title" id="section-llm-config">
            LLM Configuration
          </h2>
          <button
            type="button"
            className="btn btn--ghost"
            aria-expanded={llmConfigOpen}
            onClick={() => setLlmConfigOpen((v) => !v)}
          >
            {llmConfigOpen ? "Hide" : "Show"}
          </button>
        </div>

        <p className="config-section__note">
          Read-only. Configuration is set via environment variables and cannot be edited here.
        </p>

        {llmConfigOpen && <LLMConfigSection />}
      </section>
    </div>
  );
}
