import { Rocket } from "lucide-react";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { DeleteButton } from "@/components/shared/delete-button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ProjectFormDialog } from "@/app/(app)/projects/project-form";
import { ImpactPanel } from "@/app/(app)/projects/impact-panel";
import { deleteProject } from "@/app/(app)/projects/actions";

function fmtDate(d: Date | null) {
  return d ? d.toLocaleDateString("en-GB", { year: "numeric", month: "short" }) : "";
}

export default async function ProjectsPage() {
  const userId = await requireUserId();
  const [projects, careerExperiences] = await Promise.all([
    prisma.project.findMany({
      where: { userId },
      orderBy: { date: "desc" },
      include: { impacts: true },
    }),
    prisma.careerExperience.findMany({
      where: { userId },
      select: { id: true, company: true, role: true },
      orderBy: { startDate: "desc" },
    }),
  ]);

  return (
    <div>
      <PageHeader
        title="Projects & Impact"
        description="Every professional project, with measurable before/after impact and evidence."
        actions={<ProjectFormDialog mode="create" careerExperiences={careerExperiences} />}
      />

      {projects.length === 0 ? (
        <EmptyState
          icon={Rocket}
          title="No projects logged yet"
          description="Record the problem, your actions and the measurable result — this is the raw material for MBA essays and the readiness engine."
          action={<ProjectFormDialog mode="create" careerExperiences={careerExperiences} />}
        />
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {projects.map((p) => (
            <Card key={p.id}>
              <CardContent>
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold">{p.name}</p>
                    <p className="text-sm text-muted-foreground">
                      {p.company}
                      {p.date ? ` · ${fmtDate(p.date)}` : ""}
                      {p.role ? ` · ${p.role}` : ""}
                    </p>
                    {p.result && <p className="mt-2 text-sm">{p.result}</p>}
                    {(p.tools.length > 0 || p.countries.length > 0) && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {p.tools.map((t) => (
                          <Badge key={`t-${t}`} variant="outline">
                            {t}
                          </Badge>
                        ))}
                        {p.countries.map((c) => (
                          <Badge key={`c-${c}`} variant="secondary">
                            {c}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex shrink-0">
                    <ProjectFormDialog
                      mode="edit"
                      projectId={p.id}
                      careerExperiences={careerExperiences}
                      initialValues={{
                        name: p.name,
                        company: p.company ?? "",
                        date: p.date ? p.date.toISOString().slice(0, 10) : "",
                        problem: p.problem ?? "",
                        context: p.context ?? "",
                        objective: p.objective ?? "",
                        actions: p.actions ?? "",
                        role: p.role ?? "",
                        stakeholders: p.stakeholders.join(", "),
                        skillsUsed: p.skillsUsed.join(", "),
                        tools: p.tools.join(", "),
                        countries: p.countries.join(", "),
                        result: p.result ?? "",
                        mbaRelevance: p.mbaRelevance ?? "",
                        careerExperienceId: p.careerExperienceId ?? "none",
                      }}
                    />
                    <DeleteButton itemLabel={p.name} action={deleteProject.bind(null, p.id)} />
                  </div>
                </div>
                <ImpactPanel
                  projectId={p.id}
                  impacts={p.impacts.map((i) => ({
                    id: i.id,
                    category: i.category,
                    metricName: i.metricName,
                    beforeValue: i.beforeValue?.toString() ?? null,
                    afterValue: i.afterValue?.toString() ?? null,
                    unit: i.unit,
                    annualizedValue: i.annualizedValue?.toString() ?? null,
                    narrative: i.narrative,
                  }))}
                />
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
