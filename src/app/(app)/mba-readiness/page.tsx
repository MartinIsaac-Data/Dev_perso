import Link from "next/link";
import { Gauge, Info, Target } from "lucide-react";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { computeReadiness } from "@/lib/scoring/engine";
import { gatherScoringInputs } from "@/app/(app)/mba-readiness/gather";
import { DimensionCard } from "@/app/(app)/mba-readiness/dimension-card";
import { ReadinessSimulator } from "@/app/(app)/mba-readiness/simulator";
import { SaveAssessmentButton } from "@/app/(app)/mba-readiness/save-button";

export default async function MBAReadinessPage({
  searchParams,
}: {
  searchParams: Promise<{ program?: string }>;
}) {
  const userId = await requireUserId();
  const { program: programParam } = await searchParams;

  const programs = await prisma.mBAProgram.findMany({
    where: { userId, isArchived: false },
    orderBy: [{ isPrimaryTarget: "desc" }, { schoolName: "asc" }],
    include: { dimensionWeights: true },
  });

  if (programs.length === 0) {
    return (
      <div>
        <PageHeader
          title="MBA Readiness"
          description="A preparation/readiness score against your configured criteria — not an admission probability."
        />
        <EmptyState
          icon={Target}
          title="Add an MBA program first"
          description="The readiness engine scores your profile against a specific program's weights and requirements."
          action={
            <Button asChild size="sm">
              <Link href="/mba-targets">Go to MBA Targets</Link>
            </Button>
          }
        />
      </div>
    );
  }

  const activeProgram = programs.find((p) => p.id === programParam) ?? programs[0];

  const [dimensions, inputs, lastAssessment] = await Promise.all([
    prisma.scoringDimension.findMany({ orderBy: { sortOrder: "asc" } }),
    gatherScoringInputs(userId),
    prisma.mBAAssessment.findFirst({
      where: { userId, programId: activeProgram.id, isSimulation: false },
      orderBy: { computedAt: "desc" },
    }),
  ]);

  const weightMap = new Map(activeProgram.dimensionWeights.map((w) => [w.dimensionKey, Number(w.weight)]));
  const config = dimensions.map((d) => ({
    key: d.key,
    label: d.label,
    weight: weightMap.get(d.key) ?? Number(d.defaultWeight),
  }));
  const breakdown = computeReadiness(inputs, config);

  const biggestGaps = [...breakdown.dimensions]
    .sort((a, b) => b.weight * (100 - b.score) - a.weight * (100 - a.score))
    .slice(0, 3);

  const trend = lastAssessment ? breakdown.totalScore - lastAssessment.totalScore : null;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="MBA Readiness"
        description="A preparation/readiness score against your configured criteria — not an admission probability."
        actions={<SaveAssessmentButton programId={activeProgram.id} />}
      />

      {programs.length > 1 && (
        <div className="flex flex-wrap gap-1.5">
          {programs.map((p) => (
            <Link
              key={p.id}
              href={`/mba-readiness?program=${p.id}`}
              className={cn(
                "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                p.id === activeProgram.id
                  ? "border-primary bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent",
              )}
            >
              {p.schoolName}
            </Link>
          ))}
        </div>
      )}

      <Card>
        <CardContent className="flex flex-col items-center gap-2 py-8 text-center">
          <p className="text-sm text-muted-foreground">
            {activeProgram.schoolName} — {activeProgram.programName}
          </p>
          <p className="text-6xl font-semibold tabular-nums">{breakdown.totalScore}</p>
          <p className="text-sm text-muted-foreground">out of 100</p>
          {trend !== null && trend !== 0 && (
            <Badge variant={trend > 0 ? "success" : "destructive"}>
              {trend > 0 ? "+" : ""}
              {trend} since last snapshot
            </Badge>
          )}
          <p className="mt-2 flex max-w-md items-start gap-1.5 text-xs text-muted-foreground">
            <Info className="mt-0.5 size-3.5 shrink-0" />
            This score measures how prepared your profile is against the criteria configured for this
            program. It is not an admission probability and does not predict an admissions decision.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Biggest gaps</CardTitle>
          <CardDescription>Where improving would move the total score the most.</CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="flex flex-col gap-2">
            {biggestGaps.map((d, idx) => (
              <li key={d.key} className="flex items-start gap-3 rounded-lg border p-3">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold">
                  {idx + 1}
                </span>
                <div>
                  <p className="text-sm font-medium">{d.label}</p>
                  {d.recommendations[0] && (
                    <p className="text-sm text-muted-foreground">{d.recommendations[0]}</p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      <div>
        <div className="mb-3 flex items-center gap-2">
          <Gauge className="size-4 text-muted-foreground" />
          <p className="text-sm font-medium">Dimension scores</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {breakdown.dimensions.map((d) => (
            <DimensionCard
              key={d.key}
              label={d.label}
              score={d.score}
              weight={d.weight}
              factors={d.factors}
              recommendations={d.recommendations}
            />
          ))}
        </div>
      </div>

      <ReadinessSimulator
        dimensions={breakdown.dimensions.map((d) => ({
          key: d.key,
          label: d.label,
          score: d.score,
          weight: d.weight,
        }))}
        currentTotal={breakdown.totalScore}
      />
    </div>
  );
}
