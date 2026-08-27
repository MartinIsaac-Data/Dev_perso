"use server";

import { revalidatePath } from "next/cache";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { storySchema } from "@/lib/validations/story";

type ActionResult = { ok: boolean; error?: string };

export async function createStory(raw: Record<string, unknown>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = storySchema.safeParse(raw);
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0]?.message };

  if (parsed.data.projectId) {
    const project = await prisma.project.findFirst({ where: { id: parsed.data.projectId, userId } });
    if (!project) return { ok: false, error: "Project not found" };
  }

  await prisma.leadershipStory.create({ data: { userId, ...parsed.data } });
  revalidatePath("/ai-advisor");
  return { ok: true };
}

export async function updateStory(id: string, raw: Record<string, unknown>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = storySchema.safeParse(raw);
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0]?.message };

  if (parsed.data.projectId) {
    const project = await prisma.project.findFirst({ where: { id: parsed.data.projectId, userId } });
    if (!project) return { ok: false, error: "Project not found" };
  }

  const { count } = await prisma.leadershipStory.updateMany({ where: { id, userId }, data: parsed.data });
  if (count === 0) return { ok: false, error: "Story not found" };

  revalidatePath("/ai-advisor");
  return { ok: true };
}

export async function deleteStory(id: string): Promise<ActionResult> {
  const userId = await requireUserId();
  const { count } = await prisma.leadershipStory.deleteMany({ where: { id, userId } });
  if (count === 0) return { ok: false, error: "Story not found" };

  revalidatePath("/ai-advisor");
  return { ok: true };
}
