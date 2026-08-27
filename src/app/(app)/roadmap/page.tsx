import { Map as MapIcon } from "lucide-react";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { DeleteButton } from "@/components/shared/delete-button";
import { Badge } from "@/components/ui/badge";
import { MILESTONE_STATUS_BADGE_VARIANT, PRIORITY_BADGE_VARIANT, humanize } from "@/lib/labels";
import { MilestoneFormDialog } from "@/app/(app)/roadmap/milestone-form";
import { CreateRoadmapForm } from "@/app/(app)/roadmap/create-roadmap-form";
import { deleteMilestone } from "@/app/(app)/roadmap/actions";

export default async function RoadmapPage() {
  const userId = await requireUserId();
  const [roadmap, profile] = await Promise.all([
    prisma.roadmap.findFirst({
      where: { userId, isActive: true },
      include: { milestones: { orderBy: [{ year: "asc" }, { priority: "asc" }] } },
    }),
    prisma.profile.findUnique({ where: { userId }, select: { mbaTargetYear: true } }),
  ]);

  if (!roadmap) {
    return (
      <div>
        <PageHeader
          title="Roadmap"
          description="A year-by-year plan from today to your MBA, with milestones, dependencies and KPIs."
        />
        <EmptyState
          icon={MapIcon}
          title="No roadmap yet"
          description="Create one to start planning year by year."
          action={<CreateRoadmapForm suggestedEndYear={profile?.mbaTargetYear ?? new Date().getFullYear() + 4} />}
        />
      </div>
    );
  }

  const years = Array.from(
    { length: roadmap.endYear - roadmap.startYear + 1 },
    (_, i) => roadmap.startYear + i,
  );
  const byYear = new Map<number, typeof roadmap.milestones>();
  for (const y of years) byYear.set(y, []);
  for (const m of roadmap.milestones) {
    if (!byYear.has(m.year)) byYear.set(m.year, []);
    byYear.get(m.year)!.push(m);
  }
  const milestoneTitles = roadmap.milestones.map((m) => ({ id: m.id, title: m.title }));

  return (
    <div>
      <PageHeader
        title={roadmap.name}
        description={`${roadmap.startYear} — ${roadmap.endYear}. A year-by-year plan to your MBA.`}
        actions={
          <MilestoneFormDialog
            mode="create"
            roadmapId={roadmap.id}
            defaultYear={roadmap.startYear}
            otherMilestones={milestoneTitles}
          />
        }
      />

      <div className="flex flex-col gap-6">
        {[...byYear.entries()].map(([year, milestones]) => (
          <div key={year} className="flex gap-4">
            <div className="w-16 shrink-0 pt-1 text-right">
              <span className="text-lg font-semibold tabular-nums text-muted-foreground">{year}</span>
            </div>
            <div className="flex flex-1 flex-col gap-2 border-l pl-4">
              {milestones.length === 0 ? (
                <p className="py-1 text-xs text-muted-foreground">No milestones yet.</p>
              ) : (
                milestones.map((m) => {
                  const dependsOn = m.dependsOnId
                    ? roadmap.milestones.find((x) => x.id === m.dependsOnId)
                    : null;
                  return (
                    <div key={m.id} className="flex items-start justify-between gap-3 rounded-lg border p-3">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-medium">{m.title}</p>
                          <Badge variant={MILESTONE_STATUS_BADGE_VARIANT[m.status]}>{humanize(m.status)}</Badge>
                          <Badge variant={PRIORITY_BADGE_VARIANT[m.priority]}>{humanize(m.priority)}</Badge>
                        </div>
                        {m.objective && <p className="mt-1 text-sm text-muted-foreground">{m.objective}</p>}
                        <p className="mt-1 text-xs text-muted-foreground">
                          {m.deadline &&
                            `Due ${m.deadline.toLocaleDateString("en-GB", { day: "numeric", month: "short" })}`}
                          {m.kpi ? ` · KPI: ${m.kpi}` : ""}
                          {dependsOn ? ` · Depends on: ${dependsOn.title}` : ""}
                        </p>
                      </div>
                      <div className="flex shrink-0">
                        <MilestoneFormDialog
                          mode="edit"
                          roadmapId={roadmap.id}
                          milestoneId={m.id}
                          defaultYear={year}
                          otherMilestones={milestoneTitles.filter((x) => x.id !== m.id)}
                          initialValues={{
                            year: String(m.year),
                            title: m.title,
                            objective: m.objective ?? "",
                            deadline: m.deadline ? m.deadline.toISOString().slice(0, 10) : "",
                            status: m.status,
                            priority: m.priority,
                            kpi: m.kpi ?? "",
                            dependsOnId: m.dependsOnId ?? "none",
                          }}
                        />
                        <DeleteButton itemLabel={m.title} action={deleteMilestone.bind(null, m.id)} />
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
