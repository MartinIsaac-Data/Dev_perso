"use server";

import { revalidatePath } from "next/cache";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { milestoneSchema, roadmapSchema } from "@/lib/validations/roadmap";

type ActionResult = { ok: boolean; error?: string };

export async function createRoadmap(raw: Record<string, string>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = roadmapSchema.safeParse(raw);
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0]?.message };

  await prisma.roadmap.create({ data: { userId, ...parsed.data, isActive: true } });
  revalidatePath("/roadmap");
  return { ok: true };
}

export async function createMilestone(roadmapId: string, raw: Record<string, string>): Promise<ActionResult> {
  const userId = await requireUserId();
  const roadmap = await prisma.roadmap.findFirst({ where: { id: roadmapId, userId } });
  if (!roadmap) return { ok: false, error: "Roadmap not found" };

  const parsed = milestoneSchema.safeParse(raw);
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0]?.message };

  const { deadline, ...rest } = parsed.data;
  await prisma.roadmapMilestone.create({
    data: { roadmapId, ...rest, deadline: deadline ? new Date(deadline) : null },
  });
  revalidatePath("/roadmap");
  return { ok: true };
}

export async function updateMilestone(id: string, raw: Record<string, string>): Promise<ActionResult> {
  const userId = await requireUserId();
  const milestone = await prisma.roadmapMilestone.findFirst({
    where: { id, roadmap: { userId } },
  });
  if (!milestone) return { ok: false, error: "Milestone not found" };

  const parsed = milestoneSchema.safeParse(raw);
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0]?.message };

  const { deadline, ...rest } = parsed.data;
  await prisma.roadmapMilestone.update({
    where: { id },
    data: { ...rest, deadline: deadline ? new Date(deadline) : null },
  });
  revalidatePath("/roadmap");
  return { ok: true };
}

export async function deleteMilestone(id: string): Promise<ActionResult> {
  const userId = await requireUserId();
  const milestone = await prisma.roadmapMilestone.findFirst({
    where: { id, roadmap: { userId } },
  });
  if (!milestone) return { ok: false, error: "Milestone not found" };

  await prisma.roadmapMilestone.delete({ where: { id } });
  revalidatePath("/roadmap");
  return { ok: true };
}
