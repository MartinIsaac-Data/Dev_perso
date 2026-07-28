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

// --- Business Case Lab -----------------------------------------------------

export interface Assumption {
  id: number;
  code: string;
  label: string;
  unit: string | null;
  base_value: string;
  low_value: string | null;
  high_value: string | null;
  source: string | null;
  confidence: "low" | "medium" | "high";
  rationale: string | null;
}

export interface DriverBreakdown {
  assumption_id: number;
  code: string;
  label: string;
  unit: string | null;
  value: string;
  confidence: string;
  has_source: boolean;
}

export interface CauseNode {
  node_id: number;
  parent_id: number | null;
  label: string;
  description: string | null;
  evidence_note: string | null;
  depth: number;
  is_leaf: boolean;
  value: string;
  drivers: DriverBreakdown[];
  children: CauseNode[];
}

export interface Reconciliation {
  bottom_up_total: string;
  claimed_annual_loss: string | null;
  currency: string;
  gap: string | null;
  gap_ratio: string | null;
  verdict: string;
}

export interface CauseTree {
  scenario: string;
  currency: string;
  total: string;
  roots: CauseNode[];
  ranked_leaves: CauseNode[];
  reconciliation: Reconciliation;
}

export interface YearFlow {
  year_index: number;
  costs: string;
  benefits: string;
  net: string;
}

export interface RoiResult {
  scenario: string;
  currency: string;
  discount_rate: string;
  horizon_years: number;
  flows: YearFlow[];
  npv: string;
  total_cost_pv: string;
  total_benefit_pv: string;
  total_cost_nominal: string;
  total_benefit_nominal: string;
  payback_years: string | null;
  benefit_cost_ratio: string | null;
  is_positive: boolean;
}

export interface ScenarioComparison {
  pessimistic: RoiResult;
  base: RoiResult;
  optimistic: RoiResult;
}

export interface TornadoRow {
  assumption_id: number;
  code: string;
  label: string;
  unit: string | null;
  confidence: string;
  source: string | null;
  base_value: string;
  low_value: string;
  high_value: string;
  npv_at_low: string;
  npv_at_high: string;
  swing: string;
  has_range: boolean;
  flips_the_decision: boolean;
}

export interface Fragility {
  base_npv: string;
  pessimistic_npv: string;
  optimistic_npv: string;
  survives_pessimistic: boolean;
  only_fails_in_combination: boolean;
  headline: string;
  decision_flipping: TornadoRow[];
  unsourced: TornadoRow[];
  low_confidence_high_impact: TornadoRow[];
  point_estimates: TornadoRow[];
}

export interface AssumptionAudit {
  total: number;
  unsourced: string[];
  point_estimates: string[];
  low_confidence: string[];
  unused: string[];
  sourced_ratio: string;
}

export interface SolutionKpi {
  name: string;
  definition: string | null;
  unit: string | null;
  baseline_value: string | null;
  target_value: string | null;
  measurement_frequency: string | null;
  data_source: string | null;
}

export interface Solution {
  data_requirements: string | null;
  architecture: string | null;
  ai_component: string | null;
  automation_component: string | null;
  process_change: string | null;
  governance: string | null;
  deployment_plan: string | null;
  key_risks: string | null;
  kpis: SolutionKpi[];
}

export interface ReviewScore {
  criterion_code: string;
  criterion_name: string;
  weight: string;
  score: string;
  comment: string | null;
}

export interface ReviewChallenge {
  id: number;
  persona: "cfo" | "coo" | "cio";
  severity: "blocking" | "major" | "minor";
  target_assumption_id: number | null;
  target_assumption_code: string | null;
  target_area: string | null;
  challenge: string;
  evidence_demanded: string | null;
  response: string | null;
  resolved_on: string | null;
}

export interface CaseReview {
  id: number;
  reviewed_on: string;
  roi_model_version: number | null;
  overall_score: string;
  verdict: string | null;
  summary: string | null;
  scores: ReviewScore[];
  challenges: ReviewChallenge[];
}

export interface RoiLine {
  id: number;
  kind: "cost" | "benefit";
  category: string;
  label: string;
  year_index: number;
  quantity: string;
  amount_assumption_id: number;
  amount_code: string;
  notes: string | null;
}

export interface RoiModel {
  id: number;
  version: number;
  horizon_years: number;
  discount_rate: string;
  currency: string;
  notes: string | null;
  lines: RoiLine[];
}

export interface CaseSummary {
  id: number;
  title: string;
  industry: string | null;
  currency: string;
  status: string;
  opened_on: string;
  claimed_annual_loss: string | null;
  bottom_up_total: string;
  gap_ratio: string | null;
  assumption_count: number;
  latest_roi_version: number | null;
  base_npv: string | null;
  latest_review_score: string | null;
  open_challenges: number;
}

export interface CaseDetail {
  id: number;
  title: string;
  symptom: string;
  industry: string | null;
  company_context: string | null;
  currency: string;
  status: string;
  opened_on: string;
  claimed_annual_loss: string | null;
  assumptions: Assumption[];
  cause_tree: CauseTree;
  solution: Solution | null;
  roi_models: RoiModel[];
  reviews: CaseReview[];
  audit: AssumptionAudit;
}
