"use client";

import { useTransition } from "react";
import { toast } from "sonner";
import { Archive, ArchiveRestore, Star } from "lucide-react";

import { Button } from "@/components/ui/button";
import { setPrimaryProgram, toggleArchiveProgram } from "@/app/(app)/mba-targets/actions";

export function SetPrimaryButton({ programId, isPrimary }: { programId: string; isPrimary: boolean }) {
  const [isPending, startTransition] = useTransition();

  if (isPrimary) return null;

  return (
    <Button
      variant="outline"
      size="sm"
      disabled={isPending}
      onClick={() =>
        startTransition(async () => {
          const result = await setPrimaryProgram(programId);
          if (result.ok) toast.success("Primary target updated");
          else toast.error(result.error ?? "Something went wrong");
        })
      }
    >
      <Star className="size-3.5" /> Set as primary
    </Button>
  );
}

export function ArchiveToggleButton({ programId, isArchived }: { programId: string; isArchived: boolean }) {
  const [isPending, startTransition] = useTransition();

  return (
    <Button
      variant="ghost"
      size="sm"
      disabled={isPending}
      onClick={() =>
        startTransition(async () => {
          const result = await toggleArchiveProgram(programId, !isArchived);
          if (!result.ok) toast.error(result.error ?? "Something went wrong");
        })
      }
    >
      {isArchived ? (
        <>
          <ArchiveRestore className="size-3.5" /> Restore
        </>
      ) : (
        <>
          <Archive className="size-3.5" /> Archive
        </>
      )}
    </Button>
  );
}
