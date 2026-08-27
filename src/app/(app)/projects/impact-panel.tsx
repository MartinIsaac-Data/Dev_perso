"use client";

import { useState, useTransition } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { Plus, TrendingUp, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { IMPACT_CATEGORIES, humanize } from "@/lib/labels";
import { createImpact, deleteImpact } from "@/app/(app)/projects/actions";

type Impact = {
  id: string;
  category: string;
  metricName: string;
  beforeValue: string | null;
  afterValue: string | null;
  unit: string | null;
  annualizedValue: string | null;
  narrative: string | null;
};

export function ImpactPanel({ projectId, impacts }: { projectId: string; impacts: Impact[] }) {
  const [open, setOpen] = useState(false);
  const [isPending, startTransition] = useTransition();
  const { register, handleSubmit, watch, setValue, reset } = useForm({
    defaultValues: {
      category: "COST_REDUCTION" as (typeof IMPACT_CATEGORIES)[number],
      metricName: "",
      beforeValue: "",
      afterValue: "",
      unit: "",
      annualizedValue: "",
      narrative: "",
    },
  });
  const category = watch("category");

  const onSubmit = handleSubmit((values) => {
    startTransition(async () => {
      const result = await createImpact(projectId, values);
      if (result.ok) {
        toast.success("Impact added");
        reset();
        setOpen(false);
      } else {
        toast.error(result.error ?? "Something went wrong");
      }
    });
  });

  const onDelete = (id: string) => {
    startTransition(async () => {
      const result = await deleteImpact(id);
      if (!result.ok) toast.error(result.error ?? "Could not delete");
    });
  };

  return (
    <div className="mt-3 border-t pt-3">
      <div className="mb-2 flex items-center justify-between">
        <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <TrendingUp className="size-3.5" /> Measured impact
        </p>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button variant="ghost" size="sm" className="h-6 px-2 text-xs">
              <Plus className="size-3.5" /> Add impact
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Add measured impact</DialogTitle>
              <DialogDescription>Before/after numbers make an achievement defensible.</DialogDescription>
            </DialogHeader>
            <form onSubmit={onSubmit} className="flex flex-col gap-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="flex flex-col gap-1.5">
                  <Label>Category</Label>
                  <Select
                    value={category}
                    onValueChange={(v) => setValue("category", v as (typeof IMPACT_CATEGORIES)[number])}
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {IMPACT_CATEGORIES.map((c) => (
                        <SelectItem key={c} value={c}>
                          {humanize(c)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="metricName">Metric</Label>
                  <Input id="metricName" {...register("metricName", { required: true })} />
                </div>
              </div>
              <div className="grid gap-4 sm:grid-cols-3">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="beforeValue">Before</Label>
                  <Input id="beforeValue" type="number" step="any" {...register("beforeValue")} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="afterValue">After</Label>
                  <Input id="afterValue" type="number" step="any" {...register("afterValue")} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="unit">Unit</Label>
                  <Input id="unit" placeholder="%, hours, €…" {...register("unit")} />
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="annualizedValue">Annualized value (optional)</Label>
                <Input id="annualizedValue" type="number" step="any" {...register("annualizedValue")} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="narrative">Narrative</Label>
                <Textarea id="narrative" rows={2} {...register("narrative")} />
              </div>
              <DialogFooter>
                <Button type="submit" disabled={isPending}>
                  {isPending ? "Saving…" : "Save"}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>
      {impacts.length === 0 ? (
        <p className="text-xs text-muted-foreground">No measured impact logged yet.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {impacts.map((impact) => (
            <li key={impact.id} className="flex items-start justify-between gap-2 rounded-md bg-muted/50 p-2 text-sm">
              <div>
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">{humanize(impact.category)}</Badge>
                  <span className="font-medium">{impact.metricName}</span>
                </div>
                {impact.beforeValue !== null && impact.afterValue !== null && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    {impact.beforeValue} → {impact.afterValue} {impact.unit}
                    {impact.annualizedValue ? ` · ~${impact.annualizedValue} ${impact.unit}/yr` : ""}
                  </p>
                )}
                {impact.narrative && <p className="mt-1 text-xs text-muted-foreground">{impact.narrative}</p>}
              </div>
              <button
                type="button"
                onClick={() => onDelete(impact.id)}
                disabled={isPending}
                className="shrink-0 text-muted-foreground hover:text-destructive"
                aria-label="Delete impact"
              >
                <X className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
