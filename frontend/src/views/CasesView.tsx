import { useState } from "react";

import { ApiError, IS_STATIC, api, type Scope } from "../api/client";
import type { CaseDetail, CauseNode, ReviewChallenge, RoiResult } from "../api/types";
import { Tornado } from "../components/Tornado";
import { Badge, Card, Empty, ErrorNote, Loading, Stat } from "../components/primitives";
import { useApi } from "../hooks/useApi";

type Scenario = "pessimistic" | "base" | "optimistic";
const SCENARIOS: Scenario[] = ["pessimistic", "base", "optimistic"];

/**
 * KPI values arrive as NUMERIC(20,6) strings, so a fill rate of 0.939 comes
 * back as "0.939000" and a monthly write-off as "37500.000000". Rendering the
 * raw string makes a target look like a measurement precise to six decimals,
 * which is exactly the false confidence this application argues against.
 * Ratios render as percentages; everything else drops the padding.
 */
function formatMeasure(value: string | null, unit: string | null): string {
  if (value === null) return "—";
  const numeric = Number(value);
  if (unit === "ratio") return `${(numeric * 100).toFixed(1)}%`;
  return numeric.toLocaleString("en-GB", { maximumFractionDigits: 2 });
}

function money(value: string | number | null, currency: string): string {
  if (value === null) return "—";
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(Number(value));
}

export function CasesView({ scope }: { scope: Scope }) {
  const [selected, setSelected] = useState<number | null>(null);
  const cases = useApi(() => api.cases(scope), [scope.profile]);

  if (cases.error) return <ErrorNote message={cases.error} onRetry={cases.reload} />;
  if (cases.loading) return <Loading what="business cases" />;

  const rows = cases.data ?? [];
  if (!rows.length) return <Empty>No business case yet.</Empty>;

  const openCase = selected ?? rows[0]?.id ?? null;

  return (
    <div className="space-y-4">
      {rows.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {rows.map((row) => (
            <button
              key={row.id}
              onClick={() => setSelected(row.id)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium ring-1 ring-inset ${
                openCase === row.id
                  ? "bg-slate-900 text-white ring-slate-900"
                  : "bg-white text-slate-600 ring-slate-200 hover:bg-slate-50"
              }`}
            >
              {row.title}
            </button>
          ))}
        </div>
      )}
      {openCase !== null && <CaseDetailView scope={scope} caseId={openCase} />}
    </div>
  );
}

function CaseDetailView({ scope, caseId }: { scope: Scope; caseId: number }) {
  const [scenario, setScenario] = useState<Scenario>("base");
  const detail = useApi(
    () => api.caseDetail(scope, caseId, scenario),
    [scope.profile, caseId, scenario],
  );
  const scenarios = useApi(() => api.roiScenarios(scope, caseId), [scope.profile, caseId]);
  const tornado = useApi(() => api.tornado(scope, caseId), [scope.profile, caseId]);
  const fragility = useApi(() => api.fragility(scope, caseId), [scope.profile, caseId]);

  const error = detail.error ?? scenarios.error;
  if (error) return <ErrorNote message={error} onRetry={detail.reload} />;
  if (detail.loading || !detail.data) return <Loading what="the case" />;

  const data = detail.data;
  const currency = data.currency;
  const reconciliation = data.cause_tree.reconciliation;
  const active = scenarios.data?.[scenario];

  return (
    <div className="space-y-4">
      <Card
        title={data.title}
        subtitle={`${data.industry ?? "—"} · opened ${data.opened_on} · ${data.status}`}
        right={
          <div className="flex gap-1">
            {SCENARIOS.map((option) => (
              <button
                key={option}
                onClick={() => setScenario(option)}
                className={`rounded px-2 py-1 text-[11px] font-medium ring-1 ring-inset ${
                  scenario === option
                    ? "bg-slate-900 text-white ring-slate-900"
                    : "bg-white text-slate-600 ring-slate-200 hover:bg-slate-50"
                }`}
              >
                {option}
              </button>
            ))}
          </div>
        }
      >
        <p className="text-sm leading-relaxed text-slate-700">{data.symptom}</p>
        {data.company_context && (
          <p className="mt-2 text-xs leading-relaxed text-slate-500">{data.company_context}</p>
        )}
      </Card>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label={`NPV (${scenario})`}
          value={active ? money(active.npv, currency) : "—"}
          tone={active ? (active.is_positive ? "good" : "bad") : "neutral"}
          hint={active ? `discounted at ${(Number(active.discount_rate) * 100).toFixed(0)}%` : ""}
        />
        <Stat
          label="Benefit / cost"
          value={active?.benefit_cost_ratio ?? "—"}
          tone={active && Number(active.benefit_cost_ratio) > 1 ? "good" : "bad"}
          hint="Present value, both sides"
        />
        <Stat
          label="Payback"
          value={active?.payback_years ? `${active.payback_years} yr` : "never"}
          tone={active?.payback_years ? "neutral" : "bad"}
          hint="Discounted, interpolated"
        />
        <Stat
          label="Unexplained"
          value={
            reconciliation.gap_ratio
              ? `${(Number(reconciliation.gap_ratio) * 100).toFixed(1)}%`
              : "—"
          }
          tone={
            reconciliation.gap_ratio && Math.abs(Number(reconciliation.gap_ratio)) > 0.05
              ? "warn"
              : "good"
          }
          hint="Claim minus bottom-up total"
        />
      </div>

      {fragility.data && (
        <div
          className={`rounded-lg border px-4 py-3 ${
            fragility.data.survives_pessimistic
              ? "border-emerald-200 bg-emerald-50"
              : "border-amber-300 bg-amber-50"
          }`}
        >
          <p className="text-sm font-medium text-slate-900">{fragility.data.headline}</p>
          <p className="mt-1 text-xs text-slate-600">
            Pessimistic {money(fragility.data.pessimistic_npv, currency)} · base{" "}
            {money(fragility.data.base_npv, currency)} · optimistic{" "}
            {money(fragility.data.optimistic_npv, currency)}
          </p>
          {fragility.data.unsourced.length > 0 && (
            <p className="mt-1 text-xs text-rose-800">
              Unsourced and load-bearing:{" "}
              {fragility.data.unsourced.map((row) => row.code).join(", ")}
            </p>
          )}
        </div>
      )}

      <Card
        title="Where the money is"
        subtitle={`Quantified bottom-up under the ${data.cause_tree.scenario} scenario`}
      >
        <div className="space-y-1">
          {data.cause_tree.roots.map((root) => (
            <TreeNode
              key={root.node_id}
              node={root}
              total={Number(data.cause_tree.total)}
              currency={currency}
            />
          ))}
        </div>

        <div
          className={`mt-4 rounded-md border px-3 py-2 ${
            reconciliation.gap_ratio && Math.abs(Number(reconciliation.gap_ratio)) > 0.05
              ? "border-amber-300 bg-amber-50"
              : "border-slate-200 bg-slate-50"
          }`}
        >
          <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
            <span className="text-slate-600">Bottom-up total</span>
            <span className="font-semibold tabular-nums text-slate-900">
              {money(reconciliation.bottom_up_total, currency)}
            </span>
          </div>
          <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
            <span className="text-slate-600">Claimed by the client</span>
            <span className="tabular-nums text-slate-900">
              {money(reconciliation.claimed_annual_loss, currency)}
            </span>
          </div>
          <p className="mt-1.5 text-xs leading-relaxed text-slate-700">
            {reconciliation.verdict}
          </p>
        </div>
      </Card>

      {active && <CashFlowTable result={active} currency={currency} />}

      <Card
        title="Sensitivity"
        subtitle="One assumption varied at a time across its own stated range"
      >
        {tornado.loading || !tornado.data || !fragility.data ? (
          <Loading what="the tornado" />
        ) : (
          <Tornado
            rows={tornado.data}
            baseNpv={Number(fragility.data.base_npv)}
            currency={currency}
          />
        )}
      </Card>

      <AssumptionsTable detail={data} />

      {data.reviews.map((review) => (
        <ReviewPanel
          key={review.id}
          review={review}
          currency={currency}
          scope={scope}
          caseId={caseId}
          onAnswered={() => detail.reload()}
        />
      ))}

      {data.solution && <SolutionPanel solution={data.solution} />}
    </div>
  );
}

function TreeNode({
  node,
  total,
  currency,
}: {
  node: CauseNode;
  total: number;
  currency: string;
}) {
  const share = total > 0 ? Number(node.value) / total : 0;
  return (
    <div style={{ marginLeft: node.depth * 16 }}>
      <div className="flex items-center gap-2 py-1">
        <span className="min-w-0 flex-1 truncate text-sm text-slate-800">{node.label}</span>
        <span className="h-1.5 w-24 shrink-0 rounded bg-slate-100">
          <span
            className={`block h-1.5 rounded ${node.is_leaf ? "bg-sky-500" : "bg-slate-400"}`}
            style={{ width: `${Math.min(100, share * 100)}%` }}
          />
        </span>
        <span className="w-28 shrink-0 text-right text-xs tabular-nums text-slate-700">
          {new Intl.NumberFormat("en-GB", {
            style: "currency",
            currency,
            maximumFractionDigits: 0,
          }).format(Number(node.value))}
        </span>
      </div>

      {node.drivers.length > 0 && (
        <p className="ml-1 text-[11px] text-slate-400">
          {node.drivers
            .map((driver) => `${driver.code} (${Number(driver.value).toLocaleString("en-GB")})`)
            .join(" × ")}
          {node.drivers.some((driver) => !driver.has_source) && (
            <span className="ml-1 text-rose-600">· unsourced driver</span>
          )}
        </p>
      )}

      {node.children.map((child) => (
        <TreeNode key={child.node_id} node={child} total={total} currency={currency} />
      ))}
    </div>
  );
}

function CashFlowTable({ result, currency }: { result: RoiResult; currency: string }) {
  let cumulative = 0;
  return (
    <Card
      title="Cash flow"
      subtitle={`${result.scenario} · year 0 is the investment year and is not discounted`}
    >
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
              <th className="py-1.5 pr-3 font-medium">Year</th>
              <th className="py-1.5 pr-3 text-right font-medium">Costs</th>
              <th className="py-1.5 pr-3 text-right font-medium">Benefits</th>
              <th className="py-1.5 pr-3 text-right font-medium">Net</th>
              <th className="py-1.5 text-right font-medium">Cumulative</th>
            </tr>
          </thead>
          <tbody>
            {result.flows.map((flow) => {
              cumulative += Number(flow.net);
              return (
                <tr key={flow.year_index} className="border-b border-slate-50">
                  <td className="py-1.5 pr-3 text-slate-600">Y{flow.year_index}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums text-rose-700">
                    {Number(flow.costs) ? money(flow.costs, currency) : "—"}
                  </td>
                  <td className="py-1.5 pr-3 text-right tabular-nums text-emerald-700">
                    {Number(flow.benefits) ? money(flow.benefits, currency) : "—"}
                  </td>
                  <td className="py-1.5 pr-3 text-right tabular-nums text-slate-800">
                    {money(flow.net, currency)}
                  </td>
                  <td
                    className={`py-1.5 text-right tabular-nums ${
                      cumulative >= 0 ? "text-emerald-700" : "text-slate-500"
                    }`}
                  >
                    {money(cumulative, currency)}
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="text-xs text-slate-500">
              <td className="pt-2">Present value</td>
              <td className="pt-2 text-right tabular-nums">
                {money(result.total_cost_pv, currency)}
              </td>
              <td className="pt-2 text-right tabular-nums">
                {money(result.total_benefit_pv, currency)}
              </td>
              <td className="pt-2 text-right font-semibold tabular-nums text-slate-900">
                {money(result.npv, currency)}
              </td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
    </Card>
  );
}

function AssumptionsTable({ detail }: { detail: CaseDetail }) {
  const audit = detail.audit;
  return (
    <Card
      title="Assumptions"
      subtitle={`${audit.total} in total · ${(Number(audit.sourced_ratio) * 100).toFixed(0)}% sourced`}
    >
      {(audit.unsourced.length > 0 || audit.unused.length > 0) && (
        <div className="mb-3 space-y-1 text-xs">
          {audit.unsourced.length > 0 && (
            <p className="text-rose-700">Unsourced: {audit.unsourced.join(", ")}</p>
          )}
          {audit.unused.length > 0 && (
            <p className="text-amber-700">
              Referenced by nothing: {audit.unused.join(", ")} — either a leftover, or a cost
              that was meant to be in the model.
            </p>
          )}
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
              <th className="py-1.5 pr-3 font-medium">Code</th>
              <th className="py-1.5 pr-3 text-right font-medium">Low</th>
              <th className="py-1.5 pr-3 text-right font-medium">Base</th>
              <th className="py-1.5 pr-3 text-right font-medium">High</th>
              <th className="py-1.5 pr-3 font-medium">Confidence</th>
              <th className="py-1.5 font-medium">Source</th>
            </tr>
          </thead>
          <tbody>
            {detail.assumptions.map((assumption) => (
              <tr key={assumption.id} className="border-b border-slate-50 align-top">
                <td className="py-1.5 pr-3 font-mono text-[11px] text-slate-700">
                  {assumption.code}
                  <span className="block font-sans text-[11px] text-slate-400">
                    {assumption.unit}
                  </span>
                </td>
                <td className="py-1.5 pr-3 text-right tabular-nums text-slate-500">
                  {assumption.low_value ? Number(assumption.low_value).toLocaleString("en-GB") : "—"}
                </td>
                <td className="py-1.5 pr-3 text-right font-medium tabular-nums text-slate-900">
                  {Number(assumption.base_value).toLocaleString("en-GB")}
                </td>
                <td className="py-1.5 pr-3 text-right tabular-nums text-slate-500">
                  {assumption.high_value
                    ? Number(assumption.high_value).toLocaleString("en-GB")
                    : "—"}
                </td>
                <td className="py-1.5 pr-3">
                  <Badge
                    tone={
                      assumption.confidence === "low"
                        ? "bad"
                        : assumption.confidence === "medium"
                          ? "warn"
                          : "good"
                    }
                  >
                    {assumption.confidence}
                  </Badge>
                </td>
                <td className="py-1.5 text-xs text-slate-500">
                  {assumption.source ?? (
                    <span className="text-rose-600">no source</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function ReviewPanel({
  review,
  currency,
  scope,
  caseId,
  onAnswered,
}: {
  review: CaseDetail["reviews"][number];
  currency: string;
  scope: Scope;
  caseId: number;
  onAnswered: () => void;
}) {
  const open = review.challenges.filter((c) => !c.resolved_on).length;
  return (
    <Card
      title={`Review board — ${review.reviewed_on}`}
      subtitle={`${open} of ${review.challenges.length} objections still open`}
      right={
        <span className="text-2xl font-semibold tabular-nums text-slate-900">
          {review.overall_score}
          <span className="text-sm font-normal text-slate-400">/10</span>
        </span>
      }
    >
      {review.verdict && (
        <p className="mb-3 text-sm leading-relaxed text-slate-700">{review.verdict}</p>
      )}

      <div className="mb-4 space-y-1">
        {review.scores.map((score) => (
          <div key={score.criterion_code} className="flex items-center gap-2">
            <span className="w-44 shrink-0 text-xs text-slate-600">{score.criterion_name}</span>
            <span className="h-1.5 flex-1 rounded bg-slate-100">
              <span
                className={`block h-1.5 rounded ${
                  Number(score.score) >= 7
                    ? "bg-emerald-500"
                    : Number(score.score) >= 5
                      ? "bg-amber-500"
                      : "bg-rose-500"
                }`}
                style={{ width: `${Number(score.score) * 10}%` }}
              />
            </span>
            <span className="w-8 text-right text-xs tabular-nums text-slate-700">
              {score.score}
            </span>
            <span className="w-10 text-right text-[11px] text-slate-400">
              ×{Number(score.weight).toFixed(2)}
            </span>
          </div>
        ))}
      </div>

      <div className="space-y-2">
        {review.challenges.map((challenge) => (
          <ChallengeCard
            key={challenge.id}
            challenge={challenge}
            scope={scope}
            caseId={caseId}
            onAnswered={onAnswered}
          />
        ))}
      </div>

      <p className="mt-3 text-[11px] text-slate-400">
        Scores are weighted by the stored rubric; amounts in {currency}.
      </p>
    </Card>
  );
}

function ChallengeCard({
  challenge,
  scope,
  caseId,
  onAnswered,
}: {
  challenge: ReviewChallenge;
  scope: Scope;
  caseId: number;
  onAnswered: () => void;
}) {
  const [answering, setAnswering] = useState(false);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);

  const severityTone =
    challenge.severity === "blocking" ? "bad" : challenge.severity === "major" ? "warn" : "neutral";

  async function submit() {
    try {
      await api.answerChallenge(scope, caseId, challenge.id, text);
      setAnswering(false);
      onAnswered();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause));
    }
  }

  return (
    <article
      className={`rounded-md border p-2.5 ${
        challenge.resolved_on ? "border-slate-200 bg-slate-50" : "border-slate-200"
      }`}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone="info">{challenge.persona.toUpperCase()}</Badge>
        <Badge tone={severityTone}>{challenge.severity}</Badge>
        {challenge.target_assumption_code && (
          <Badge title="This objection is pinned to a named assumption">
            {challenge.target_assumption_code}
          </Badge>
        )}
        {challenge.target_area && <Badge>{challenge.target_area}</Badge>}
        {challenge.resolved_on && <Badge tone="good">answered {challenge.resolved_on}</Badge>}
      </div>

      <p className="mt-1.5 text-sm leading-relaxed text-slate-700">{challenge.challenge}</p>

      {challenge.evidence_demanded && (
        <p className="mt-1 text-xs text-slate-500">
          <span className="font-medium">Evidence demanded:</span> {challenge.evidence_demanded}
        </p>
      )}

      {challenge.response ? (
        <p className="mt-1.5 rounded bg-emerald-50 px-2 py-1 text-xs text-emerald-900">
          {challenge.response}
        </p>
      ) : answering ? (
        <div className="mt-2 space-y-1.5">
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={2}
            placeholder="How was this answered?"
            className="w-full rounded border border-slate-200 px-2 py-1 text-xs outline-none focus:border-sky-400"
          />
          {error && <p className="text-xs text-rose-700">{error}</p>}
          <div className="flex gap-2">
            <button
              onClick={submit}
              disabled={!text.trim()}
              className="rounded bg-sky-700 px-2 py-1 text-xs font-medium text-white disabled:opacity-40"
            >
              Save
            </button>
            <button
              onClick={() => setAnswering(false)}
              className="rounded px-2 py-1 text-xs text-slate-500"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : IS_STATIC ? null : (
        <button
          onClick={() => setAnswering(true)}
          className="mt-1.5 text-xs text-sky-700 underline underline-offset-2"
        >
          Record an answer
        </button>
      )}
    </article>
  );
}

function SolutionPanel({ solution }: { solution: NonNullable<CaseDetail["solution"]> }) {
  const sections: [string, string | null][] = [
    ["Data required", solution.data_requirements],
    ["Architecture", solution.architecture],
    ["AI component", solution.ai_component],
    ["Automation", solution.automation_component],
    ["Process change", solution.process_change],
    ["Governance", solution.governance],
    ["Deployment", solution.deployment_plan],
    ["Key risks", solution.key_risks],
  ];

  return (
    <Card title="Proposed solution">
      <dl className="grid gap-3 md:grid-cols-2">
        {sections
          .filter(([, body]) => body)
          .map(([label, body]) => (
            <div key={label}>
              <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                {label}
              </dt>
              <dd className="mt-0.5 text-xs leading-relaxed text-slate-700">{body}</dd>
            </div>
          ))}
      </dl>

      {solution.kpis.length > 0 && (
        <div className="mt-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Steering indicators
          </h3>
          <table className="mt-1 w-full text-xs">
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500">
                <th className="py-1 pr-3 font-medium">KPI</th>
                <th className="py-1 pr-3 text-right font-medium">Baseline</th>
                <th className="py-1 pr-3 text-right font-medium">Target</th>
                <th className="py-1 font-medium">Frequency</th>
              </tr>
            </thead>
            <tbody>
              {solution.kpis.map((kpi) => (
                <tr key={kpi.name} className="border-b border-slate-50">
                  <td className="py-1 pr-3 text-slate-700">{kpi.name}</td>
                  <td className="py-1 pr-3 text-right tabular-nums text-slate-500">
                    {formatMeasure(kpi.baseline_value, kpi.unit)}
                  </td>
                  <td className="py-1 pr-3 text-right tabular-nums text-slate-900">
                    {formatMeasure(kpi.target_value, kpi.unit)}
                  </td>
                  <td className="py-1 text-slate-500">{kpi.measurement_frequency ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
