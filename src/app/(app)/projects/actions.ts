"use server";

import { revalidatePath } from "next/cache";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { projectImpactSchema, projectSchema } from "@/lib/validations/project";

type ActionResult = { ok: boolean; error?: string };

function toProjectData(parsed: ReturnType<typeof projectSchema.safeParse>) {
  if (!parsed.success) return null;
  const { date, ...rest } = parsed.data;
  return { ...rest, date: date ? new Date(date) : null };
}

export async function createProject(raw: Record<string, string>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = projectSchema.safeParse(raw);
  const data = toProjectData(parsed);
  if (!data) return { ok: false, error: !parsed.success ? parsed.error.issues[0]?.message : "Invalid data" };

  if (data.careerExperienceId) {
    const exp = await prisma.careerExperience.findFirst({
      where: { id: data.careerExperienceId, userId },
    });
    if (!exp) return { ok: false, error: "Career experience not found" };
  }

  await prisma.project.create({ data: { userId, ...data } });
  revalidatePath("/projects");
  revalidatePath("/");
  return { ok: true };
}

export async function updateProject(id: string, raw: Record<string, string>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = projectSchema.safeParse(raw);
  const data = toProjectData(parsed);
  if (!data) return { ok: false, error: !parsed.success ? parsed.error.issues[0]?.message : "Invalid data" };

  if (data.careerExperienceId) {
    const exp = await prisma.careerExperience.findFirst({
      where: { id: data.careerExperienceId, userId },
    });
    if (!exp) return { ok: false, error: "Career experience not found" };
  }

  const { count } = await prisma.project.updateMany({ where: { id, userId }, data });
  if (count === 0) return { ok: false, error: "Project not found" };

  revalidatePath("/projects");
  revalidatePath("/");
  return { ok: true };
}

export async function deleteProject(id: string): Promise<ActionResult> {
  const userId = await requireUserId();
  const { count } = await prisma.project.deleteMany({ where: { id, userId } });
  if (count === 0) return { ok: false, error: "Project not found" };

  revalidatePath("/projects");
  revalidatePath("/");
  return { ok: true };
}

export async function createImpact(projectId: string, raw: Record<string, string>): Promise<ActionResult> {
  const userId = await requireUserId();
  const project = await prisma.project.findFirst({ where: { id: projectId, userId } });
  if (!project) return { ok: false, error: "Project not found" };

  const parsed = projectImpactSchema.safeParse(raw);
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0]?.message };

  await prisma.projectImpact.create({ data: { projectId, ...parsed.data } });
  revalidatePath("/projects");
  return { ok: true };
}

export async function deleteImpact(impactId: string): Promise<ActionResult> {
  const userId = await requireUserId();
  const impact = await prisma.projectImpact.findFirst({
    where: { id: impactId, project: { userId } },
  });
  if (!impact) return { ok: false, error: "Not found" };

  await prisma.projectImpact.delete({ where: { id: impactId } });
  revalidatePath("/projects");
  return { ok: true };
}
