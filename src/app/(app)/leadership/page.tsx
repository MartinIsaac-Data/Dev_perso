import { Users } from "lucide-react";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { DeleteButton } from "@/components/shared/delete-button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { humanize } from "@/lib/labels";
import { LeadershipFormDialog } from "@/app/(app)/leadership/leadership-form";
import { deleteLeadership } from "@/app/(app)/leadership/actions";

function fmtDate(d: Date | null) {
  return d ? d.toLocaleDateString("en-GB", { year: "numeric", month: "short" }) : "";
}

export default async function LeadershipPage() {
  const userId = await requireUserId();
  const records = await prisma.leadershipExperience.findMany({
    where: { userId },
    orderBy: [{ isOngoing: "desc" }, { startDate: "desc" }],
  });

  return (
    <div>
      <PageHeader
        title="Leadership"
        description="Your leadership portfolio — project leadership, team management, mentoring and community work."
        actions={<LeadershipFormDialog mode="create" />}
      />

      {records.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No leadership experiences yet"
          description="Add the experiences that show scope, duration, team size and impact."
          action={<LeadershipFormDialog mode="create" />}
        />
      ) : (
        <div className="flex flex-col gap-3">
          {records.map((r) => (
            <Card key={r.id}>
              <CardContent className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-semibold">{r.title}</p>
                    <Badge variant="secondary">{humanize(r.type)}</Badge>
                    {r.isOngoing && <Badge variant="success">Ongoing</Badge>}
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {r.organization}
                    {r.role ? ` · ${r.role}` : ""}
                    {r.teamSize ? ` · Team of ${r.teamSize}` : ""}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {fmtDate(r.startDate)}
                    {r.startDate && (r.endDate || r.isOngoing) ? " – " : ""}
                    {r.isOngoing ? "Present" : fmtDate(r.endDate)}
                  </p>
                  {r.results && <p className="mt-2 text-sm">{r.results}</p>}
                </div>
                <div className="flex shrink-0">
                  <LeadershipFormDialog
                    mode="edit"
                    leadershipId={r.id}
                    initialValues={{
                      type: r.type,
                      title: r.title,
                      organization: r.organization ?? "",
                      role: r.role ?? "",
                      teamSize: r.teamSize?.toString() ?? "",
                      startDate: r.startDate ? r.startDate.toISOString().slice(0, 10) : "",
                      endDate: r.endDate ? r.endDate.toISOString().slice(0, 10) : "",
                      isOngoing: r.isOngoing,
                      responsibilities: r.responsibilities ?? "",
                      results: r.results ?? "",
                      skillsUsed: r.skillsUsed.join(", "),
                    }}
                  />
                  <DeleteButton itemLabel={r.title} action={deleteLeadership.bind(null, r.id)} />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
