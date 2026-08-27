"use client";

import { useTransition } from "react";
import { toast } from "sonner";
import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { saveAssessment } from "@/app/(app)/mba-readiness/actions";

export function SaveAssessmentButton({ programId }: { programId: string }) {
  const [isPending, startTransition] = useTransition();

  return (
    <Button
      variant="outline"
      size="sm"
      disabled={isPending}
      onClick={() =>
        startTransition(async () => {
          const result = await saveAssessment(programId);
          if (result.ok) toast.success(`Snapshot saved — score ${result.breakdown.totalScore}/100`);
          else toast.error(result.error ?? "Something went wrong");
        })
      }
    >
      <RefreshCw className="size-3.5" /> {isPending ? "Saving…" : "Save snapshot"}
    </Button>
  );
}
