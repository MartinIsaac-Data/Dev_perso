import type {
  Assumption,
  CaseDetail,
  CauseTree,
  CaseSummary,
  Deliverable,
  DeliverableInput,
  DeliverableType,
  DomainSummary,
  Graph,
  Phase,
  Profile,
  QuarterStatus,
  SkillEvidence,
  AgentRunRow,
  Fragility,
  MarketGapReport,
  PeriodicReview,
  Posting,
  ReviewChallenge,
  RoiResult,
  ScenarioComparison,
  SkillLevel,
  SkillPosition,
  TornadoRow,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

/**
 * Static mode: serve every read from a recorded snapshot instead of the API.
 *
 * The application has no authentication and is local-first by design, so the
 * public demonstration site publishes a recording of the demo profile rather
 * than the API itself. Writes are then impossible rather than merely hidden,
 * because there is nothing behind the interface to write to.
 */
export const IS_STATIC = import.meta.env.VITE_STATIC_SNAPSHOT === "true";

const READ_ONLY_MESSAGE =
  "This is a static demonstration. It is a recording of the demo profile, " +
  "with no backend behind it, so nothing can be changed here.";

interface Snapshot {
  generated_at: string;
  profile: string;
  read_only: boolean;
  responses: Record<string, unknown>;
}

let snapshotPromise: Promise<Snapshot> | null = null;

function loadSnapshot(): Promise<Snapshot> {
  if (snapshotPromise === null) {
    // BASE_URL rather than a leading slash, so the site works when served
    // from a sub-path as well as from a domain root.
    snapshotPromise = fetch(`${import.meta.env.BASE_URL}snapshot.json`).then((response) => {
      if (!response.ok) {
        throw new ApiError(response.status, "The demonstration snapshot could not be loaded.");
      }
      return response.json() as Promise<Snapshot>;
    });
  }
  return snapshotPromise;
}

export async function snapshotMeta(): Promise<{ generated_at: string; profile: string } | null> {
  if (!IS_STATIC) return null;
  const snapshot = await loadSnapshot();
  return { generated_at: snapshot.generated_at, profile: snapshot.profile };
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/**
 * FastAPI reports validation failures in two shapes: a plain string in
 * `detail` for errors we raise ourselves, and a list of objects for Pydantic
 * failures. Flattening both here means every caller can render `error.message`
 * and no view has to know the difference.
 */
function readDetail(body: unknown, fallback: string): string {
  if (typeof body !== "object" || body === null) return fallback;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item !== "object" || item === null) return null;
        const entry = item as { loc?: unknown[]; msg?: string };
        const field = Array.isArray(entry.loc) ? entry.loc.slice(1).join(".") : "";
        return field ? `${field}: ${entry.msg ?? ""}` : (entry.msg ?? null);
      })
      .filter(Boolean);
    if (parts.length) return parts.join("; ");
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (IS_STATIC) {
    const method = init?.method ?? "GET";
    if (method !== "GET") throw new ApiError(405, READ_ONLY_MESSAGE);

    const snapshot = await loadSnapshot();
    if (!(path in snapshot.responses)) {
      // Named explicitly rather than rendering an empty view: a missing key
      // means the generator and this client disagree about the canonical URL,
      // and that is a build problem, not a data problem.
      throw new ApiError(404, `Not recorded in the demonstration snapshot: ${path}`);
    }
    return snapshot.responses[path] as T;
  }

  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    // A network-level failure here almost always means the backend is not
    // running, so say that rather than surfacing "Failed to fetch".
    throw new ApiError(0, `Cannot reach the API at ${BASE}. Is the backend running?`);
  }

  if (response.status === 204) return undefined as T;

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(response.status, readDetail(body, `${response.status} on ${path}`));
  }
  return body as T;
}

/**
 * Build a query string with parameters in a stable, sorted order.
 *
 * The order matters because the static snapshot is keyed by the full URL, and
 * `?limit=8&profile=demo` and `?profile=demo&limit=8` are the same request.
 * Sorting here and sorting in `snapshot.py` is what keeps the two agreeing.
 */
function query(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  const entries = Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== "")
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  for (const [key, value] of entries) search.set(key, String(value));
  const rendered = search.toString();
  return rendered ? `?${rendered}` : "";
}

export interface Scope {
  profile: string;
  asOf?: string;
}

export const api = {
  profiles: () => request<Profile[]>("/profiles"),
  phases: () => request<Phase[]>("/phases"),
  levels: () => request<SkillLevel[]>("/skills/levels"),
  graph: () => request<Graph>("/skills/graph"),
  deliverableTypes: () => request<DeliverableType[]>("/deliverable-types"),
  targetRoles: () => request<{ code: string; name: string; description: string | null }[]>("/target-roles"),

  positions: ({ profile, asOf }: Scope) =>
    request<SkillPosition[]>(`/skills/positions${query({ profile, as_of: asOf })}`),

  criticalPath: ({ profile, asOf }: Scope, limit = 10) =>
    request<SkillPosition[]>(`/skills/critical-path${query({ profile, as_of: asOf, limit })}`),

  available: ({ profile, asOf }: Scope) =>
    request<SkillPosition[]>(`/skills/available${query({ profile, as_of: asOf })}`),

  decayed: ({ profile, asOf }: Scope) =>
    request<SkillPosition[]>(`/skills/decayed${query({ profile, as_of: asOf })}`),

  domainSummary: ({ profile, asOf }: Scope) =>
    request<DomainSummary[]>(`/skills/domains/summary${query({ profile, as_of: asOf })}`),

  deliverables: ({ profile }: Scope) =>
    request<Deliverable[]>(`/deliverables${query({ profile })}`),

  createDeliverable: ({ profile }: Scope, payload: DeliverableInput) =>
    request<Deliverable>(`/deliverables${query({ profile })}`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  quotaStatus: ({ profile, asOf }: Scope, quartersBack = 6) =>
    request<QuarterStatus[]>(
      `/quota-status${query({ profile, as_of: asOf, quarters_back: quartersBack })}`,
    ),

  evidenceCv: ({ profile }: Scope, minLevel = 2) =>
    request<SkillEvidence[]>(`/evidence-cv${query({ profile, min_level: minLevel })}`),

  cases: ({ profile }: Scope) => request<CaseSummary[]>(`/cases${query({ profile })}`),

  caseDetail: ({ profile }: Scope, id: number, scenario = "base") =>
    request<CaseDetail>(`/cases/${id}${query({ profile, scenario })}`),

  causeTree: ({ profile }: Scope, id: number, scenario = "base") =>
    request<CauseTree>(`/cases/${id}/cause-tree${query({ profile, scenario })}`),

  roiScenarios: ({ profile }: Scope, id: number, version?: number) =>
    request<ScenarioComparison>(`/cases/${id}/roi/scenarios${query({ profile, version })}`),

  roi: ({ profile }: Scope, id: number, scenario = "base", version?: number) =>
    request<RoiResult>(`/cases/${id}/roi${query({ profile, scenario, version })}`),

  tornado: ({ profile }: Scope, id: number, version?: number) =>
    request<TornadoRow[]>(`/cases/${id}/roi/tornado${query({ profile, version })}`),

  fragility: ({ profile }: Scope, id: number, version?: number) =>
    request<Fragility>(`/cases/${id}/roi/fragility${query({ profile, version })}`),

  answerChallenge: ({ profile }: Scope, caseId: number, challengeId: number, response: string) =>
    request<ReviewChallenge>(
      `/cases/${caseId}/challenges/${challengeId}/response${query({ profile })}`,
      { method: "POST", body: JSON.stringify({ response }) },
    ),

  updateAssumption: (
    { profile }: Scope,
    caseId: number,
    code: string,
    patch: Record<string, string | null>,
  ) =>
    request<Assumption>(`/cases/${caseId}/assumptions/${code}${query({ profile })}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  marketGaps: ({ profile }: Scope, targetRole?: string) =>
    request<MarketGapReport>(`/market/gaps${query({ profile, target_role: targetRole })}`),

  postings: () => request<Posting[]>("/postings"),

  agentRuns: () => request<AgentRunRow[]>("/agent-runs"),

  periodicReviews: ({ profile }: Scope) =>
    request<PeriodicReview[]>(`/periodic-reviews${query({ profile })}`),

  setTarget: ({ profile }: Scope, code: string, targetLevel: number) =>
    request<SkillPosition>(`/skills/${code}/target${query({ profile })}`, {
      method: "PUT",
      body: JSON.stringify({ target_level: targetLevel }),
    }),
};
