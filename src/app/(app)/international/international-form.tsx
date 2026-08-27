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
import { INTERNATIONAL_EXPOSURE_TYPES, humanize } from "@/lib/labels";
import { createInternational, updateInternational } from "@/app/(app)/international/actions";

export type InternationalValues = {
  country: string;
  company: string;
  project: string;
  role: string;
  type: (typeof INTERNATIONAL_EXPOSURE_TYPES)[number];
  startDate: string;
  endDate: string;
  team: string;
  responsibilities: string;
};

const emptyValues: InternationalValues = {
  country: "",
  company: "",
  project: "",
  role: "",
  type: "WORKED_IN_COUNTRY",
  startDate: "",
  endDate: "",
  team: "",
  responsibilities: "",
};

export function InternationalFormDialog({
  mode,
  recordId,
  initialValues,
}: {
  mode: "create" | "edit";
  recordId?: string;
  initialValues?: InternationalValues;
}) {
  const [open, setOpen] = useState(false);
  const [isPending, startTransition] = useTransition();
  const { register, handleSubmit, watch, setValue } = useForm<InternationalValues>({
    defaultValues: initialValues ?? emptyValues,
  });
  const type = watch("type");

  const onSubmit = handleSubmit((values) => {
    startTransition(async () => {
      const result =
        mode === "create" ? await createInternational(values) : await updateInternational(recordId!, values);
      if (result.ok) {
        toast.success(mode === "create" ? "Added" : "Updated");
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
            <Plus className="size-4" /> Add exposure
          </Button>
        ) : (
          <Button variant="ghost" size="icon" className="size-8" aria-label="Edit">
            <Pencil className="size-4" />
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{mode === "create" ? "Add international exposure" : "Edit international exposure"}</DialogTitle>
          <DialogDescription>Countries, projects and multicultural teams.</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto pr-1">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="country">Country</Label>
              <Input id="country" {...register("country", { required: true })} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Type</Label>
              <Select value={type} onValueChange={(v) => setValue("type", v as InternationalValues["type"])}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {INTERNATIONAL_EXPOSURE_TYPES.map((t) => (
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
              <Label htmlFor="company">Company</Label>
              <Input id="company" {...register("company")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="project">Project</Label>
              <Input id="project" {...register("project")} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="role">Role</Label>
              <Input id="role" {...register("role")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="team">Team</Label>
              <Input id="team" {...register("team")} />
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
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="responsibilities">Responsibilities</Label>
            <Textarea id="responsibilities" rows={2} {...register("responsibilities")} />
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
