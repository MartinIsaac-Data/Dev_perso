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
import { EVIDENCE_TYPES, humanize } from "@/lib/labels";
import { createEvidence, updateEvidence } from "@/app/(app)/evidence/actions";

export type EvidenceValues = {
  title: string;
  type: (typeof EVIDENCE_TYPES)[number];
  date: string;
  description: string;
  tags: string;
  fileUrl: string;
  projectId: string;
  certificationId: string;
};

const emptyValues: EvidenceValues = {
  title: "",
  type: "PDF",
  date: "",
  description: "",
  tags: "",
  fileUrl: "",
  projectId: "none",
  certificationId: "none",
};

export function EvidenceFormDialog({
  mode,
  evidenceId,
  initialValues,
  projects,
  certifications,
}: {
  mode: "create" | "edit";
  evidenceId?: string;
  initialValues?: EvidenceValues;
  projects: { id: string; name: string }[];
  certifications: { id: string; name: string }[];
}) {
  const [open, setOpen] = useState(false);
  const [isPending, startTransition] = useTransition();
  const { register, handleSubmit, watch, setValue } = useForm<EvidenceValues>({
    defaultValues: initialValues ?? emptyValues,
  });
  const type = watch("type");
  const projectId = watch("projectId");
  const certificationId = watch("certificationId");

  const onSubmit = handleSubmit((values) => {
    startTransition(async () => {
      const result =
        mode === "create" ? await createEvidence(values) : await updateEvidence(evidenceId!, values);
      if (result.ok) {
        toast.success(mode === "create" ? "Evidence added" : "Updated");
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
            <Plus className="size-4" /> Add evidence
          </Button>
        ) : (
          <Button variant="ghost" size="icon" className="size-8">
            <Pencil className="size-4" />
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{mode === "create" ? "Add evidence" : "Edit evidence"}</DialogTitle>
          <DialogDescription>
            The proof behind an achievement — so you don&apos;t forget it in three years.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto pr-1">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="title">Title</Label>
              <Input id="title" {...register("title", { required: true })} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Type</Label>
              <Select value={type} onValueChange={(v) => setValue("type", v as EvidenceValues["type"])}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {EVIDENCE_TYPES.map((t) => (
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
              <Label>Related project</Label>
              <Select value={projectId} onValueChange={(v) => setValue("projectId", v)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {projects.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Related certification</Label>
              <Select value={certificationId} onValueChange={(v) => setValue("certificationId", v)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {certifications.map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="date">Date</Label>
              <Input id="date" type="date" {...register("date")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tags">Tags</Label>
              <Input id="tags" placeholder="Comma-separated" {...register("tags")} />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="fileUrl">File URL</Label>
            <Input id="fileUrl" {...register("fileUrl")} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="description">Description</Label>
            <Textarea id="description" rows={3} {...register("description")} />
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
