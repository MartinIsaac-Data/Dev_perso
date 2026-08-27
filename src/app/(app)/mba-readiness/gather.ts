import "server-only";

import { prisma } from "@/lib/db";
import type { ScoringInputs } from "@/lib/scoring/types";

export async function gatherScoringInputs(userId: string): Promise<ScoringInputs> {
  const [profile, education, careerExperiences, impacts, leadership, international, certifications] =
    await Promise.all([
      prisma.profile.findUnique({ where: { userId } }),
      prisma.education.findMany({
        where: { userId },
        select: { degree: true, honors: true, relevantCoursework: true },
      }),
      prisma.careerExperience.findMany({
        where: { userId },
        select: { company: true, role: true, teamSize: true, isCurrent: true },
      }),
      prisma.projectImpact.findMany({
        where: { project: { userId } },
        select: { category: true, projectId: true },
      }),
      prisma.leadershipExperience.findMany({
        where: { userId },
        select: { type: true, teamSize: true, isOngoing: true },
      }),
      prisma.internationalExperience.findMany({
        where: { userId },
        select: { country: true, type: true },
      }),
      prisma.certification.findMany({
        where: { userId },
        select: { name: true, status: true, score: true },
      }),
    ]);

  return {
    yearsOfExperience: profile?.yearsOfExperience ? Number(profile.yearsOfExperience) : null,
    languages: profile?.languages ?? [],
    careerGoalShortTerm: profile?.careerGoalShortTerm ?? null,
    careerGoalLongTerm: profile?.careerGoalLongTerm ?? null,
    mbaRationale: profile?.mbaRationale ?? null,
    education,
    careerExperiences,
    projectImpactCount: new Set(impacts.map((i) => i.projectId)).size,
    projectImpactCategories: impacts.map((i) => i.category),
    leadership,
    international,
    certifications,
  };
}
