// Mirrors the Pydantic response models in backend/app/schemas.
//
// Hand-written rather than generated from the OpenAPI schema, deliberately:
// at this size a generator adds a build step and a whole category of "the
// types are stale" confusion, and writing them by hand once forces reading
// what the API actually returns. If this grows past a few dozen types, that
// trade flips and openapi-typescript becomes the right answer.

export interface Profile {
  code: string;
  display_name: string;
  is_demo: boolean;
  based_in: string | null;
  currency: string;
}

export interface SkillLevel {
  level: number;
  code: string;
  name: string;
  definition: string;
  evidence_expectation: string | null;
}

export interface UnmetPrerequisite {
  skill_id: number;
  code: string;
  name: string;
  required_level: number;
  current_level: number;
}

export interface SkillPosition {
  skill_id: number;
  code: string;
  name: string;
  domain_code: string;
  domain_name: string;
  description: string | null;
  current_level: number;
  target_level: number;
  gap: number;
  tracked: boolean;
  last_practised_on: string | null;
  decay_months: number;
  months_since_practice: number | null;
  is_decayed: boolean;
  unlocks_total: number;
  blocks_below_target: number;
  is_blocked: boolean;
  is_available: boolean;
  unmet_prerequisites: UnmetPrerequisite[];
}

export interface SkillNode {
  id: number;
  code: string;
  name: string;
  description: string | null;
  decay_months: number | null;
}

export interface SkillEdge {
  prerequisite_skill_id: number;
  dependent_skill_id: number;
  required_level: number;
  note: string | null;
}

export interface SkillDomain {
  code: string;
  name: string;
  ordinal: number;
}

export interface Graph {
  domains: SkillDomain[];
  skills: SkillNode[];
  edges: SkillEdge[];
  is_acyclic: boolean;
  longest_chain: number;
}

export interface DomainSummary {
  domain_code: string;
  domain_name: string;
  skills: number;
  targeted: number;
  at_target: number;
  total_gap: number;
  decayed: number;
  blocked: number;
}

export interface DeliverableType {
  id: number;
  code: string;
  name: string;
  is_publication: boolean;
  description: string | null;
}

export interface DeliverableSkillLink {
  skill_id: number;
  skill_code: string;
  skill_name: string;
  contribution: number;
}

export interface DeliverableImpact {
  metric_code: string;
  value: string;
  unit: string | null;
  measured_on: string;
  source: string | null;
}

export interface Deliverable {
  id: number;
  title: string;
  summary: string | null;
  type_code: string;
  type_name: string;
  status: "planned" | "in_progress" | "published" | "abandoned";
  started_on: string | null;
  published_on: string | null;
  artifact_url: string | null;
  business_value: string | null;
  skills: DeliverableSkillLink[];
  impacts: DeliverableImpact[];
}

export interface DeliverableInput {
  title: string;
  type_code: string;
  status: string;
  summary?: string | null;
  started_on?: string | null;
  published_on?: string | null;
  artifact_url?: string | null;
  skills: { skill_code: string; contribution: number }[];
}

export interface QuotaLine {
  type_code: string;
  type_name: string;
  required: number;
  published: number;
  met: boolean;
  shortfall: number;
}

export interface QuarterStatus {
  year: number;
  quarter: number;
  starts_on: string;
  ends_on: string;
  phase_code: string | null;
  phase_name: string | null;
  is_current: boolean;
  in_scope: boolean;
  met: boolean;
  is_silent: boolean;
  total_published: number;
  lines: QuotaLine[];
}

export interface EvidenceItem {
  deliverable_id: number;
  title: string;
  type_code: string;
  type_name: string;
  published_on: string | null;
  artifact_url: string | null;
  cited_for_promotion: boolean;
  contribution: number | null;
}

export interface SkillEvidence {
  skill_code: string;
  skill_name: string;
  domain_name: string;
  current_level: number;
  is_defensible: boolean;
  evidence: EvidenceItem[];
}

export interface PhaseQuota {
  type_code: string;
  type_name: string;
  min_per_quarter: number;
}

export interface Phase {
  code: string;
  name: string;
  ordinal: number;
  starts_on: string;
  ends_on: string;
  objective: string | null;
  is_current: boolean;
  quotas: PhaseQuota[];
}
