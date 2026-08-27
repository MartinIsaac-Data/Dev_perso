"use client";

import { useMemo, useState, useTransition } from "react";
import { toast } from "sonner";
import { SlidersHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { updateWeights } from "@/app/(app)/mba-targets/actions";

type DimensionWeight = { key: string; label: string; weight: number };

export function WeightsDialog({
  programId,
  dimensions,
}: {
  programId: string;
  dimensions: DimensionWeight[];
}) {
  const [open, setOpen] = useState(false);
  const [isPending, startTransition] = useTransition();
  const [values, setValues] = useState<Record<string, number>>(
    Object.fromEntries(dimensions.map((d) => [d.key, d.weight])),
  );

  const total = useMemo(() => Object.values(values).reduce((sum, w) => sum + (w || 0), 0), [values]);

  const onSave = () => {
    startTransition(async () => {
      const result = await updateWeights(programId, values);
      if (result.ok) {
        toast.success("Weights updated");
        setOpen(false);
      } else {
        toast.error(result.error ?? "Something went wrong");
      }
    });
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <SlidersHorizontal className="size-3.5" /> Scoring weights
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Scoring weights for this program</DialogTitle>
          <DialogDescription>
            Must total 100. These weight the MBA Readiness score for this specific program.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          {dimensions.map((d) => (
            <div key={d.key} className="flex items-center justify-between gap-3">
              <Label className="text-sm font-normal">{d.label}</Label>
              <div className="flex items-center gap-1">
                <Input
                  type="number"
                  min="0"
                  max="100"
                  className="w-20"
                  value={values[d.key] ?? 0}
                  onChange={(e) =>
                    setValues((prev) => ({ ...prev, [d.key]: Number(e.target.value) }))
                  }
                />
                <span className="text-xs text-muted-foreground">%</span>
              </div>
            </div>
          ))}
        </div>
        <p className={`text-sm font-medium ${total === 100 ? "text-success" : "text-destructive"}`}>
          Total: {total}%
        </p>
        <DialogFooter>
          <Button onClick={onSave} disabled={isPending || total !== 100}>
            {isPending ? "Saving…" : "Save weights"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
