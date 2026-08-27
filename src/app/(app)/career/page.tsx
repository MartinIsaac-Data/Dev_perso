import { Briefcase } from "lucide-react";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { KpiCard } from "@/components/shared/kpi-card";
import { DeleteButton } from "@/components/shared/delete-button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { humanize } from "@/lib/labels";
import { ExperienceFormDialog } from "@/app/(app)/career/experience-form";
import { AchievementPanel } from "@/app/(app)/career/achievement-panel";
import { deleteExperience } from "@/app/(app)/career/actions";

function fmtDate(d: Date | null) {
  return d ? d.toLocaleDateString("en-GB", { year: "numeric", month: "short" }) : "";
}

export default async function CareerPage() {
  const userId = await requireUserId();
  const experiences = await prisma.careerExperience.findMany({
    where: { userId },
    orderBy: [{ isCurrent: "desc" }, { startDate: "desc" }],
    include: { achievements: { orderBy: { date: "desc" } } },
  });

  const distinctCompanies = new Set(experiences.map((e) => e.company)).size;
  const totalMonths = experiences.reduce((sum, e) => {
    const end = e.endDate ?? new Date();
    const months = (end.getFullYear() - e.startDate.getFullYear()) * 12 + (end.getMonth() - e.startDate.getMonth());
    return sum + Math.max(months, 0);
  }, 0);
  const countries = new Set(experiences.flatMap((e) => e.countriesCovered)).size;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Career"
        description="Your career timeline — companies, roles, responsibilities and achievements."
        actions={<ExperienceFormDialog mode="create" />}
      />

      {experiences.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-3">
          <KpiCard label="Companies" value={distinctCompanies} icon={Briefcase} />
          <KpiCard label="Total experience" value={`${(totalMonths / 12).toFixed(1)} yrs`} />
          <KpiCard label="Countries covered" value={countries} />
        </div>
      )}

      {experiences.length === 0 ? (
        <EmptyState
          icon={Briefcase}
          title="No career experience logged yet"
          description="Add your roles — this feeds the Career Snapshot and, later, the MBA readiness engine."
          action={<ExperienceFormDialog mode="create" />}
        />
      ) : (
        <div className="flex flex-col gap-3">
          {experiences.map((exp) => (
            <Card key={exp.id}>
              <CardContent>
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold">{exp.role}</p>
                      {exp.isCurrent && <Badge variant="success">Current</Badge>}
                      <Badge variant="outline">{humanize(exp.employmentType)}</Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {exp.company}
                      {exp.department ? ` · ${exp.department}` : ""}
                      {exp.location ? ` · ${exp.location}` : ""}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {fmtDate(exp.startDate)} – {exp.isCurrent ? "Present" : fmtDate(exp.endDate)}
                      {exp.teamSize ? ` · Team of ${exp.teamSize}` : ""}
                      {exp.manager ? ` · Reports to ${exp.manager}` : ""}
                    </p>
                    {exp.responsibilities && (
                      <p className="mt-2 text-sm text-muted-foreground">{exp.responsibilities}</p>
                    )}
                    {(exp.countriesCovered.length > 0 || exp.skillsUsed.length > 0) && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {exp.countriesCovered.map((c) => (
                          <Badge key={`c-${c}`} variant="secondary">
                            {c}
                          </Badge>
                        ))}
                        {exp.skillsUsed.map((s) => (
                          <Badge key={`s-${s}`} variant="outline">
                            {s}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex shrink-0">
                    <ExperienceFormDialog
                      mode="edit"
                      experienceId={exp.id}
                      initialValues={{
                        company: exp.company,
                        role: exp.role,
                        department: exp.department ?? "",
                        location: exp.location ?? "",
                        startDate: exp.startDate.toISOString().slice(0, 10),
                        endDate: exp.endDate ? exp.endDate.toISOString().slice(0, 10) : "",
                        isCurrent: exp.isCurrent,
                        employmentType: exp.employmentType,
                        responsibilities: exp.responsibilities ?? "",
                        teamSize: exp.teamSize?.toString() ?? "",
                        manager: exp.manager ?? "",
                        countriesCovered: exp.countriesCovered.join(", "),
                        skillsUsed: exp.skillsUsed.join(", "),
                      }}
                    />
                    <DeleteButton
                      itemLabel={`${exp.role} at ${exp.company}`}
                      action={deleteExperience.bind(null, exp.id)}
                    />
                  </div>
                </div>
                <AchievementPanel careerExperienceId={exp.id} achievements={exp.achievements} />
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
