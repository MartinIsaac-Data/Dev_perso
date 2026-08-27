import { Construction } from "lucide-react";

import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";

export function ComingSoon({
  title,
  description,
  phaseNote,
}: {
  title: string;
  description: string;
  phaseNote: string;
}) {
  return (
    <div>
      <PageHeader title={title} description={description} />
      <EmptyState icon={Construction} title="This module is on the roadmap" description={phaseNote} />
    </div>
  );
}
