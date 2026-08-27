import Link from "next/link";
import {
  Target,
  Gauge,
  Briefcase,
  Globe2,
  Award,
  Wallet,
  ArrowUpRight,
  ExternalLink,
  CircleAlert,
} from "lucide-react";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { computeReadiness } from "@/lib/scoring/engine";
import { gatherScoringInputs } from "@/app/(app)/mba-readiness/gather";

const PRIORITY_ORDER: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };

export default async function DashboardPage() {
  const userId = await requireUserId();

  const [
    profile,
    primaryProgram,
    careerExperiences,
    projectCount,
    leadershipCount,
    countries,
    certifications,
    courses,
    openTasks,
    financialPlan,
  ] = await Promise.all([
    prisma.profile.findUnique({ where: { userId } }),
    prisma.mBAProgram.findFirst({
      where: { userId, isPrimaryTarget: true, isArchived: false },
      include: { deadlines: { orderBy: { deadline: "asc" }, take: 1 }, dimensionWeights: true },
    }),
    prisma.careerExperience.findMany({ where: { userId }, select: { company: true } }),
    prisma.project.count({ where: { userId } }),
    prisma.leadershipExperience.count({ where: { userId } }),
    prisma.internationalExperience.findMany({ where: { userId }, select: { country: true }, distinct: ["country"] }),
    prisma.certification.findMany({ where: { userId }, select: { status: true } }),
    prisma.course.findMany({ where: { userId }, select: { hours: true, completedAt: true } }),
    prisma.task.findMany({
      where: { userId, status: { not: "DONE" } },
      orderBy: [{ deadline: "asc" }],
      take: 20,
    }),
    prisma.financialPlan.findFirst({ where: { userId } }),
  ]);

  const readiness = primaryProgram
    ? await (async () => {
        const [dimensions, inputs] = await Promise.all([
          prisma.scoringDimension.findMany({ orderBy: { sortOrder: "asc" } }),
          gatherScoringInputs(userId),
        ]);
        const weightMap = new Map(primaryProgram.dimensionWeights.map((w) => [w.dimensionKey, Number(w.weight)]));
        const config = dimensions.map((d) => ({
          key: d.key,
          label: d.label,
          weight: weightMap.get(d.key) ?? Number(d.defaultWeight),
        }));
        return computeReadiness(inputs, config);
      })()
    : null;

  const distinctCompanies = new Set(careerExperiences.map((c) => c.company)).size;
  const certsCompleted = certifications.filter((c) => c.status === "PASSED").length;
  const certsInProgress = certifications.filter(
    (c) => c.status === "IN_PROGRESS" || c.status === "EXAM_SCHEDULED",
  ).length;
  const coursesCompleted = courses.filter((c) => c.completedAt).length;
  const learningHours = courses.reduce((sum, c) => sum + Number(c.hours ?? 0), 0);

  const topActions = [...openTasks]
    .sort((a, b) => {
      const p = (PRIORITY_ORDER[a.priority] ?? 9) - (PRIORITY_ORDER[b.priority] ?? 9);
      if (p !== 0) return p;
      if (a.deadline && b.deadline) return a.deadline.getTime() - b.deadline.getTime();
      if (a.deadline) return -1;
      if (b.deadline) return 1;
      return 0;
    })
    .slice(0, 3);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={`Welcome back${profile?.fullName ? `, ${profile.fullName.split(" ")[0]}` : ""}.`}
        description="Where you stand, where you're going, and what to do next."
      />

      {/* Primary MBA target */}
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <Target className="size-4 text-muted-foreground" /> Primary MBA target
              </CardTitle>
              <CardDescription>The school and intake this whole plan is built around.</CardDescription>
            </div>
            <Button asChild variant="outline" size="sm">
              <Link href="/mba-targets">
                Manage targets <ArrowUpRight className="size-3.5" />
              </Link>
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {primaryProgram ? (
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-lg font-semibold">
                  {primaryProgram.schoolName} — {primaryProgram.programName}
                </p>
                <p className="text-sm text-muted-foreground">
                  {primaryProgram.city ? `${primaryProgram.city}, ` : ""}
                  {primaryProgram.country} · Target intake: {primaryProgram.targetIntake ?? "TBD"}
                </p>
                {primaryProgram.lastVerifiedAt && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Last verified: {primaryProgram.lastVerifiedAt.toLocaleDateString("en-GB", {
                      year: "numeric",
                      month: "long",
                      day: "numeric",
                    })}
                  </p>
                )}
              </div>
              {primaryProgram.deadlines[0] && (
                <Badge variant="secondary" className="w-fit">
                  Next deadline: {primaryProgram.deadlines[0].round} ·{" "}
                  {primaryProgram.deadlines[0].deadline.toLocaleDateString("en-GB", {
                    year: "numeric",
                    month: "short",
                    day: "numeric",
                  })}
                </Badge>
              )}
            </div>
          ) : (
            <EmptyState
              icon={Target}
              title="No primary target set"
              description="Add an MBA program and mark it as your primary target to anchor the rest of the app around it."
              action={
                <Button asChild size="sm">
                  <Link href="/mba-targets">Add a program</Link>
                </Button>
              }
            />
          )}
        </CardContent>
      </Card>

      {/* Readiness score */}
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <Gauge className="size-4 text-muted-foreground" /> MBA Readiness
              </CardTitle>
              <CardDescription>
                A preparation/readiness score against your configured criteria — not an admission
                probability.
              </CardDescription>
            </div>
            {readiness && (
              <Button asChild variant="outline" size="sm">
                <Link href="/mba-readiness">
                  Full breakdown <ArrowUpRight className="size-3.5" />
                </Link>
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {readiness ? (
            <div className="flex flex-col gap-4">
              <div className="flex items-center gap-4">
                <p className="text-4xl font-semibold tabular-nums">{readiness.totalScore}</p>
                <p className="text-sm text-muted-foreground">/ 100</p>
              </div>
              {[...readiness.dimensions]
                .sort((a, b) => b.weight * (100 - b.score) - a.weight * (100 - a.score))
                .slice(0, 3)
                .map((d) => (
                  <div key={d.key} className="flex flex-col gap-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium text-foreground">{d.label}</span>
                      <span className="text-muted-foreground">{d.score}/100</span>
                    </div>
                    <Progress value={d.score} />
                  </div>
                ))}
            </div>
          ) : (
            <EmptyState
              icon={Gauge}
              title="Set a primary MBA target"
              description="Mark a program as your primary target to compute your readiness score against it."
              action={
                <Button asChild size="sm">
                  <Link href="/mba-targets">Go to MBA Targets</Link>
                </Button>
              }
            />
          )}
        </CardContent>
      </Card>

      {/* Next best actions */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <CircleAlert className="size-4 text-muted-foreground" /> What to do next
          </CardTitle>
          <CardDescription>Your highest-priority open tasks, soonest deadline first.</CardDescription>
        </CardHeader>
        <CardContent>
          {topActions.length > 0 ? (
            <ul className="flex flex-col gap-3">
              {topActions.map((task) => (
                <li key={task.id} className="flex items-start justify-between gap-3 rounded-lg border p-3">
                  <div>
                    <p className="text-sm font-medium">{task.title}</p>
                    <p className="text-xs text-muted-foreground">
                      {task.category ?? "General"}
                      {task.deadline &&
                        ` · Due ${task.deadline.toLocaleDateString("en-GB", { day: "numeric", month: "short" })}`}
                    </p>
                  </div>
                  <Badge
                    variant={
                      task.priority === "CRITICAL" || task.priority === "HIGH" ? "destructive" : "secondary"
                    }
                  >
                    {task.priority}
                  </Badge>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No open tasks" description="You're all caught up — add tasks from the Tasks page." />
          )}
        </CardContent>
      </Card>

      {/* Snapshots */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <SnapshotCard
          icon={Briefcase}
          title="Career snapshot"
          rows={[
            ["Current role", profile?.currentJobTitle ?? "—"],
            ["Companies", String(distinctCompanies)],
            ["Years of experience", profile?.yearsOfExperience?.toString() ?? "—"],
            ["Projects logged", String(projectCount)],
            ["Leadership experiences", String(leadershipCount)],
          ]}
          href="/career"
        />
        <SnapshotCard
          icon={Globe2}
          title="International exposure"
          rows={[["Countries", String(countries.length)]]}
          href="/international"
        />
        <SnapshotCard
          icon={Award}
          title="Learning snapshot"
          rows={[
            ["Certifications completed", String(certsCompleted)],
            ["Certifications in progress", String(certsInProgress)],
            ["Courses completed", String(coursesCompleted)],
            ["Learning hours logged", String(learningHours)],
          ]}
          href="/certifications"
        />
      </div>

      {/* Financial snapshot */}
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <Wallet className="size-4 text-muted-foreground" /> Financial snapshot
              </CardTitle>
              <CardDescription>Estimated cost, planned funding and the gap.</CardDescription>
            </div>
            {financialPlan && (
              <Button asChild variant="outline" size="sm">
                <Link href="/financial-plan">
                  Full plan <ArrowUpRight className="size-3.5" />
                </Link>
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {financialPlan ? (
            (() => {
              const totalCost =
                Number(financialPlan.tuition ?? 0) +
                Number(financialPlan.livingCost ?? 0) +
                Number(financialPlan.travelCost ?? 0) +
                Number(financialPlan.visaCost ?? 0) +
                Number(financialPlan.insuranceCost ?? 0) +
                Number(financialPlan.otherCost ?? 0);
              const plannedFunding =
                Number(financialPlan.currentSavings) +
                Number(financialPlan.scholarshipTarget) +
                Number(financialPlan.employerSponsorship) +
                Number(financialPlan.studentLoanTarget) +
                Number(financialPlan.familySupport);
              const gap = totalCost - plannedFunding;
              return (
                <div className="grid grid-cols-3 gap-4 text-sm">
                  <div>
                    <p className="text-xs text-muted-foreground">Estimated cost</p>
                    <p className="font-medium tabular-nums">
                      {totalCost.toLocaleString()} {financialPlan.currency}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Planned funding</p>
                    <p className="font-medium tabular-nums">
                      {plannedFunding.toLocaleString()} {financialPlan.currency}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">{gap > 0 ? "Gap" : "Surplus"}</p>
                    <p className="font-medium tabular-nums">
                      {Math.abs(gap).toLocaleString()} {financialPlan.currency}
                    </p>
                  </div>
                </div>
              );
            })()
          ) : (
            <EmptyState
              icon={Wallet}
              title="Financial plan not set up yet"
              description="Estimate the total cost, funding sources and a savings projection."
              action={
                <Button asChild size="sm">
                  <Link href="/financial-plan">Set up financial plan</Link>
                </Button>
              }
            />
          )}
        </CardContent>
      </Card>

      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <ExternalLink className="size-3" /> Every score and recommendation in MBA Compass is traceable back
        to the data you enter — nothing is fabricated.
      </p>
    </div>
  );
}

function SnapshotCard({
  icon: Icon,
  title,
  rows,
  href,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  rows: [string, string][];
  href: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <Icon className="size-4 text-muted-foreground" /> {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="flex flex-col gap-2">
          {rows.map(([label, value]) => (
            <div key={label} className="flex items-center justify-between text-sm">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="font-medium tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>
        <Separator className="my-3" />
        <Link href={href} className="text-xs font-medium text-primary hover:underline">
          View details →
        </Link>
      </CardContent>
    </Card>
  );
}
