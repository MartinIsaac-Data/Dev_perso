import "server-only";

import { prisma } from "@/lib/db";
import { computeReadiness } from "@/lib/scoring/engine";
import { gatherScoringInputs } from "@/app/(app)/mba-readiness/gather";

export async function buildAdvisorContext(userId: string): Promise<string> {
  const [profile, primaryProgram, experiences, projects, skills, certifications, tasks] = await Promise.all([
    prisma.profile.findUnique({ where: { userId } }),
    prisma.mBAProgram.findFirst({
      where: { userId, isPrimaryTarget: true, isArchived: false },
      include: { dimensionWeights: true },
    }),
    prisma.careerExperience.findMany({
      where: { userId },
      select: { company: true, role: true, isCurrent: true, startDate: true, endDate: true },
      orderBy: { startDate: "desc" },
    }),
    prisma.project.findMany({
      where: { userId },
      select: { name: true, result: true },
      take: 10,
    }),
    prisma.skill.findMany({ where: { userId }, select: { name: true, currentLevel: true, targetLevel: true } }),
    prisma.certification.findMany({ where: { userId }, select: { name: true, status: true } }),
    prisma.task.findMany({
      where: { userId, status: { not: "DONE" } },
      select: { title: true, priority: true, deadline: true },
      take: 10,
    }),
  ]);

  let readinessSummary = "No MBA program marked as primary target yet.";
  if (primaryProgram) {
    const dimensions = await prisma.scoringDimension.findMany({ orderBy: { sortOrder: "asc" } });
    const weightMap = new Map(primaryProgram.dimensionWeights.map((w) => [w.dimensionKey, Number(w.weight)]));
    const config = dimensions.map((d) => ({
      key: d.key,
      label: d.label,
      weight: weightMap.get(d.key) ?? Number(d.defaultWeight),
    }));
    const inputs = await gatherScoringInputs(userId);
    const breakdown = computeReadiness(inputs, config);
    readinessSummary = `Primary target: ${primaryProgram.schoolName} — ${primaryProgram.programName}. Readiness score: ${breakdown.totalScore}/100. Dimension scores: ${breakdown.dimensions
      .map((d) => `${d.label} ${d.score}`)
      .join(", ")}.`;
  }

  const lines = [
    `Name: ${profile?.fullName ?? "Unknown"}`,
    `Current role: ${profile?.currentJobTitle ?? "—"} at ${profile?.currentCompany ?? "—"}`,
    `Years of experience: ${profile?.yearsOfExperience ?? "—"}`,
    `Short-term goal: ${profile?.careerGoalShortTerm ?? "Not set"}`,
    `Long-term goal: ${profile?.careerGoalLongTerm ?? "Not set"}`,
    `MBA rationale: ${profile?.mbaRationale ?? "Not set"}`,
    "",
    readinessSummary,
    "",
    `Career history: ${experiences.map((e) => `${e.role} at ${e.company}${e.isCurrent ? " (current)" : ""}`).join("; ") || "None logged"}`,
    `Recent projects: ${projects.map((p) => `${p.name}${p.result ? ` — ${p.result}` : ""}`).join("; ") || "None logged"}`,
    `Skills: ${skills.map((s) => `${s.name} (${s.currentLevel} → ${s.targetLevel})`).join(", ") || "None logged"}`,
    `Certifications: ${certifications.map((c) => `${c.name} (${c.status})`).join(", ") || "None logged"}`,
    `Open tasks: ${tasks.map((t) => `${t.title} [${t.priority}]`).join("; ") || "None"}`,
  ];

  return lines.join("\n");
}

export const ADVISOR_SYSTEM_PROMPT = `You are the AI Career Advisor inside MBA Compass, a personal career and MBA
preparation tool. You are given a factual snapshot of the user's own data below.

Rules:
- Only reference facts present in the snapshot. Never invent achievements, employers, scores, or
  experiences the user hasn't logged.
- If the user asks about something not in the snapshot, say so plainly and suggest they log it in
  the relevant part of the app (Career, Projects, Skills, Certifications, MBA Targets, Tasks).
- Be direct and specific. Prefer concrete next actions over generic advice.
- The MBA Readiness score is a preparation score against configured criteria, not an admission
  probability — never frame it as one, and never state or imply an admission chance.
- Keep responses concise (a few short paragraphs or a short list), not essay-length.`;
