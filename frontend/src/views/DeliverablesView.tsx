import { useState } from "react";

import { ApiError, api, type Scope } from "../api/client";
import type { Deliverable } from "../api/types";
import { Badge, Card, Empty, ErrorNote, Loading } from "../components/primitives";
import { useApi } from "../hooks/useApi";

const STATUS_TONE = {
  published: "good",
  in_progress: "info",
  planned: "neutral",
  abandoned: "warn",
} as const;

export function DeliverablesView({ scope }: { scope: Scope }) {
  const [creating, setCreating] = useState(false);
  const deliverables = useApi(() => api.deliverables(scope), [scope.profile]);
  const types = useApi(() => api.deliverableTypes(), []);

  if (deliverables.error) {
    return <ErrorNote message={deliverables.error} onRetry={deliverables.reload} />;
  }

  const rows = deliverables.data ?? [];
  const published = rows.filter((d) => d.status === "published");
  const open = rows.filter((d) => d.status === "in_progress" || d.status === "planned");

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-600">
          {published.length} published · {open.length} open
        </p>
        <button
          onClick={() => setCreating((value) => !value)}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700"
        >
          {creating ? "Cancel" : "Record a deliverable"}
        </button>
      </div>

      {creating && (
        <NewDeliverableForm
          scope={scope}
          typeCodes={(types.data ?? []).map((t) => ({ code: t.code, name: t.name }))}
          onDone={() => {
            setCreating(false);
            deliverables.reload();
          }}
        />
      )}

      {deliverables.loading ? (
        <Loading what="deliverables" />
      ) : !rows.length ? (
        <Empty>Nothing recorded yet.</Empty>
      ) : (
        <div className="space-y-2">
          {rows.map((deliverable) => (
            <DeliverableRow key={deliverable.id} deliverable={deliverable} />
          ))}
        </div>
      )}
    </div>
  );
}

function DeliverableRow({ deliverable }: { deliverable: Deliverable }) {
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-medium text-slate-900">{deliverable.title}</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            {deliverable.type_name}
            {deliverable.published_on && ` · published ${deliverable.published_on}`}
            {!deliverable.published_on &&
              deliverable.started_on &&
              ` · started ${deliverable.started_on}`}
          </p>
        </div>
        <Badge tone={STATUS_TONE[deliverable.status]}>{deliverable.status.replace("_", " ")}</Badge>
      </div>

      {deliverable.summary && (
        <p className="mt-2 text-xs leading-relaxed text-slate-600">{deliverable.summary}</p>
      )}

      {deliverable.skills.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {deliverable.skills.map((link) => (
            <Badge
              key={link.skill_code}
              tone={link.contribution === 3 ? "info" : "neutral"}
              title={
                link.contribution === 3
                  ? "Central to this work"
                  : link.contribution === 2
                    ? "Meaningfully used"
                    : "Touched"
              }
            >
              {link.skill_name}
            </Badge>
          ))}
        </div>
      )}

      {deliverable.impacts.length > 0 && (
        <p className="mt-2 text-[11px] text-slate-500">
          {deliverable.impacts
            .map((impact) => `${impact.value} ${impact.unit ?? impact.metric_code}`)
            .join(" · ")}
        </p>
      )}

      {deliverable.artifact_url && (
        <a
          href={deliverable.artifact_url}
          target="_blank"
          rel="noreferrer"
          className="mt-2 inline-block text-xs text-sky-700 underline underline-offset-2"
        >
          {deliverable.artifact_url}
        </a>
      )}
    </article>
  );
}

function NewDeliverableForm({
  scope,
  typeCodes,
  onDone,
}: {
  scope: Scope;
  typeCodes: { code: string; name: string }[];
  onDone: () => void;
}) {
  const [title, setTitle] = useState("");
  const [typeCode, setTypeCode] = useState("project");
  const [status, setStatus] = useState("planned");
  const [publishedOn, setPublishedOn] = useState("");
  const [skills, setSkills] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.createDeliverable(scope, {
        title,
        type_code: typeCode,
        status,
        published_on: status === "published" ? publishedOn || null : null,
        skills: skills
          .split(",")
          .map((code) => code.trim())
          .filter(Boolean)
          .map((code) => ({ skill_code: code, contribution: 2 })),
      });
      onDone();
    } catch (cause) {
      // The API refuses a published deliverable with no date, and names any
      // skill code it does not recognise. Surfacing that message verbatim is
      // more useful than re-implementing the rules here.
      setError(cause instanceof ApiError ? cause.message : String(cause));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card title="New deliverable">
      <form onSubmit={submit} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Title">
            <input
              required
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              className="w-full rounded border border-slate-200 px-2 py-1.5 text-sm outline-none focus:border-sky-400"
            />
          </Field>
          <Field label="Type">
            <select
              value={typeCode}
              onChange={(event) => setTypeCode(event.target.value)}
              className="w-full rounded border border-slate-200 px-2 py-1.5 text-sm outline-none focus:border-sky-400"
            >
              {typeCodes.map((type) => (
                <option key={type.code} value={type.code}>
                  {type.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Status">
            <select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
              className="w-full rounded border border-slate-200 px-2 py-1.5 text-sm outline-none focus:border-sky-400"
            >
              <option value="planned">planned</option>
              <option value="in_progress">in progress</option>
              <option value="published">published</option>
              <option value="abandoned">abandoned</option>
            </select>
          </Field>
          <Field label="Published on" hint="Required once the status is published">
            <input
              type="date"
              value={publishedOn}
              onChange={(event) => setPublishedOn(event.target.value)}
              disabled={status !== "published"}
              className="w-full rounded border border-slate-200 px-2 py-1.5 text-sm outline-none focus:border-sky-400 disabled:bg-slate-50 disabled:text-slate-400"
            />
          </Field>
        </div>

        <Field label="Skills exercised" hint="Comma-separated codes, e.g. dax, dimensional_modelling">
          <input
            value={skills}
            onChange={(event) => setSkills(event.target.value)}
            className="w-full rounded border border-slate-200 px-2 py-1.5 font-mono text-xs outline-none focus:border-sky-400"
          />
        </Field>

        {error && <ErrorNote message={error} />}

        <button
          type="submit"
          disabled={saving}
          className="rounded-md bg-sky-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-800 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </form>
    </Card>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-slate-600">{label}</span>
      {hint && <span className="ml-1 text-[11px] text-slate-400">{hint}</span>}
      <div className="mt-1">{children}</div>
    </label>
  );
}
