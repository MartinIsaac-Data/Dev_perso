import type {
  Deliverable,
  DeliverableInput,
  DeliverableType,
  DomainSummary,
  Graph,
  Phase,
  Profile,
  QuarterStatus,
  SkillEvidence,
  SkillLevel,
  SkillPosition,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

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

function query(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
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

  setTarget: ({ profile }: Scope, code: string, targetLevel: number) =>
    request<SkillPosition>(`/skills/${code}/target${query({ profile })}`, {
      method: "PUT",
      body: JSON.stringify({ target_level: targetLevel }),
    }),
};
