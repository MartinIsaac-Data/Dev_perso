import "server-only";

import { prisma } from "@/lib/db";
import { computeReadiness } from "@/lib/scoring/engine";
import { gatherScoringInputs } from "@/app/(app)/mba-readiness/gather";

export type NextBestAction = {
  title: string;
  reason: string;
  deadline?: Date | null;
  expectedImpact?: string;
  severity: number; // higher = more urgent, used only for ranking
  href: string;
};

const DAY_MS = 24 * 60 * 60 * 1000;

export async function computeNextBestActions(userId: string): Promise<NextBestAction[]> {
  const now = new Date();
  const candidates: NextBestAction[] = [];

  const [overdueTasks, highPriorityTasks, programs, certifications, financialPlan] = await Promise.all([
    prisma.task.findMany({
      where: { userId, status: { not: "DONE" }, deadline: { lt: now } },
      orderBy: { deadline: "asc" },
      take: 3,
    }),
    prisma.task.findMany({
      where: { userId, status: { not: "DONE" }, priority: { in: ["CRITICAL", "HIGH"] }, deadline: null },
      take: 3,
    }),
    prisma.mBAProgram.findMany({
      where: { userId, isArchived: false },
      include: { deadlines: { where: { deadline: { gte: now } }, orderBy: { deadline: "asc" }, take: 1 } },
    }),
    prisma.certification.findMany({
      where: { userId, status: { in: ["PLANNING", "IN_PROGRESS", "EXAM_SCHEDULED"] } },
    }),
    prisma.financialPlan.findFirst({ where: { userId } }),
  ]);

  for (const task of overdueTasks) {
    candidates.push({
      title: task.title,
      reason: "This task is overdue.",
      deadline: task.deadline,
      severity: 100,
      href: "/tasks",
    });
  }

  for (const task of highPriorityTasks) {
    candidates.push({
      title: task.title,
      reason: `Marked ${task.priority.toLowerCase()} priority with no deadline set.`,
      severity: task.priority === "CRITICAL" ? 70 : 55,
      href: "/tasks",
    });
  }

  for (const program of programs) {
    const nextDeadline = program.deadlines[0];
    if (!nextDeadline) continue;
    const daysAway = (nextDeadline.deadline.getTime() - now.getTime()) / DAY_MS;
    if (daysAway <= 60) {
      candidates.push({
        title: `${nextDeadline.round} deadline for ${program.schoolName}`,
        reason: `${Math.max(0, Math.round(daysAway))} days away.`,
        deadline: nextDeadline.deadline,
        severity: daysAway <= 14 ? 95 : 65,
        href: "/mba-targets",
      });
    }
  }

  for (const cert of certifications) {
    if (cert.examDate) {
      const daysAway = (cert.examDate.getTime() - now.getTime()) / DAY_MS;
      if (daysAway >= 0 && daysAway <= 30) {
        candidates.push({
          title: `Prepare for ${cert.name}`,
          reason: `Exam in ${Math.round(daysAway)} days.`,
          deadline: cert.examDate,
          severity: 85,
          href: "/certifications",
        });
      }
    }
    if (cert.expirationDate) {
      const daysAway = (cert.expirationDate.getTime() - now.getTime()) / DAY_MS;
      if (daysAway >= 0 && daysAway <= 60) {
        candidates.push({
          title: `${cert.name} expires soon`,
          reason: `Renews or expires in ${Math.round(daysAway)} days.`,
          deadline: cert.expirationDate,
          severity: 60,
          href: "/certifications",
        });
      }
    }
  }

  const primaryProgram = await prisma.mBAProgram.findFirst({
    where: { userId, isPrimaryTarget: true, isArchived: false },
    include: { dimensionWeights: true },
  });
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
    const biggestGap = [...breakdown.dimensions].sort(
      (a, b) => b.weight * (100 - b.score) - a.weight * (100 - a.score),
    )[0];
    if (biggestGap && biggestGap.recommendations[0]) {
      candidates.push({
        title: `Close your ${biggestGap.label} gap`,
        reason: biggestGap.recommendations[0],
        expectedImpact: `Your lowest-scoring weighted dimension (${biggestGap.score}/100).`,
        severity: 50,
        href: "/mba-readiness",
      });
    }
  }

  if (financialPlan) {
    const totalCost =
      Number(financialPlan.tuition ?? 0) +
      Number(financialPlan.livingCost ?? 0) +
      Number(financialPlan.travelCost ?? 0) +
      Number(financialPlan.visaCost ?? 0) +
      Number(financialPlan.insuranceCost ?? 0) +
      Number(financialPlan.otherCost ?? 0);
    if (totalCost > 0 && Number(financialPlan.monthlyContribution) === 0) {
      candidates.push({
        title: "Set up a monthly savings contribution",
        reason: "Your financial plan has an estimated cost but no monthly contribution planned.",
        severity: 45,
        href: "/financial-plan",
      });
    }
  }

  return candidates.sort((a, b) => b.severity - a.severity).slice(0, 3);
}
