"use server";

import { revalidatePath } from "next/cache";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { computeReadiness } from "@/lib/scoring/engine";
import { gatherScoringInputs } from "@/app/(app)/mba-readiness/gather";

export async function saveAssessment(programId: string) {
  const userId = await requireUserId();
  const program = await prisma.mBAProgram.findFirst({
    where: { id: programId, userId },
    include: { dimensionWeights: true },
  });
  if (!program) return { ok: false as const, error: "Program not found" };

  const dimensions = await prisma.scoringDimension.findMany({ orderBy: { sortOrder: "asc" } });
  const weightMap = new Map(program.dimensionWeights.map((w) => [w.dimensionKey, Number(w.weight)]));
  const config = dimensions.map((d) => ({
    key: d.key,
    label: d.label,
    weight: weightMap.get(d.key) ?? Number(d.defaultWeight),
  }));

  const inputs = await gatherScoringInputs(userId);
  const breakdown = computeReadiness(inputs, config);

  await prisma.mBAAssessment.create({
    data: {
      userId,
      programId,
      totalScore: breakdown.totalScore,
      isSimulation: false,
      breakdown: breakdown as unknown as object,
    },
  });

  revalidatePath("/mba-readiness");
  revalidatePath("/");
  return { ok: true as const, breakdown };
}
