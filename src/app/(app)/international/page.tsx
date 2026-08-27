import { Globe2 } from "lucide-react";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { DeleteButton } from "@/components/shared/delete-button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { humanize } from "@/lib/labels";
import { InternationalFormDialog } from "@/app/(app)/international/international-form";
import { deleteInternational } from "@/app/(app)/international/actions";

export default async function InternationalPage() {
  const userId = await requireUserId();
  const records = await prisma.internationalExperience.findMany({
    where: { userId },
    orderBy: [{ country: "asc" }],
  });
  const countries = [...new Set(records.map((r) => r.country))];

  return (
    <div>
      <PageHeader
        title="International Exposure"
        description="Countries you've worked with, international projects and multicultural teams."
        actions={<InternationalFormDialog mode="create" />}
      />

      {records.length === 0 ? (
        <EmptyState
          icon={Globe2}
          title="No international exposure logged yet"
          description="Add the countries, projects and stakeholders you've worked across."
          action={<InternationalFormDialog mode="create" />}
        />
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-2">
            {countries.map((c) => (
              <Badge key={c} variant="secondary">
                {c}
              </Badge>
            ))}
          </div>
          <div className="flex flex-col gap-3">
            {records.map((r) => (
              <Card key={r.id}>
                <CardContent className="flex items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold">{r.country}</p>
                      <Badge variant="outline">{humanize(r.type)}</Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {r.company}
                      {r.project ? ` · ${r.project}` : ""}
                      {r.role ? ` · ${r.role}` : ""}
                    </p>
                  </div>
                  <div className="flex shrink-0">
                    <InternationalFormDialog
                      mode="edit"
                      recordId={r.id}
                      initialValues={{
                        country: r.country,
                        company: r.company ?? "",
                        project: r.project ?? "",
                        role: r.role ?? "",
                        type: r.type,
                        startDate: r.startDate ? r.startDate.toISOString().slice(0, 10) : "",
                        endDate: r.endDate ? r.endDate.toISOString().slice(0, 10) : "",
                        team: r.team ?? "",
                        responsibilities: r.responsibilities ?? "",
                      }}
                    />
                    <DeleteButton itemLabel={r.country} action={deleteInternational.bind(null, r.id)} />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
