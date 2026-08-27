"use client";

import { useState, useTransition } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { Plus, Trophy, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { createAchievement, deleteAchievement } from "@/app/(app)/career/actions";

type Achievement = { id: string; title: string; description: string | null; date: Date | null };

export function AchievementPanel({
  careerExperienceId,
  achievements,
}: {
  careerExperienceId: string;
  achievements: Achievement[];
}) {
  const [open, setOpen] = useState(false);
  const [isPending, startTransition] = useTransition();
  const { register, handleSubmit, reset } = useForm({
    defaultValues: { title: "", description: "", date: "" },
  });

  const onSubmit = handleSubmit((values) => {
    startTransition(async () => {
      const result = await createAchievement(careerExperienceId, values);
      if (result.ok) {
        toast.success("Achievement added");
        reset();
        setOpen(false);
      } else {
        toast.error(result.error ?? "Something went wrong");
      }
    });
  });

  const onDelete = (id: string) => {
    startTransition(async () => {
      const result = await deleteAchievement(id);
      if (!result.ok) toast.error(result.error ?? "Could not delete");
    });
  };

  return (
    <div className="mt-3 border-t pt-3">
      <div className="mb-2 flex items-center justify-between">
        <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <Trophy className="size-3.5" /> Achievements
        </p>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button variant="ghost" size="sm" className="h-6 px-2 text-xs">
              <Plus className="size-3.5" /> Add
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-sm">
            <DialogHeader>
              <DialogTitle>Add achievement</DialogTitle>
              <DialogDescription>A specific, measurable outcome from this role.</DialogDescription>
            </DialogHeader>
            <form onSubmit={onSubmit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`title-${careerExperienceId}`}>Title</Label>
                <Input id={`title-${careerExperienceId}`} {...register("title", { required: true })} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`date-${careerExperienceId}`}>Date</Label>
                <Input id={`date-${careerExperienceId}`} type="date" {...register("date")} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`description-${careerExperienceId}`}>Description</Label>
                <Textarea id={`description-${careerExperienceId}`} rows={2} {...register("description")} />
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
      {achievements.length === 0 ? (
        <p className="text-xs text-muted-foreground">No achievements logged yet.</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {achievements.map((a) => (
            <li key={a.id} className="flex items-start justify-between gap-2 text-sm">
              <span>{a.title}</span>
              <button
                type="button"
                onClick={() => onDelete(a.id)}
                disabled={isPending}
                className="shrink-0 text-muted-foreground hover:text-destructive"
                aria-label="Delete achievement"
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
