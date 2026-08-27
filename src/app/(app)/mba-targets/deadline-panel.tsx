"use client";

import { useState, useTransition } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { CalendarClock, Plus, X } from "lucide-react";

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
import { createDeadline, deleteDeadline } from "@/app/(app)/mba-targets/actions";

type Deadline = { id: string; round: string; deadline: Date };

export function DeadlinePanel({ programId, deadlines }: { programId: string; deadlines: Deadline[] }) {
  const [open, setOpen] = useState(false);
  const [isPending, startTransition] = useTransition();
  const { register, handleSubmit, reset } = useForm({ defaultValues: { round: "", deadline: "", notes: "" } });

  const onSubmit = handleSubmit((values) => {
    startTransition(async () => {
      const result = await createDeadline(programId, values);
      if (result.ok) {
        reset();
        setOpen(false);
      } else {
        toast.error(result.error ?? "Something went wrong");
      }
    });
  });

  const onDelete = (id: string) => {
    startTransition(async () => {
      const result = await deleteDeadline(id);
      if (!result.ok) toast.error(result.error ?? "Could not delete");
    });
  };

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <CalendarClock className="size-3.5" /> Deadlines
        </p>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button variant="ghost" size="sm" className="h-6 px-2 text-xs">
              <Plus className="size-3.5" /> Add
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-sm">
            <DialogHeader>
              <DialogTitle>Add application deadline</DialogTitle>
              <DialogDescription>A round or intake deadline for this program.</DialogDescription>
            </DialogHeader>
            <form onSubmit={onSubmit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <Label>Round</Label>
                <Input placeholder="Round 1" {...register("round", { required: true })} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Deadline</Label>
                <Input type="date" {...register("deadline", { required: true })} />
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
      {deadlines.length === 0 ? (
        <p className="text-xs text-muted-foreground">No deadlines added yet.</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {deadlines.map((d) => (
            <li key={d.id} className="flex items-center justify-between text-sm">
              <span>
                {d.round} ·{" "}
                {d.deadline.toLocaleDateString("en-GB", { year: "numeric", month: "short", day: "numeric" })}
              </span>
              <button
                type="button"
                onClick={() => onDelete(d.id)}
                disabled={isPending}
                className="text-muted-foreground hover:text-destructive"
                aria-label="Delete deadline"
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
