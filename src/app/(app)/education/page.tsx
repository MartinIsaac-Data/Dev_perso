import { GraduationCap } from "lucide-react";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { DeleteButton } from "@/components/shared/delete-button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EducationFormDialog } from "@/app/(app)/education/education-form";
import { deleteEducation } from "@/app/(app)/education/actions";

function fmtYear(d: Date | null) {
  return d ? d.getFullYear().toString() : "Present";
}

export default async function EducationPage() {
  const userId = await requireUserId();
  const records = await prisma.education.findMany({
    where: { userId },
    orderBy: { startDate: "desc" },
  });

  return (
    <div>
      <PageHeader
        title="Education"
        description="Degrees, coursework and academic honors."
        actions={<EducationFormDialog mode="create" />}
      />

      {records.length === 0 ? (
        <EmptyState
          icon={GraduationCap}
          title="No education records yet"
          description="Add your degrees and relevant coursework."
          action={<EducationFormDialog mode="create" />}
        />
      ) : (
        <div className="flex flex-col gap-3">
          {records.map((r) => (
            <Card key={r.id}>
              <CardContent className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold">{r.degree}</p>
                  <p className="text-sm text-muted-foreground">
                    {r.university}
                    {r.field ? ` · ${r.field}` : ""}
                    {r.country ? ` · ${r.country}` : ""}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {fmtYear(r.startDate)} – {fmtYear(r.endDate)}
                    {r.gradeGpa ? ` · ${r.gradeGpa}` : ""}
                    {r.honors ? ` · ${r.honors}` : ""}
                  </p>
                  {r.relevantCoursework.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {r.relevantCoursework.map((course) => (
                        <Badge key={course} variant="outline">
                          {course}
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex shrink-0">
                  <EducationFormDialog
                    mode="edit"
                    educationId={r.id}
                    initialValues={{
                      degree: r.degree,
                      university: r.university,
                      field: r.field ?? "",
                      country: r.country ?? "",
                      startDate: r.startDate ? r.startDate.toISOString().slice(0, 10) : "",
                      endDate: r.endDate ? r.endDate.toISOString().slice(0, 10) : "",
                      gradeGpa: r.gradeGpa ?? "",
                      honors: r.honors ?? "",
                      relevantCoursework: r.relevantCoursework.join(", "),
                      documentUrl: r.documentUrl ?? "",
                    }}
                  />
                  <DeleteButton itemLabel={r.degree} action={deleteEducation.bind(null, r.id)} />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
