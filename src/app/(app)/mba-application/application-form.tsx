"use client";

import { useState, useTransition } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { Pencil, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
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
import { APPLICATION_STATUSES, humanize } from "@/lib/labels";
import { createApplication, updateApplication } from "@/app/(app)/mba-application/actions";

export type ApplicationValues = {
  programId: string;
  intake: string;
  round: string;
  deadline: string;
  status: (typeof APPLICATION_STATUSES)[number];
  cvReady: boolean;
  essaysReady: boolean;
  recommendationsReady: boolean;
  transcriptReady: boolean;
  testScoreReady: boolean;
  englishTestReady: boolean;
  passportReady: boolean;
  notes: string;
};

const CHECKLIST_FIELDS: { key: keyof ApplicationValues; label: string }[] = [
  { key: "cvReady", label: "CV" },
  { key: "essaysReady", label: "Essays" },
  { key: "recommendationsReady", label: "Recommendations" },
  { key: "transcriptReady", label: "Transcript" },
  { key: "testScoreReady", label: "GMAT/GRE score" },
  { key: "englishTestReady", label: "English test" },
  { key: "passportReady", label: "Passport" },
];

function emptyValues(defaultProgramId: string): ApplicationValues {
  return {
    programId: defaultProgramId,
    intake: "",
    round: "",
    deadline: "",
    status: "RESEARCHING",
    cvReady: false,
    essaysReady: false,
    recommendationsReady: false,
    transcriptReady: false,
    testScoreReady: false,
    englishTestReady: false,
    passportReady: false,
    notes: "",
  };
}

export function ApplicationFormDialog({
  mode,
  applicationId,
  initialValues,
  programs,
}: {
  mode: "create" | "edit";
  applicationId?: string;
  initialValues?: ApplicationValues;
  programs: { id: string; schoolName: string; programName: string }[];
}) {
  const [open, setOpen] = useState(false);
  const [isPending, startTransition] = useTransition();
  const { register, handleSubmit, watch, setValue } = useForm<ApplicationValues>({
    defaultValues: initialValues ?? emptyValues(programs[0]?.id ?? ""),
  });
  const programId = watch("programId");
  const status = watch("status");

  const onSubmit = handleSubmit((values) => {
    startTransition(async () => {
      const result =
        mode === "create" ? await createApplication(values) : await updateApplication(applicationId!, values);
      if (result.ok) {
        toast.success(mode === "create" ? "Application added" : "Updated");
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
          <Button size="sm" disabled={programs.length === 0}>
            <Plus className="size-4" /> Add application
          </Button>
        ) : (
          <Button variant="ghost" size="icon" className="size-8" aria-label="Edit">
            <Pencil className="size-4" />
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{mode === "create" ? "Add application" : "Edit application"}</DialogTitle>
          <DialogDescription>Track a specific program&apos;s application through to a decision.</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto pr-1">
          <div className="flex flex-col gap-1.5">
            <Label>Program</Label>
            <Select value={programId} onValueChange={(v) => setValue("programId", v)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {programs.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.schoolName} — {p.programName}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="intake">Intake</Label>
              <Input id="intake" {...register("intake")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="round">Round</Label>
              <Input id="round" {...register("round")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="deadline">Deadline</Label>
              <Input id="deadline" type="date" {...register("deadline")} />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Status</Label>
            <Select value={status} onValueChange={(v) => setValue("status", v as ApplicationValues["status"])}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {APPLICATION_STATUSES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {humanize(s)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="mb-2 block">Document checklist</Label>
            <div className="grid gap-2 sm:grid-cols-2">
              {CHECKLIST_FIELDS.map((f) => (
                <label key={f.key} className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={watch(f.key) as boolean}
                    onCheckedChange={(checked) => setValue(f.key, checked === true)}
                  />
                  {f.label}
                </label>
              ))}
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="notes">Notes</Label>
            <Textarea id="notes" rows={2} {...register("notes")} />
          </div>
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
