"use server";

import { revalidatePath } from "next/cache";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { achievementSchema, careerExperienceSchema } from "@/lib/validations/career";

type ActionResult = { ok: boolean; error?: string };

function toExperienceData(parsed: ReturnType<typeof careerExperienceSchema.safeParse>) {
  if (!parsed.success) return null;
  const { startDate, endDate, isCurrent, ...rest } = parsed.data;
  return {
    ...rest,
    startDate: new Date(startDate),
    endDate: isCurrent ? null : endDate ? new Date(endDate) : null,
    isCurrent,
  };
}

export async function createExperience(raw: Record<string, unknown>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = careerExperienceSchema.safeParse(raw);
  const data = toExperienceData(parsed);
  if (!data) return { ok: false, error: !parsed.success ? parsed.error.issues[0]?.message : "Invalid data" };

  await prisma.careerExperience.create({ data: { userId, ...data } });
  revalidatePath("/career");
  revalidatePath("/");
  return { ok: true };
}

export async function updateExperience(id: string, raw: Record<string, unknown>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = careerExperienceSchema.safeParse(raw);
  const data = toExperienceData(parsed);
  if (!data) return { ok: false, error: !parsed.success ? parsed.error.issues[0]?.message : "Invalid data" };

  const { count } = await prisma.careerExperience.updateMany({ where: { id, userId }, data });
  if (count === 0) return { ok: false, error: "Not found" };

  revalidatePath("/career");
  revalidatePath("/");
  return { ok: true };
}

export async function deleteExperience(id: string): Promise<ActionResult> {
  const userId = await requireUserId();
  const { count } = await prisma.careerExperience.deleteMany({ where: { id, userId } });
  if (count === 0) return { ok: false, error: "Not found" };

  revalidatePath("/career");
  revalidatePath("/");
  return { ok: true };
}

export async function createAchievement(
  careerExperienceId: string,
  raw: Record<string, string>,
): Promise<ActionResult> {
  const userId = await requireUserId();
  const experience = await prisma.careerExperience.findFirst({
    where: { id: careerExperienceId, userId },
  });
  if (!experience) return { ok: false, error: "Career experience not found" };

  const parsed = achievementSchema.safeParse(raw);
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0]?.message };

  const { date, ...rest } = parsed.data;
  await prisma.careerAchievement.create({
    data: { careerExperienceId, ...rest, date: date ? new Date(date) : null },
  });

  revalidatePath("/career");
  return { ok: true };
}

export async function deleteAchievement(achievementId: string): Promise<ActionResult> {
  const userId = await requireUserId();
  const achievement = await prisma.careerAchievement.findFirst({
    where: { id: achievementId, careerExperience: { userId } },
  });
  if (!achievement) return { ok: false, error: "Not found" };

  await prisma.careerAchievement.delete({ where: { id: achievementId } });
  revalidatePath("/career");
  return { ok: true };
}
