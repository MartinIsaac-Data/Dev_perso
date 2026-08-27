"use server";

import { revalidatePath } from "next/cache";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import {
  mbaDeadlineSchema,
  mbaProgramSchema,
  mbaScholarshipSchema,
} from "@/lib/validations/mba-program";

type ActionResult = { ok: boolean; error?: string };

function toProgramData(parsed: ReturnType<typeof mbaProgramSchema.safeParse>) {
  if (!parsed.success) return null;
  const { lastVerifiedAt, ...rest } = parsed.data;
  return { ...rest, lastVerifiedAt: lastVerifiedAt ? new Date(lastVerifiedAt) : null };
}

export async function createProgram(raw: Record<string, string>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = mbaProgramSchema.safeParse(raw);
  const data = toProgramData(parsed);
  if (!data) return { ok: false, error: !parsed.success ? parsed.error.issues[0]?.message : "Invalid data" };

  const dimensions = await prisma.scoringDimension.findMany();

  await prisma.$transaction(async (tx) => {
    const program = await tx.mBAProgram.create({ data: { userId, ...data } });
    if (dimensions.length > 0) {
      await tx.mBADimensionWeight.createMany({
        data: dimensions.map((d) => ({
          programId: program.id,
          dimensionKey: d.key,
          weight: d.defaultWeight,
        })),
      });
    }
  });

  revalidatePath("/mba-targets");
  revalidatePath("/");
  return { ok: true };
}

export async function updateProgram(id: string, raw: Record<string, string>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = mbaProgramSchema.safeParse(raw);
  const data = toProgramData(parsed);
  if (!data) return { ok: false, error: !parsed.success ? parsed.error.issues[0]?.message : "Invalid data" };

  const { count } = await prisma.mBAProgram.updateMany({ where: { id, userId }, data });
  if (count === 0) return { ok: false, error: "Program not found" };

  revalidatePath("/mba-targets");
  revalidatePath("/");
  return { ok: true };
}

export async function deleteProgram(id: string): Promise<ActionResult> {
  const userId = await requireUserId();
  const { count } = await prisma.mBAProgram.deleteMany({ where: { id, userId } });
  if (count === 0) return { ok: false, error: "Program not found" };

  revalidatePath("/mba-targets");
  revalidatePath("/");
  return { ok: true };
}

export async function setPrimaryProgram(id: string): Promise<ActionResult> {
  const userId = await requireUserId();
  const program = await prisma.mBAProgram.findFirst({ where: { id, userId } });
  if (!program) return { ok: false, error: "Program not found" };

  await prisma.$transaction([
    prisma.mBAProgram.updateMany({ where: { userId }, data: { isPrimaryTarget: false } }),
    prisma.mBAProgram.update({ where: { id }, data: { isPrimaryTarget: true } }),
  ]);

  revalidatePath("/mba-targets");
  revalidatePath("/");
  return { ok: true };
}

export async function toggleArchiveProgram(id: string, archived: boolean): Promise<ActionResult> {
  const userId = await requireUserId();
  const { count } = await prisma.mBAProgram.updateMany({
    where: { id, userId },
    data: { isArchived: archived, isPrimaryTarget: archived ? false : undefined },
  });
  if (count === 0) return { ok: false, error: "Program not found" };

  revalidatePath("/mba-targets");
  revalidatePath("/");
  return { ok: true };
}

export async function updateWeights(
  programId: string,
  weights: Record<string, number>,
): Promise<ActionResult> {
  const userId = await requireUserId();
  const program = await prisma.mBAProgram.findFirst({ where: { id: programId, userId } });
  if (!program) return { ok: false, error: "Program not found" };

  const total = Object.values(weights).reduce((sum, w) => sum + w, 0);
  if (Math.round(total) !== 100) {
    return { ok: false, error: `Weights must total 100 (currently ${total.toFixed(0)})` };
  }

  await prisma.$transaction(
    Object.entries(weights).map(([dimensionKey, weight]) =>
      prisma.mBADimensionWeight.upsert({
        where: { programId_dimensionKey: { programId, dimensionKey } },
        create: { programId, dimensionKey, weight },
        update: { weight },
      }),
    ),
  );

  revalidatePath("/mba-targets");
  revalidatePath("/mba-readiness");
  return { ok: true };
}

// --- Deadlines ---

export async function createDeadline(programId: string, raw: Record<string, string>): Promise<ActionResult> {
  const userId = await requireUserId();
  const program = await prisma.mBAProgram.findFirst({ where: { id: programId, userId } });
  if (!program) return { ok: false, error: "Program not found" };

  const parsed = mbaDeadlineSchema.safeParse(raw);
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0]?.message };

  await prisma.mBADeadline.create({
    data: { programId, round: parsed.data.round, deadline: new Date(parsed.data.deadline), notes: parsed.data.notes },
  });
  revalidatePath("/mba-targets");
  revalidatePath("/");
  return { ok: true };
}

export async function deleteDeadline(deadlineId: string): Promise<ActionResult> {
  const userId = await requireUserId();
  const deadline = await prisma.mBADeadline.findFirst({
    where: { id: deadlineId, program: { userId } },
  });
  if (!deadline) return { ok: false, error: "Not found" };

  await prisma.mBADeadline.delete({ where: { id: deadlineId } });
  revalidatePath("/mba-targets");
  revalidatePath("/");
  return { ok: true };
}

// --- Scholarships ---

export async function createScholarship(
  programId: string,
  raw: Record<string, string>,
): Promise<ActionResult> {
  const userId = await requireUserId();
  const program = await prisma.mBAProgram.findFirst({ where: { id: programId, userId } });
  if (!program) return { ok: false, error: "Program not found" };

  const parsed = mbaScholarshipSchema.safeParse(raw);
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0]?.message };

  const { deadline, ...rest } = parsed.data;
  await prisma.mBAScholarship.create({
    data: { programId, ...rest, deadline: deadline ? new Date(deadline) : null },
  });
  revalidatePath("/mba-targets");
  return { ok: true };
}

export async function deleteScholarship(scholarshipId: string): Promise<ActionResult> {
  const userId = await requireUserId();
  const scholarship = await prisma.mBAScholarship.findFirst({
    where: { id: scholarshipId, program: { userId } },
  });
  if (!scholarship) return { ok: false, error: "Not found" };

  await prisma.mBAScholarship.delete({ where: { id: scholarshipId } });
  revalidatePath("/mba-targets");
  return { ok: true };
}
