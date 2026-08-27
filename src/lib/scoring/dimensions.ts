import type { ScoringInputs } from "@/lib/scoring/types";

function clamp(n: number, min = 0, max = 100) {
  return Math.max(min, Math.min(max, Math.round(n)));
}

type DimensionOutput = { score: number; factors: { label: string; value: string }[]; recommendations: string[] };

function academicProfile(i: ScoringInputs): DimensionOutput {
  const factors: { label: string; value: string }[] = [];
  const recommendations: string[] = [];
  let score = 0;

  const hasDegree = i.education.length > 0;
  if (hasDegree) score += 40;
  factors.push({ label: "Degree on file", value: hasDegree ? "Yes" : "No" });

  const hasMasters = i.education.some((e) => /master|msc|mba|ms\b|m\.sc/i.test(e.degree));
  if (hasMasters) score += 30;
  factors.push({ label: "Master's-level degree", value: hasMasters ? "Yes" : "No" });

  const hasHonors = i.education.some((e) => !!e.honors);
  if (hasHonors) score += 15;
  factors.push({ label: "Academic honors", value: hasHonors ? "Yes" : "No" });

  const courseworkCount = i.education.reduce((sum, e) => sum + e.relevantCoursework.length, 0);
  if (courseworkCount >= 3) score += 15;
  factors.push({ label: "Relevant coursework logged", value: String(courseworkCount) });

  if (!hasDegree) recommendations.push("Add your degree(s) under Education.");
  if (!hasMasters) recommendations.push("A quantitative or business-adjacent master's strengthens this dimension, if applicable.");

  return { score: clamp(score), factors, recommendations };
}

function professionalExperience(i: ScoringInputs): DimensionOutput {
  const factors: { label: string; value: string }[] = [];
  const recommendations: string[] = [];

  const years = i.yearsOfExperience ?? 0;
  const experienceScore = clamp((years / 8) * 70, 0, 70);
  factors.push({ label: "Years of experience", value: years.toString() });

  const distinctCompanies = new Set(i.careerExperiences.map((e) => e.company)).size;
  const diversityScore = clamp(distinctCompanies * 10, 0, 20);
  factors.push({ label: "Companies", value: String(distinctCompanies) });

  const hasResponsibility = i.careerExperiences.some((e) => e.isCurrent && (e.teamSize ?? 0) > 0);
  const responsibilityScore = hasResponsibility ? 10 : 0;
  factors.push({ label: "Current role has direct reports", value: hasResponsibility ? "Yes" : "No" });

  if (years < 4) recommendations.push("Most target programs expect 3-6+ years of experience — keep building tenure.");
  if (!hasResponsibility) recommendations.push("Taking on direct reports in your current role would strengthen this dimension.");

  return { score: clamp(experienceScore + diversityScore + responsibilityScore), factors, recommendations };
}

function leadership(i: ScoringInputs): DimensionOutput {
  const factors: { label: string; value: string }[] = [];
  const recommendations: string[] = [];

  const count = i.leadership.length;
  const countScore = clamp(count * 15, 0, 60);
  factors.push({ label: "Leadership experiences logged", value: String(count) });

  const hasTeamLead = i.leadership.some((l) => l.type === "TEAM_LEADERSHIP" && (l.teamSize ?? 0) >= 3);
  const teamScore = hasTeamLead ? 20 : 0;
  factors.push({ label: "Team leadership (3+ people)", value: hasTeamLead ? "Yes" : "No" });

  const hasMentoring = i.leadership.some((l) => l.type === "MENTORING");
  const mentoringScore = hasMentoring ? 10 : 0;
  factors.push({ label: "Mentoring", value: hasMentoring ? "Yes" : "No" });

  const hasOngoing = i.leadership.some((l) => l.isOngoing);
  const ongoingScore = hasOngoing ? 10 : 0;
  factors.push({ label: "Ongoing leadership role", value: hasOngoing ? "Yes" : "No" });

  if (count === 0) recommendations.push("Log a leadership experience — project leadership, team management, mentoring or community work.");
  if (!hasTeamLead) recommendations.push("Lead a project involving at least three people or departments.");

  return { score: clamp(countScore + teamScore + mentoringScore + ongoingScore), factors, recommendations };
}

function businessImpact(i: ScoringInputs): DimensionOutput {
  const factors: { label: string; value: string }[] = [];
  const recommendations: string[] = [];

  const countScore = clamp(i.projectImpactCount * 15, 0, 75);
  factors.push({ label: "Projects with measured impact", value: String(i.projectImpactCount) });

  const distinctCategories = new Set(i.projectImpactCategories).size;
  const diversityScore = clamp(distinctCategories * 5, 0, 25);
  factors.push({ label: "Impact categories covered", value: String(distinctCategories) });

  if (i.projectImpactCount === 0) recommendations.push("Add a project and quantify its before/after impact — this is the single highest-leverage dimension to improve.");
  else if (i.projectImpactCount < 3) recommendations.push("Document impact on 1-2 more projects with clear before/after numbers.");

  return { score: clamp(countScore + diversityScore), factors, recommendations };
}

function internationalExposure(i: ScoringInputs): DimensionOutput {
  const factors: { label: string; value: string }[] = [];
  const recommendations: string[] = [];

  const distinctCountries = new Set(i.international.map((r) => r.country)).size;
  const countryScore = clamp(distinctCountries * 15, 0, 75);
  factors.push({ label: "Countries", value: String(distinctCountries) });

  const distinctTypes = new Set(i.international.map((r) => r.type)).size;
  const typeScore = clamp(distinctTypes * 5, 0, 25);
  factors.push({ label: "Exposure types", value: String(distinctTypes) });

  if (distinctCountries < 2) recommendations.push("Seek an international project, client, or multicultural team assignment.");

  return { score: clamp(countryScore + typeScore), factors, recommendations };
}

function gmatGre(i: ScoringInputs): DimensionOutput {
  const factors: { label: string; value: string }[] = [];
  const recommendations: string[] = [];

  const test = i.certifications.find((c) => /gmat|gre\b/i.test(c.name));
  let score = 0;
  if (test) {
    if (test.status === "PASSED") score = test.score ? 90 : 70;
    else if (test.status === "EXAM_SCHEDULED") score = 40;
    else if (test.status === "IN_PROGRESS") score = 30;
    else if (test.status === "PLANNING") score = 10;
  }
  factors.push({ label: "Test", value: test ? `${test.name} — ${test.status}` : "Not logged" });
  if (test?.score) factors.push({ label: "Score", value: test.score });

  if (!test) recommendations.push("Decide on GMAT vs. GRE and log it under Certifications to start tracking prep.");
  else if (test.status !== "PASSED") recommendations.push("Keep to your GMAT/GRE prep plan — this is a heavily-weighted, controllable dimension.");

  return { score: clamp(score), factors, recommendations };
}

function english(i: ScoringInputs): DimensionOutput {
  const factors: { label: string; value: string }[] = [];
  const recommendations: string[] = [];

  const test = i.certifications.find((c) => /toefl|ielts|english/i.test(c.name));
  const speaksEnglish = i.languages.some((l) => /english/i.test(l));
  let score = 0;
  if (test?.status === "PASSED") score = 80;
  else if (test && (test.status === "IN_PROGRESS" || test.status === "EXAM_SCHEDULED")) score = 40;
  else if (speaksEnglish) score = 60;

  if (speaksEnglish) score += 20;
  factors.push({ label: "English test", value: test ? `${test.name} — ${test.status}` : "Not logged" });
  factors.push({ label: "English listed as a language", value: speaksEnglish ? "Yes" : "No" });

  if (!test) recommendations.push("If your target schools require it, log a TOEFL/IELTS score under Certifications.");

  return { score: clamp(score), factors, recommendations };
}

function careerProgression(i: ScoringInputs): DimensionOutput {
  const factors: { label: string; value: string }[] = [];
  const recommendations: string[] = [];

  const roleCount = i.careerExperiences.length;
  const countScore = clamp(roleCount * 20, 0, 80);
  factors.push({ label: "Roles logged", value: String(roleCount) });

  const hasSeniorTitle = i.careerExperiences.some((e) =>
    /manager|director|head|lead|vp|chief|principal/i.test(e.role),
  );
  const seniorityScore = hasSeniorTitle ? 20 : 0;
  factors.push({ label: "Senior title held", value: hasSeniorTitle ? "Yes" : "No" });

  if (roleCount < 2) recommendations.push("Log your full role history — progression is judged relative to tenure, not a single role.");

  return { score: clamp(countScore + seniorityScore), factors, recommendations };
}

function extracurricular(i: ScoringInputs): DimensionOutput {
  const factors: { label: string; value: string }[] = [];
  const recommendations: string[] = [];

  const count = i.leadership.filter((l) => l.type === "COMMUNITY" || l.type === "ENTREPRENEURSHIP").length;
  const score = count > 0 ? clamp(30 + count * 30, 0, 90) : 0;
  factors.push({ label: "Community / entrepreneurship activities", value: String(count) });

  if (count === 0) recommendations.push("Volunteering, an association, or a side venture rounds out your profile beyond work.");

  return { score, factors, recommendations };
}

function goalClarity(i: ScoringInputs): DimensionOutput {
  const factors: { label: string; value: string }[] = [];
  const recommendations: string[] = [];

  const filled = [i.careerGoalShortTerm, i.careerGoalLongTerm, i.mbaRationale].filter(Boolean).length;
  const score = clamp((filled / 3) * 100);
  factors.push({ label: "Short-term goal", value: i.careerGoalShortTerm ? "Set" : "Missing" });
  factors.push({ label: "Long-term goal", value: i.careerGoalLongTerm ? "Set" : "Missing" });
  factors.push({ label: "MBA rationale", value: i.mbaRationale ? "Set" : "Missing" });

  if (filled < 3) recommendations.push("Fill in your short-term goal, long-term goal and MBA rationale in Settings.");

  return { score, factors, recommendations };
}

export const DIMENSION_CALCULATORS: Record<string, (i: ScoringInputs) => DimensionOutput> = {
  ACADEMIC_PROFILE: academicProfile,
  PROFESSIONAL_EXPERIENCE: professionalExperience,
  LEADERSHIP: leadership,
  BUSINESS_IMPACT: businessImpact,
  INTERNATIONAL_EXPOSURE: internationalExposure,
  GMAT_GRE: gmatGre,
  ENGLISH: english,
  CAREER_PROGRESSION: careerProgression,
  EXTRACURRICULAR: extracurricular,
  GOAL_CLARITY: goalClarity,
};
