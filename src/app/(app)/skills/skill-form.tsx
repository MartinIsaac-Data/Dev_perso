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
import { SKILL_CATEGORIES, SKILL_LEVELS, humanize } from "@/lib/labels";
import { createSkill, updateSkill } from "@/app/(app)/skills/actions";

type SkillValues = {
  name: string;
  category: (typeof SKILL_CATEGORIES)[number];
  currentLevel: (typeof SKILL_LEVELS)[number];
  targetLevel: (typeof SKILL_LEVELS)[number];
  notes: string;
};

const emptyValues: SkillValues = {
  name: "",
  category: "TECHNICAL",
  currentLevel: "BEGINNER",
  targetLevel: "ADVANCED",
  notes: "",
};

export function SkillFormDialog({
  mode,
  skillId,
  initialValues,
}: {
  mode: "create" | "edit";
  skillId?: string;
  initialValues?: SkillValues;
}) {
  const [open, setOpen] = useState(false);
  const [isPending, startTransition] = useTransition();
  const { register, handleSubmit, watch, setValue } = useForm<SkillValues>({
    defaultValues: initialValues ?? emptyValues,
  });

  const category = watch("category");
  const currentLevel = watch("currentLevel");
  const targetLevel = watch("targetLevel");

  const onSubmit = handleSubmit((values) => {
    startTransition(async () => {
      const result =
        mode === "create" ? await createSkill(values) : await updateSkill(skillId!, values);
      if (result.ok) {
        toast.success(mode === "create" ? "Skill added" : "Skill updated");
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
            <Plus className="size-4" /> Add skill
          </Button>
        ) : (
          <Button variant="ghost" size="icon" className="size-8" aria-label="Edit">
            <Pencil className="size-4" />
          </Button>
        )}
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{mode === "create" ? "Add skill" : "Edit skill"}</DialogTitle>
          <DialogDescription>Track where you are and where you want to be.</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="name">Name</Label>
            <Input id="name" {...register("name", { required: true })} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Category</Label>
            <Select value={category} onValueChange={(v) => setValue("category", v as SkillValues["category"])}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SKILL_CATEGORIES.map((c) => (
                  <SelectItem key={c} value={c}>
                    {humanize(c)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label>Current level</Label>
              <Select
                value={currentLevel}
                onValueChange={(v) => setValue("currentLevel", v as SkillValues["currentLevel"])}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SKILL_LEVELS.map((l) => (
                    <SelectItem key={l} value={l}>
                      {humanize(l)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Target level</Label>
              <Select
                value={targetLevel}
                onValueChange={(v) => setValue("targetLevel", v as SkillValues["targetLevel"])}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SKILL_LEVELS.map((l) => (
                    <SelectItem key={l} value={l}>
                      {humanize(l)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="notes">Notes</Label>
            <Textarea id="notes" rows={3} {...register("notes")} />
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
