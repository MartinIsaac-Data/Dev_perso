"use client";

import { useState, useTransition } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { Pencil, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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
import { MILESTONE_STATUSES, PRIORITIES, humanize } from "@/lib/labels";
import { createMilestone, updateMilestone } from "@/app/(app)/roadmap/actions";

export type MilestoneValues = {
  year: string;
  title: string;
  objective: string;
  deadline: string;
  status: (typeof MILESTONE_STATUSES)[number];
  priority: (typeof PRIORITIES)[number];
  kpi: string;
  dependsOnId: string;
};

function emptyValues(defaultYear: number): MilestoneValues {
  return {
    year: String(defaultYear),
    title: "",
    objective: "",
    deadline: "",
    status: "PLANNED",
    priority: "MEDIUM",
    kpi: "",
    dependsOnId: "none",
  };
}

export function MilestoneFormDialog({
  mode,
  roadmapId,
  milestoneId,
  initialValues,
  defaultYear,
  otherMilestones,
}: {
  mode: "create" | "edit";
  roadmapId: string;
  milestoneId?: string;
  initialValues?: MilestoneValues;
  defaultYear: number;
  otherMilestones: { id: string; title: string }[];
}) {
  const [open, setOpen] = useState(false);
  const [isPending, startTransition] = useTransition();
  const { register, handleSubmit, watch, setValue } = useForm<MilestoneValues>({
    defaultValues: initialValues ?? emptyValues(defaultYear),
  });
  const status = watch("status");
  const priority = watch("priority");
  const dependsOnId = watch("dependsOnId");

  const onSubmit = handleSubmit((values) => {
    startTransition(async () => {
      const result =
        mode === "create"
          ? await createMilestone(roadmapId, values)
          : await updateMilestone(milestoneId!, values);
      if (result.ok) {
        toast.success(mode === "create" ? "Milestone added" : "Updated");
        setOpen(false);
      } else {
        toast.error(result.error ?? "Something went wrong");
      }
    });
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {mode === "create" ? (
          <Button size="sm" variant="outline">
            <Plus className="size-4" /> Add milestone
          </Button>
        ) : (
          <Button variant="ghost" size="icon" className="size-7" aria-label="Edit">
            <Pencil className="size-3.5" />
          </Button>
        )}
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{mode === "create" ? "Add milestone" : "Edit milestone"}</DialogTitle>
          <DialogDescription>A concrete step on the way to your MBA.</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto pr-1">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="title">Title</Label>
              <Input id="title" {...register("title", { required: true })} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="year">Year</Label>
              <Input id="year" type="number" {...register("year", { required: true })} />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="objective">Objective</Label>
            <Textarea id="objective" rows={2} {...register("objective")} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label>Status</Label>
              <Select value={status} onValueChange={(v) => setValue("status", v as MilestoneValues["status"])}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MILESTONE_STATUSES.map((s) => (
                    <SelectItem key={s} value={s}>
                      {humanize(s)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Priority</Label>
              <Select value={priority} onValueChange={(v) => setValue("priority", v as MilestoneValues["priority"])}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PRIORITIES.map((p) => (
                    <SelectItem key={p} value={p}>
                      {humanize(p)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="deadline">Deadline</Label>
              <Input id="deadline" type="date" {...register("deadline")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="kpi">KPI</Label>
              <Input id="kpi" {...register("kpi")} />
            </div>
          </div>
          {otherMilestones.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <Label>Depends on</Label>
              <Select value={dependsOnId} onValueChange={(v) => setValue("dependsOnId", v)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {otherMilestones.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <DialogFooter>
            <Button type="submit" disabled={isPending}>
              {isPending ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
