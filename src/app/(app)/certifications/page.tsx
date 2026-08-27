import { Award } from "lucide-react";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { KpiCard } from "@/components/shared/kpi-card";
import { DeleteButton } from "@/components/shared/delete-button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { CERTIFICATION_STATUS_BADGE_VARIANT, humanize } from "@/lib/labels";
import { CertificationFormDialog } from "@/app/(app)/certifications/certification-form";
import { deleteCertification } from "@/app/(app)/certifications/actions";

function fmtDate(d: Date | null) {
  return d ? d.toLocaleDateString("en-GB", { year: "numeric", month: "short", day: "numeric" }) : "—";
}

export default async function CertificationsPage() {
  const userId = await requireUserId();
  const certifications = await prisma.certification.findMany({
    where: { userId },
    orderBy: [{ status: "asc" }, { name: "asc" }],
  });

  const completed = certifications.filter((c) => c.status === "PASSED").length;
  const inProgress = certifications.filter(
    (c) => c.status === "IN_PROGRESS" || c.status === "EXAM_SCHEDULED",
  ).length;
  const now = new Date();
  const in90Days = new Date(now.getTime() + 90 * 24 * 60 * 60 * 1000);
  const expiringSoon = certifications.filter(
    (c) => c.expirationDate && c.expirationDate > now && c.expirationDate <= in90Days,
  ).length;
  const totalInvestment = certifications.reduce((sum, c) => sum + Number(c.cost ?? 0), 0);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Certifications"
        description="From planning to exam to completion — with cost and renewal tracking."
        actions={<CertificationFormDialog mode="create" />}
      />

      {certifications.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard label="Completed" value={completed} icon={Award} />
          <KpiCard label="In progress" value={inProgress} />
          <KpiCard label="Expiring within 90 days" value={expiringSoon} />
          <KpiCard label="Total investment" value={`€${totalInvestment.toLocaleString()}`} />
        </div>
      )}

      {certifications.length === 0 ? (
        <EmptyState
          icon={Award}
          title="No certifications yet"
          description="Track certifications from planning through exam to completion."
          action={<CertificationFormDialog mode="create" />}
        />
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Certification</TableHead>
                <TableHead>Provider</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Completed</TableHead>
                <TableHead>Expires</TableHead>
                <TableHead>Cost</TableHead>
                <TableHead className="w-20" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {certifications.map((c) => (
                <TableRow key={c.id}>
                  <TableCell className="font-medium">{c.name}</TableCell>
                  <TableCell className="text-muted-foreground">{c.provider}</TableCell>
                  <TableCell>
                    <Badge variant={CERTIFICATION_STATUS_BADGE_VARIANT[c.status]}>
                      {humanize(c.status)}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{fmtDate(c.completionDate)}</TableCell>
                  <TableCell className="text-muted-foreground">{fmtDate(c.expirationDate)}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {c.cost ? `${Number(c.cost).toLocaleString()} ${c.currency}` : "—"}
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end">
                      <CertificationFormDialog
                        mode="edit"
                        certificationId={c.id}
                        initialValues={{
                          name: c.name,
                          provider: c.provider,
                          category: c.category ?? "",
                          status: c.status,
                          startDate: c.startDate ? c.startDate.toISOString().slice(0, 10) : "",
                          examDate: c.examDate ? c.examDate.toISOString().slice(0, 10) : "",
                          completionDate: c.completionDate
                            ? c.completionDate.toISOString().slice(0, 10)
                            : "",
                          score: c.score ?? "",
                          cost: c.cost?.toString() ?? "",
                          currency: c.currency,
                          expirationDate: c.expirationDate
                            ? c.expirationDate.toISOString().slice(0, 10)
                            : "",
                          certificateUrl: c.certificateUrl ?? "",
                          notes: c.notes ?? "",
                        }}
                      />
                      <DeleteButton itemLabel={c.name} action={deleteCertification.bind(null, c.id)} />
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
