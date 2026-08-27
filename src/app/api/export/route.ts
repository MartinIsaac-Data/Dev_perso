import { NextResponse } from "next/server";

import { prisma } from "@/lib/db";
import { auth } from "@/auth";

export async function GET() {
  const session = await auth();
  const userId = session?.user?.id;
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const [
    profile,
    careerExperiences,
    projects,
    evidence,
    skills,
    certifications,
    courses,
    education,
    leadershipExperiences,
    leadershipStories,
    internationalExperiences,
    mbaPrograms,
    mbaApplications,
    goals,
    roadmaps,
    tasks,
    financialPlan,
    financialTransactions,
  ] = await Promise.all([
    prisma.profile.findUnique({ where: { userId } }),
    prisma.careerExperience.findMany({ where: { userId }, include: { achievements: true } }),
    prisma.project.findMany({ where: { userId }, include: { impacts: true } }),
    prisma.evidence.findMany({ where: { userId } }),
    prisma.skill.findMany({ where: { userId }, include: { assessments: true } }),
    prisma.certification.findMany({ where: { userId } }),
    prisma.course.findMany({ where: { userId } }),
    prisma.education.findMany({ where: { userId } }),
    prisma.leadershipExperience.findMany({ where: { userId } }),
    prisma.leadershipStory.findMany({ where: { userId } }),
    prisma.internationalExperience.findMany({ where: { userId } }),
    prisma.mBAProgram.findMany({
      where: { userId },
      include: { deadlines: true, scholarships: true, requirements: true, dimensionWeights: true },
    }),
    prisma.mBAApplication.findMany({ where: { userId } }),
    prisma.goal.findMany({ where: { userId } }),
    prisma.roadmap.findMany({ where: { userId }, include: { milestones: true } }),
    prisma.task.findMany({ where: { userId } }),
    prisma.financialPlan.findFirst({ where: { userId } }),
    prisma.financialTransaction.findMany({ where: { userId } }),
  ]);

  const exportPayload = {
    exportedAt: new Date().toISOString(),
    profile,
    careerExperiences,
    projects,
    evidence,
    skills,
    certifications,
    courses,
    education,
    leadershipExperiences,
    leadershipStories,
    internationalExperiences,
    mbaPrograms,
    mbaApplications,
    goals,
    roadmaps,
    tasks,
    financialPlan,
    financialTransactions,
  };

  return new NextResponse(JSON.stringify(exportPayload, null, 2), {
    headers: {
      "content-type": "application/json",
      "content-disposition": `attachment; filename="mba-compass-export-${new Date().toISOString().slice(0, 10)}.json"`,
    },
  });
}
