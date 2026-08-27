export type ScoringInputs = {
  yearsOfExperience: number | null;
  languages: string[];
  careerGoalShortTerm: string | null;
  careerGoalLongTerm: string | null;
  mbaRationale: string | null;
  education: { degree: string; honors: string | null; relevantCoursework: string[] }[];
  careerExperiences: { company: string; role: string; teamSize: number | null; isCurrent: boolean }[];
  projectImpactCount: number;
  projectImpactCategories: string[];
  leadership: { type: string; teamSize: number | null; isOngoing: boolean }[];
  international: { country: string; type: string }[];
  certifications: { name: string; status: string; score: string | null }[];
};

export type DimensionResult = {
  key: string;
  label: string;
  score: number; // 0-100
  weight: number; // 0-100, percentage points
  weighted: number; // score * weight / 100
  factors: { label: string; value: string }[];
  recommendations: string[];
};

export type ReadinessBreakdown = {
  totalScore: number;
  dimensions: DimensionResult[];
};
