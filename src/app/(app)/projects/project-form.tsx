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
import { createProject, updateProject } from "@/app/(app)/projects/actions";

export type ProjectValues = {
  name: string;
  company: string;
  date: string;
  problem: string;
  context: string;
  objective: string;
  actions: string;
  role: string;
  stakeholders: string;
  skillsUsed: string;
  tools: string;
  countries: string;
  result: string;
  mbaRelevance: string;
  careerExperienceId: string;
};

const emptyValues: ProjectValues = {
  name: "",
  company: "",
  date: "",
  problem: "",
  context: "",
  objective: "",
  actions: "",
  role: "",
  stakeholders: "",
  skillsUsed: "",
  tools: "",
  countries: "",
  result: "",
  mbaRelevance: "",
  careerExperienceId: "none",
};

export function ProjectFormDialog({
  mode,
  projectId,
  initialValues,
  careerExperiences,
}: {
  mode: "create" | "edit";
  projectId?: string;
  initialValues?: ProjectValues;
  careerExperiences: { id: string; company: string; role: string }[];
}) {
  const [open, setOpen] = useState(false);
  const [isPending, startTransition] = useTransition();
  const { register, handleSubmit, watch, setValue } = useForm<ProjectValues>({
    defaultValues: initialValues ?? emptyValues,
  });
  const careerExperienceId = watch("careerExperienceId");

  const onSubmit = handleSubmit((values) => {
    startTransition(async () => {
      const result =
        mode === "create" ? await createProject(values) : await updateProject(projectId!, values);
      if (result.ok) {
        toast.success(mode === "create" ? "Project added" : "Updated");
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
            <Plus className="size-4" /> Add project
          </Button>
        ) : (
          <Button variant="ghost" size="icon" className="size-8" aria-label="Edit">
            <Pencil className="size-4" />
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{mode === "create" ? "Add project" : "Edit project"}</DialogTitle>
          <DialogDescription>Problem, actions and result — the raw material for impact stories.</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto pr-1">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="name">Project name</Label>
              <Input id="name" {...register("name", { required: true })} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="company">Company</Label>
              <Input id="company" {...register("company")} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="date">Date</Label>
              <Input id="date" type="date" {...register("date")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="role">Your role</Label>
              <Input id="role" {...register("role")} />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Linked career experience</Label>
            <Select
              value={careerExperienceId}
              onValueChange={(v) => setValue("careerExperienceId", v)}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None</SelectItem>
                {careerExperiences.map((e) => (
                  <SelectItem key={e.id} value={e.id}>
                    {e.role} at {e.company}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="problem">Problem</Label>
            <Textarea id="problem" rows={2} {...register("problem")} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="objective">Objective</Label>
            <Textarea id="objective" rows={2} {...register("objective")} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="actions">Actions</Label>
            <Textarea id="actions" rows={2} {...register("actions")} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="result">Result</Label>
            <Textarea id="result" rows={2} {...register("result")} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tools">Tools</Label>
              <Input id="tools" placeholder="Comma-separated" {...register("tools")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="countries">Countries</Label>
              <Input id="countries" placeholder="Comma-separated" {...register("countries")} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="stakeholders">Stakeholders</Label>
              <Input id="stakeholders" placeholder="Comma-separated" {...register("stakeholders")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="skillsUsed">Skills used</Label>
              <Input id="skillsUsed" placeholder="Comma-separated" {...register("skillsUsed")} />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="mbaRelevance">MBA relevance</Label>
            <Textarea id="mbaRelevance" rows={2} {...register("mbaRelevance")} />
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
