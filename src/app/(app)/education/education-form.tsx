"use client";

import { useState, useTransition } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { Pencil, Plus } from "lucide-react";

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
import { createEducation, updateEducation } from "@/app/(app)/education/actions";

export type EducationValues = {
  degree: string;
  university: string;
  field: string;
  country: string;
  startDate: string;
  endDate: string;
  gradeGpa: string;
  honors: string;
  relevantCoursework: string;
  documentUrl: string;
};

const emptyValues: EducationValues = {
  degree: "",
  university: "",
  field: "",
  country: "",
  startDate: "",
  endDate: "",
  gradeGpa: "",
  honors: "",
  relevantCoursework: "",
  documentUrl: "",
};

export function EducationFormDialog({
  mode,
  educationId,
  initialValues,
}: {
  mode: "create" | "edit";
  educationId?: string;
  initialValues?: EducationValues;
}) {
  const [open, setOpen] = useState(false);
  const [isPending, startTransition] = useTransition();
  const { register, handleSubmit } = useForm<EducationValues>({
    defaultValues: initialValues ?? emptyValues,
  });

  const onSubmit = handleSubmit((values) => {
    startTransition(async () => {
      const result =
        mode === "create" ? await createEducation(values) : await updateEducation(educationId!, values);
      if (result.ok) {
        toast.success(mode === "create" ? "Education added" : "Education updated");
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
            <Plus className="size-4" /> Add education
          </Button>
        ) : (
          <Button variant="ghost" size="icon" className="size-8" aria-label="Edit">
            <Pencil className="size-4" />
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{mode === "create" ? "Add education" : "Edit education"}</DialogTitle>
          <DialogDescription>Degrees, coursework and academic honors.</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto pr-1">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="degree">Degree</Label>
              <Input id="degree" {...register("degree", { required: true })} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="university">University</Label>
              <Input id="university" {...register("university", { required: true })} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="field">Field of study</Label>
              <Input id="field" {...register("field")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="country">Country</Label>
              <Input id="country" {...register("country")} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="startDate">Start date</Label>
              <Input id="startDate" type="date" {...register("startDate")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="endDate">End date</Label>
              <Input id="endDate" type="date" {...register("endDate")} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="gradeGpa">Grade / GPA</Label>
              <Input id="gradeGpa" {...register("gradeGpa")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="honors">Honors</Label>
              <Input id="honors" {...register("honors")} />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="relevantCoursework">Relevant coursework</Label>
            <Input id="relevantCoursework" placeholder="Comma-separated" {...register("relevantCoursework")} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="documentUrl">Document URL</Label>
            <Input id="documentUrl" {...register("documentUrl")} />
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
