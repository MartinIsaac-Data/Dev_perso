import { Target } from "lucide-react";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { DeleteButton } from "@/components/shared/delete-button";
import { humanize } from "@/lib/labels";
import { ProgramFormDialog } from "@/app/(app)/mba-targets/program-form";
import { DeadlinePanel } from "@/app/(app)/mba-targets/deadline-panel";
import { ScholarshipPanel } from "@/app/(app)/mba-targets/scholarship-panel";
import { WeightsDialog } from "@/app/(app)/mba-targets/weights-dialog";
import { SetPrimaryButton, ArchiveToggleButton } from "@/app/(app)/mba-targets/program-actions";
import { deleteProgram } from "@/app/(app)/mba-targets/actions";

function fmtDate(d: Date | null) {
  return d ? d.toLocaleDateString("en-GB", { year: "numeric", month: "long", day: "numeric" }) : null;
}

export default async function MBATargetsPage() {
  const userId = await requireUserId();
  const programs = await prisma.mBAProgram.findMany({
    where: { userId },
    orderBy: [{ isArchived: "asc" }, { isPrimaryTarget: "desc" }, { targetYear: "asc" }],
    include: {
      deadlines: { orderBy: { deadline: "asc" } },
      scholarships: { orderBy: { name: "asc" } },
      dimensionWeights: true,
    },
  });
  const dimensions = await prisma.scoringDimension.findMany({ orderBy: { sortOrder: "asc" } });

  const active = programs.filter((p) => !p.isArchived);
  const archived = programs.filter((p) => p.isArchived);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="MBA Targets"
        description="The schools and programs you're targeting — requirements, deadlines and scholarships."
        actions={<ProgramFormDialog mode="create" />}
      />

      {programs.length === 0 ? (
        <EmptyState
          icon={Target}
          title="No MBA programs yet"
          description="Add the schools you're considering — mark one as your primary target to anchor the dashboard and readiness engine."
          action={<ProgramFormDialog mode="create" />}
        />
      ) : (
        <div className="flex flex-col gap-4">
          {active.map((program) => {
            const weightMap = new Map(program.dimensionWeights.map((w) => [w.dimensionKey, Number(w.weight)]));
            const dimensionWeights = dimensions.map((d) => ({
              key: d.key,
              label: d.label,
              weight: weightMap.get(d.key) ?? Number(d.defaultWeight),
            }));
            const totalCost =
              (program.tuition ? Number(program.tuition) : 0) +
              (program.estimatedLivingCost ? Number(program.estimatedLivingCost) : 0);

            return (
              <Card key={program.id}>
                <CardContent className="flex flex-col gap-4">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-base font-semibold">
                          {program.schoolName} — {program.programName}
                        </p>
                        {program.isPrimaryTarget && <Badge>Primary target</Badge>}
                        <Badge variant="secondary">{humanize(program.programType)}</Badge>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {program.city ? `${program.city}, ` : ""}
                        {program.country}
                        {program.durationMonths ? ` · ${program.durationMonths} months` : ""}
                        {program.targetIntake ? ` · Target intake: ${program.targetIntake}` : ""}
                      </p>
                      {fmtDate(program.lastVerifiedAt) && (
                        <p className="mt-1 text-xs text-muted-foreground">
                          Last verified: {fmtDate(program.lastVerifiedAt)}
                          {program.sourceUrl ? ` · ${program.sourceUrl}` : ""}
                        </p>
                      )}
                    </div>
                    <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
                      <SetPrimaryButton programId={program.id} isPrimary={program.isPrimaryTarget} />
                      <WeightsDialog programId={program.id} dimensions={dimensionWeights} />
                      <ProgramFormDialog
                        mode="edit"
                        programId={program.id}
                        initialValues={{
                          schoolName: program.schoolName,
                          programName: program.programName,
                          country: program.country ?? "",
                          city: program.city ?? "",
                          campus: program.campus ?? "",
                          programType: program.programType,
                          durationMonths: program.durationMonths?.toString() ?? "",
                          tuition: program.tuition?.toString() ?? "",
                          estimatedLivingCost: program.estimatedLivingCost?.toString() ?? "",
                          currency: program.currency,
                          minExperienceYears: program.minExperienceYears?.toString() ?? "",
                          avgExperienceYears: program.avgExperienceYears?.toString() ?? "",
                          gmatRequirement: program.gmatRequirement ?? "",
                          greRequirement: program.greRequirement ?? "",
                          englishRequirement: program.englishRequirement ?? "",
                          officialWebsite: program.officialWebsite ?? "",
                          notes: program.notes ?? "",
                          targetIntake: program.targetIntake ?? "",
                          targetYear: program.targetYear?.toString() ?? "",
                          lastVerifiedAt: program.lastVerifiedAt
                            ? program.lastVerifiedAt.toISOString().slice(0, 10)
                            : "",
                          sourceUrl: program.sourceUrl ?? "",
                        }}
                      />
                      <ArchiveToggleButton programId={program.id} isArchived={program.isArchived} />
                      <DeleteButton
                        itemLabel={`${program.schoolName} ${program.programName}`}
                        action={deleteProgram.bind(null, program.id)}
                      />
                    </div>
                  </div>

                  <div className="grid gap-4 text-sm sm:grid-cols-3">
                    <div>
                      <p className="text-xs text-muted-foreground">Estimated total cost</p>
                      <p className="font-medium">
                        {totalCost > 0 ? `${totalCost.toLocaleString()} ${program.currency}` : "—"}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Experience (min / avg)</p>
                      <p className="font-medium">
                        {program.minExperienceYears ? Number(program.minExperienceYears) : "—"} /{" "}
                        {program.avgExperienceYears ? Number(program.avgExperienceYears) : "—"} yrs
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">GMAT / English</p>
                      <p className="font-medium">
                        {program.gmatRequirement || "—"}
                        {program.englishRequirement ? ` · ${program.englishRequirement}` : ""}
                      </p>
                    </div>
                  </div>

                  <div className="grid gap-4 border-t pt-3 sm:grid-cols-2">
                    <DeadlinePanel programId={program.id} deadlines={program.deadlines} />
                    <ScholarshipPanel
                      programId={program.id}
                      scholarships={program.scholarships.map((s) => ({
                        id: s.id,
                        name: s.name,
                        amount: s.amount?.toString() ?? null,
                        currency: s.currency,
                        status: s.status,
                        deadline: s.deadline,
                      }))}
                    />
                  </div>
                </CardContent>
              </Card>
            );
          })}

          {archived.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-medium text-muted-foreground">Archived programs</p>
              <div className="flex flex-col gap-2">
                {archived.map((program) => (
                  <Card key={program.id} className="opacity-60">
                    <CardContent className="flex items-center justify-between">
                      <p className="text-sm">
                        {program.schoolName} — {program.programName}
                      </p>
                      <div className="flex gap-1.5">
                        <ArchiveToggleButton programId={program.id} isArchived={program.isArchived} />
                        <DeleteButton
                          itemLabel={`${program.schoolName} ${program.programName}`}
                          action={deleteProgram.bind(null, program.id)}
                        />
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
