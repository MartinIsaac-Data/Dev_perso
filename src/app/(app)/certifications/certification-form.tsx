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
import { CERTIFICATION_STATUSES, humanize } from "@/lib/labels";
import { createCertification, updateCertification } from "@/app/(app)/certifications/actions";

export type CertificationValues = {
  name: string;
  provider: string;
  category: string;
  status: (typeof CERTIFICATION_STATUSES)[number];
  startDate: string;
  examDate: string;
  completionDate: string;
  score: string;
  cost: string;
  currency: string;
  expirationDate: string;
  certificateUrl: string;
  notes: string;
};

const emptyValues: CertificationValues = {
  name: "",
  provider: "",
  category: "",
  status: "NOT_STARTED",
  startDate: "",
  examDate: "",
  completionDate: "",
  score: "",
  cost: "",
  currency: "EUR",
  expirationDate: "",
  certificateUrl: "",
  notes: "",
};

export function CertificationFormDialog({
  mode,
  certificationId,
  initialValues,
}: {
  mode: "create" | "edit";
  certificationId?: string;
  initialValues?: CertificationValues;
}) {
  const [open, setOpen] = useState(false);
  const [isPending, startTransition] = useTransition();
  const { register, handleSubmit, watch, setValue } = useForm<CertificationValues>({
    defaultValues: initialValues ?? emptyValues,
  });
  const status = watch("status");

  const onSubmit = handleSubmit((values) => {
    startTransition(async () => {
      const result =
        mode === "create"
          ? await createCertification(values)
          : await updateCertification(certificationId!, values);
      if (result.ok) {
        toast.success(mode === "create" ? "Certification added" : "Certification updated");
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
            <Plus className="size-4" /> Add certification
          </Button>
        ) : (
          <Button variant="ghost" size="icon" className="size-8">
            <Pencil className="size-4" />
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{mode === "create" ? "Add certification" : "Edit certification"}</DialogTitle>
          <DialogDescription>Planning through completion, with cost and expiration.</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto pr-1">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="name">Name</Label>
              <Input id="name" {...register("name", { required: true })} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="provider">Provider</Label>
              <Input id="provider" {...register("provider", { required: true })} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="category">Category</Label>
              <Input id="category" placeholder="Data, Supply Chain, English…" {...register("category")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Status</Label>
              <Select value={status} onValueChange={(v) => setValue("status", v as CertificationValues["status"])}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CERTIFICATION_STATUSES.map((s) => (
                    <SelectItem key={s} value={s}>
                      {humanize(s)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="startDate">Start date</Label>
              <Input id="startDate" type="date" {...register("startDate")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="examDate">Exam date</Label>
              <Input id="examDate" type="date" {...register("examDate")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="completionDate">Completion date</Label>
              <Input id="completionDate" type="date" {...register("completionDate")} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="score">Score</Label>
              <Input id="score" placeholder="112/120" {...register("score")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="cost">Cost</Label>
              <Input id="cost" type="number" step="0.01" min="0" {...register("cost")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="currency">Currency</Label>
              <Input id="currency" {...register("currency")} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="expirationDate">Expiration date</Label>
              <Input id="expirationDate" type="date" {...register("expirationDate")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="certificateUrl">Certificate URL</Label>
              <Input id="certificateUrl" {...register("certificateUrl")} />
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
