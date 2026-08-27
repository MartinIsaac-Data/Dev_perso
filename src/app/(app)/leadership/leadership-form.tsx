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
import { LEADERSHIP_TYPES, humanize } from "@/lib/labels";
import { createLeadership, updateLeadership } from "@/app/(app)/leadership/actions";

export type LeadershipValues = {
  type: (typeof LEADERSHIP_TYPES)[number];
  title: string;
  organization: string;
  role: string;
  teamSize: string;
  startDate: string;
  endDate: string;
  isOngoing: boolean;
  responsibilities: string;
  results: string;
  skillsUsed: string;
};

const emptyValues: LeadershipValues = {
  type: "TEAM_LEADERSHIP",
  title: "",
  organization: "",
  role: "",
  teamSize: "",
  startDate: "",
  endDate: "",
  isOngoing: false,
  responsibilities: "",
  results: "",
  skillsUsed: "",
};

export function LeadershipFormDialog({
  mode,
  leadershipId,
  initialValues,
}: {
  mode: "create" | "edit";
  leadershipId?: string;
  initialValues?: LeadershipValues;
}) {
  const [open, setOpen] = useState(false);
  const [isPending, startTransition] = useTransition();
  const { register, handleSubmit, watch, setValue } = useForm<LeadershipValues>({
    defaultValues: initialValues ?? emptyValues,
  });
  const type = watch("type");
  const isOngoing = watch("isOngoing");

  const onSubmit = handleSubmit((values) => {
    startTransition(async () => {
      const result =
        mode === "create" ? await createLeadership(values) : await updateLeadership(leadershipId!, values);
      if (result.ok) {
        toast.success(mode === "create" ? "Leadership experience added" : "Updated");
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
            <Plus className="size-4" /> Add leadership experience
          </Button>
        ) : (
          <Button variant="ghost" size="icon" className="size-8">
            <Pencil className="size-4" />
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{mode === "create" ? "Add leadership experience" : "Edit leadership experience"}</DialogTitle>
          <DialogDescription>Project leadership, team management, mentoring, community work.</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto pr-1">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="title">Title</Label>
              <Input id="title" {...register("title", { required: true })} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Type</Label>
              <Select value={type} onValueChange={(v) => setValue("type", v as LeadershipValues["type"])}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {LEADERSHIP_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {humanize(t)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="organization">Organization</Label>
              <Input id="organization" {...register("organization")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="role">Role</Label>
              <Input id="role" {...register("role")} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="teamSize">Team size</Label>
              <Input id="teamSize" type="number" min="0" {...register("teamSize")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="startDate">Start date</Label>
              <Input id="startDate" type="date" {...register("startDate")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="endDate">End date</Label>
              <Input id="endDate" type="date" disabled={isOngoing} {...register("endDate")} />
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={isOngoing}
              onCheckedChange={(checked) => setValue("isOngoing", checked === true)}
            />
            Ongoing
          </label>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="responsibilities">Responsibilities</Label>
            <Textarea id="responsibilities" rows={2} {...register("responsibilities")} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="results">Results</Label>
            <Textarea id="results" rows={2} {...register("results")} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="skillsUsed">Skills used</Label>
            <Input id="skillsUsed" placeholder="Comma-separated" {...register("skillsUsed")} />
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
