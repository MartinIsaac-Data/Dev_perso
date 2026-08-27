"use server";

import { revalidatePath } from "next/cache";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { skillSchema } from "@/lib/validations/skill";

type ActionResult = { ok: boolean; error?: string };

export async function createSkill(raw: Record<string, string>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = skillSchema.safeParse(raw);
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0]?.message };

  await prisma.skill.create({ data: { userId, ...parsed.data } });
  revalidatePath("/skills");
  revalidatePath("/");
  return { ok: true };
}

export async function updateSkill(id: string, raw: Record<string, string>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = skillSchema.safeParse(raw);
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0]?.message };

  const { count } = await prisma.skill.updateMany({
    where: { id, userId },
    data: parsed.data,
  });
  if (count === 0) return { ok: false, error: "Skill not found" };

  revalidatePath("/skills");
  revalidatePath("/");
  return { ok: true };
}

export async function deleteSkill(id: string): Promise<ActionResult> {
  const userId = await requireUserId();
  const { count } = await prisma.skill.deleteMany({ where: { id, userId } });
  if (count === 0) return { ok: false, error: "Skill not found" };

  revalidatePath("/skills");
  revalidatePath("/");
  return { ok: true };
}
