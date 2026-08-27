import Link from "next/link";
import { FileCheck2 } from "lucide-react";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { DeleteButton } from "@/components/shared/delete-button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { APPLICATION_STATUS_BADGE_VARIANT, humanize } from "@/lib/labels";
import { ApplicationFormDialog } from "@/app/(app)/mba-application/application-form";
import { deleteApplication } from "@/app/(app)/mba-application/actions";

const CHECKLIST_KEYS = [
  "cvReady",
  "essaysReady",
  "recommendationsReady",
  "transcriptReady",
  "testScoreReady",
  "englishTestReady",
  "passportReady",
] as const;

export default async function MBAApplicationPage() {
  const userId = await requireUserId();
  const [applications, programs] = await Promise.all([
    prisma.mBAApplication.findMany({
      where: { userId },
      orderBy: { deadline: "asc" },
      include: { program: { select: { schoolName: true, programName: true } } },
    }),
    prisma.mBAProgram.findMany({
      where: { userId, isArchived: false },
      select: { id: true, schoolName: true, programName: true },
    }),
  ]);

  if (programs.length === 0) {
    return (
      <div>
        <PageHeader
          title="MBA Application"
          description="Track applications per school — round, deadline, status and document checklist."
        />
        <EmptyState
          icon={FileCheck2}
          title="Add an MBA program first"
          description="Applications are tracked against a specific program in MBA Targets."
          action={
            <Button asChild size="sm">
              <Link href="/mba-targets">Go to MBA Targets</Link>
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="MBA Application"
        description="Track applications per school — round, deadline, status and document checklist."
        actions={<ApplicationFormDialog mode="create" programs={programs} />}
      />

      {applications.length === 0 ? (
        <EmptyState
          icon={FileCheck2}
          title="No applications tracked yet"
          description="Add an application once you're ready to start preparing for a specific round."
          action={<ApplicationFormDialog mode="create" programs={programs} />}
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {applications.map((app) => {
            const done = CHECKLIST_KEYS.filter((k) => app[k]).length;
            const pct = Math.round((done / CHECKLIST_KEYS.length) * 100);
            return (
              <Card key={app.id}>
                <CardContent className="flex flex-col gap-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold">
                        {app.program.schoolName} — {app.program.programName}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {app.intake}
                        {app.round ? ` · ${app.round}` : ""}
                        {app.deadline
                          ? ` · Due ${app.deadline.toLocaleDateString("en-GB", { year: "numeric", month: "short", day: "numeric" })}`
                          : ""}
                      </p>
                    </div>
                    <div className="flex shrink-0">
                      <ApplicationFormDialog
                        mode="edit"
                        applicationId={app.id}
                        programs={programs}
                        initialValues={{
                          programId: app.programId,
                          intake: app.intake ?? "",
                          round: app.round ?? "",
                          deadline: app.deadline ? app.deadline.toISOString().slice(0, 10) : "",
                          status: app.status,
                          cvReady: app.cvReady,
                          essaysReady: app.essaysReady,
                          recommendationsReady: app.recommendationsReady,
                          transcriptReady: app.transcriptReady,
                          testScoreReady: app.testScoreReady,
                          englishTestReady: app.englishTestReady,
                          passportReady: app.passportReady,
                          notes: app.notes ?? "",
                        }}
                      />
                      <DeleteButton
                        itemLabel={`${app.program.schoolName} application`}
                        action={deleteApplication.bind(null, app.id)}
                      />
                    </div>
                  </div>
                  <Badge variant={APPLICATION_STATUS_BADGE_VARIANT[app.status]} className="w-fit">
                    {humanize(app.status)}
                  </Badge>
                  <div>
                    <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
                      <span>Document checklist</span>
                      <span>
                        {done}/{CHECKLIST_KEYS.length}
                      </span>
                    </div>
                    <Progress value={pct} />
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
