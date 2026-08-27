import { Archive } from "lucide-react";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { DeleteButton } from "@/components/shared/delete-button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { humanize } from "@/lib/labels";
import { EvidenceFormDialog } from "@/app/(app)/evidence/evidence-form";
import { deleteEvidence } from "@/app/(app)/evidence/actions";

export default async function EvidencePage() {
  const userId = await requireUserId();
  const [records, projects, certifications] = await Promise.all([
    prisma.evidence.findMany({
      where: { userId },
      orderBy: { date: "desc" },
      include: { project: { select: { name: true } }, certification: { select: { name: true } } },
    }),
    prisma.project.findMany({ where: { userId }, select: { id: true, name: true } }),
    prisma.certification.findMany({ where: { userId }, select: { id: true, name: true } }),
  ]);

  return (
    <div>
      <PageHeader
        title="Evidence Bank"
        description="Connect achievements to the proof behind them — dashboards, reviews, KPI reports."
        actions={
          <EvidenceFormDialog mode="create" projects={projects} certifications={certifications} />
        }
      />

      {records.length === 0 ? (
        <EmptyState
          icon={Archive}
          title="No evidence saved yet"
          description="Attach the proof behind your achievements so you don't forget it years later."
          action={
            <EvidenceFormDialog mode="create" projects={projects} certifications={certifications} />
          }
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {records.map((r) => (
            <Card key={r.id}>
              <CardContent className="flex flex-col gap-2">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold">{r.title}</p>
                    <Badge variant="secondary" className="mt-1">
                      {humanize(r.type)}
                    </Badge>
                  </div>
                  <div className="flex shrink-0">
                    <EvidenceFormDialog
                      mode="edit"
                      evidenceId={r.id}
                      projects={projects}
                      certifications={certifications}
                      initialValues={{
                        title: r.title,
                        type: r.type,
                        date: r.date ? r.date.toISOString().slice(0, 10) : "",
                        description: r.description ?? "",
                        tags: r.tags.join(", "),
                        fileUrl: r.fileUrl ?? "",
                        projectId: r.projectId ?? "none",
                        certificationId: r.certificationId ?? "none",
                      }}
                    />
                    <DeleteButton itemLabel={r.title} action={deleteEvidence.bind(null, r.id)} />
                  </div>
                </div>
                {(r.project || r.certification) && (
                  <p className="text-xs text-muted-foreground">
                    Linked to: {r.project?.name}
                    {r.project && r.certification ? " · " : ""}
                    {r.certification?.name}
                  </p>
                )}
                {r.description && <p className="text-sm text-muted-foreground">{r.description}</p>}
                {r.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {r.tags.map((tag) => (
                      <Badge key={tag} variant="outline">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
