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
import { PROGRAM_TYPES, humanize } from "@/lib/labels";
import { createProgram, updateProgram } from "@/app/(app)/mba-targets/actions";

export type ProgramValues = {
  schoolName: string;
  programName: string;
  country: string;
  city: string;
  campus: string;
  programType: (typeof PROGRAM_TYPES)[number];
  durationMonths: string;
  tuition: string;
  estimatedLivingCost: string;
  currency: string;
  minExperienceYears: string;
  avgExperienceYears: string;
  gmatRequirement: string;
  greRequirement: string;
  englishRequirement: string;
  officialWebsite: string;
  notes: string;
  targetIntake: string;
  targetYear: string;
  lastVerifiedAt: string;
  sourceUrl: string;
};

const emptyValues: ProgramValues = {
  schoolName: "",
  programName: "MBA",
  country: "",
  city: "",
  campus: "",
  programType: "FULL_TIME",
  durationMonths: "",
  tuition: "",
  estimatedLivingCost: "",
  currency: "EUR",
  minExperienceYears: "",
  avgExperienceYears: "",
  gmatRequirement: "",
  greRequirement: "",
  englishRequirement: "",
  officialWebsite: "",
  notes: "",
  targetIntake: "",
  targetYear: "",
  lastVerifiedAt: new Date().toISOString().slice(0, 10),
  sourceUrl: "",
};

export function ProgramFormDialog({
  mode,
  programId,
  initialValues,
}: {
  mode: "create" | "edit";
  programId?: string;
  initialValues?: ProgramValues;
}) {
  const [open, setOpen] = useState(false);
  const [isPending, startTransition] = useTransition();
  const { register, handleSubmit, watch, setValue } = useForm<ProgramValues>({
    defaultValues: initialValues ?? emptyValues,
  });
  const programType = watch("programType");

  const onSubmit = handleSubmit((values) => {
    startTransition(async () => {
      const result =
        mode === "create" ? await createProgram(values) : await updateProgram(programId!, values);
      if (result.ok) {
        toast.success(mode === "create" ? "Program added" : "Updated");
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
          <Button size="sm">
            <Plus className="size-4" /> Add program
          </Button>
        ) : (
          <Button variant="ghost" size="icon" className="size-8" aria-label="Edit">
            <Pencil className="size-4" />
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{mode === "create" ? "Add MBA program" : "Edit MBA program"}</DialogTitle>
          <DialogDescription>
            School and program details. Set &quot;Last verified&quot; whenever you confirm this against the
            school&apos;s site.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto pr-1">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="schoolName">School</Label>
              <Input id="schoolName" {...register("schoolName", { required: true })} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="programName">Program</Label>
              <Input id="programName" {...register("programName", { required: true })} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="country">Country</Label>
              <Input id="country" {...register("country")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="city">City</Label>
              <Input id="city" {...register("city")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="campus">Campus</Label>
              <Input id="campus" {...register("campus")} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label>Program type</Label>
              <Select
                value={programType}
                onValueChange={(v) => setValue("programType", v as ProgramValues["programType"])}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PROGRAM_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {humanize(t)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="durationMonths">Duration (months)</Label>
              <Input id="durationMonths" type="number" min="0" {...register("durationMonths")} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tuition">Tuition</Label>
              <Input id="tuition" type="number" step="100" min="0" {...register("tuition")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="estimatedLivingCost">Living cost</Label>
              <Input id="estimatedLivingCost" type="number" step="100" min="0" {...register("estimatedLivingCost")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="currency">Currency</Label>
              <Input id="currency" {...register("currency")} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="minExperienceYears">Min. experience (yrs)</Label>
              <Input id="minExperienceYears" type="number" step="0.5" min="0" {...register("minExperienceYears")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="avgExperienceYears">Avg. experience (yrs)</Label>
              <Input id="avgExperienceYears" type="number" step="0.5" min="0" {...register("avgExperienceYears")} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="gmatRequirement">GMAT</Label>
              <Input id="gmatRequirement" {...register("gmatRequirement")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="greRequirement">GRE</Label>
              <Input id="greRequirement" {...register("greRequirement")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="englishRequirement">English</Label>
              <Input id="englishRequirement" {...register("englishRequirement")} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="targetIntake">Target intake</Label>
              <Input id="targetIntake" placeholder="August 2030" {...register("targetIntake")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="targetYear">Target year</Label>
              <Input id="targetYear" type="number" min="2026" max="2045" {...register("targetYear")} />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="officialWebsite">Official website</Label>
            <Input id="officialWebsite" {...register("officialWebsite")} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="lastVerifiedAt">Last verified</Label>
              <Input id="lastVerifiedAt" type="date" {...register("lastVerifiedAt")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sourceUrl">Source URL</Label>
              <Input id="sourceUrl" {...register("sourceUrl")} />
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
