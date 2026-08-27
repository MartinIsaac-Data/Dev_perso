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
import { EMPLOYMENT_TYPES, humanize } from "@/lib/labels";
import { createExperience, updateExperience } from "@/app/(app)/career/actions";

export type ExperienceValues = {
  company: string;
  role: string;
  department: string;
  location: string;
  startDate: string;
  endDate: string;
  isCurrent: boolean;
  employmentType: (typeof EMPLOYMENT_TYPES)[number];
  responsibilities: string;
  teamSize: string;
  manager: string;
  countriesCovered: string;
  skillsUsed: string;
};

const emptyValues: ExperienceValues = {
  company: "",
  role: "",
  department: "",
  location: "",
  startDate: "",
  endDate: "",
  isCurrent: false,
  employmentType: "FULL_TIME",
  responsibilities: "",
  teamSize: "",
  manager: "",
  countriesCovered: "",
  skillsUsed: "",
};

export function ExperienceFormDialog({
  mode,
  experienceId,
  initialValues,
}: {
  mode: "create" | "edit";
  experienceId?: string;
  initialValues?: ExperienceValues;
}) {
  const [open, setOpen] = useState(false);
  const [isPending, startTransition] = useTransition();
  const { register, handleSubmit, watch, setValue } = useForm<ExperienceValues>({
    defaultValues: initialValues ?? emptyValues,
  });
  const isCurrent = watch("isCurrent");
  const employmentType = watch("employmentType");

  const onSubmit = handleSubmit((values) => {
    startTransition(async () => {
      const result =
        mode === "create" ? await createExperience(values) : await updateExperience(experienceId!, values);
      if (result.ok) {
        toast.success(mode === "create" ? "Experience added" : "Updated");
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
            <Plus className="size-4" /> Add experience
          </Button>
        ) : (
          <Button variant="ghost" size="icon" className="size-8" aria-label="Edit">
            <Pencil className="size-4" />
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{mode === "create" ? "Add career experience" : "Edit career experience"}</DialogTitle>
          <DialogDescription>Company, role, responsibilities and reach.</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto pr-1">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="company">Company</Label>
              <Input id="company" {...register("company", { required: true })} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="role">Role</Label>
              <Input id="role" {...register("role", { required: true })} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="department">Department</Label>
              <Input id="department" {...register("department")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="location">Location</Label>
              <Input id="location" {...register("location")} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="startDate">Start date</Label>
              <Input id="startDate" type="date" {...register("startDate", { required: true })} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="endDate">End date</Label>
              <Input id="endDate" type="date" disabled={isCurrent} {...register("endDate")} />
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={isCurrent}
              onCheckedChange={(checked) => setValue("isCurrent", checked === true)}
            />
            This is my current role
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label>Employment type</Label>
              <Select
                value={employmentType}
                onValueChange={(v) => setValue("employmentType", v as ExperienceValues["employmentType"])}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {EMPLOYMENT_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {humanize(t)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="teamSize">Team size</Label>
              <Input id="teamSize" type="number" min="0" {...register("teamSize")} />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="manager">Manager</Label>
            <Input id="manager" {...register("manager")} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="responsibilities">Responsibilities</Label>
            <Textarea id="responsibilities" rows={3} {...register("responsibilities")} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="countriesCovered">Countries covered</Label>
              <Input id="countriesCovered" placeholder="Comma-separated" {...register("countriesCovered")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="skillsUsed">Skills used</Label>
              <Input id="skillsUsed" placeholder="Comma-separated" {...register("skillsUsed")} />
            </div>
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
