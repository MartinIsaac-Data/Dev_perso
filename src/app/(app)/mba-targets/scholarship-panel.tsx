"use client";

import { useState, useTransition } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { GraduationCap, Plus, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
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
import { SCHOLARSHIP_STATUSES, humanize } from "@/lib/labels";
import { createScholarship, deleteScholarship } from "@/app/(app)/mba-targets/actions";

type Scholarship = {
  id: string;
  name: string;
  amount: string | null;
  currency: string;
  status: string;
  deadline: Date | null;
};

export function ScholarshipPanel({
  programId,
  scholarships,
}: {
  programId: string;
  scholarships: Scholarship[];
}) {
  const [open, setOpen] = useState(false);
  const [isPending, startTransition] = useTransition();
  const { register, handleSubmit, watch, setValue, reset } = useForm({
    defaultValues: {
      name: "",
      amount: "",
      currency: "EUR",
      eligibility: "",
      deadline: "",
      status: "RESEARCHING" as (typeof SCHOLARSHIP_STATUSES)[number],
      website: "",
    },
  });
  const status = watch("status");

  const onSubmit = handleSubmit((values) => {
    startTransition(async () => {
      const result = await createScholarship(programId, values);
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
      const result = await deleteScholarship(id);
      if (!result.ok) toast.error(result.error ?? "Could not delete");
    });
  };

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <GraduationCap className="size-3.5" /> Scholarships
        </p>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button variant="ghost" size="sm" className="h-6 px-2 text-xs">
              <Plus className="size-3.5" /> Add
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-sm">
            <DialogHeader>
              <DialogTitle>Add scholarship</DialogTitle>
              <DialogDescription>Track funding opportunities for this program.</DialogDescription>
            </DialogHeader>
            <form onSubmit={onSubmit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <Label>Name</Label>
                <Input {...register("name", { required: true })} />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <Label>Amount</Label>
                  <Input type="number" min="0" {...register("amount")} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>Status</Label>
                  <Select value={status} onValueChange={(v) => setValue("status", v as typeof status)}>
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {SCHOLARSHIP_STATUSES.map((s) => (
                        <SelectItem key={s} value={s}>
                          {humanize(s)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Deadline</Label>
                <Input type="date" {...register("deadline")} />
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
      {scholarships.length === 0 ? (
        <p className="text-xs text-muted-foreground">No scholarships added yet.</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {scholarships.map((s) => (
            <li key={s.id} className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2">
                {s.name}
                <Badge variant="outline">{humanize(s.status)}</Badge>
                {s.amount && (
                  <span className="text-xs text-muted-foreground">
                    {Number(s.amount).toLocaleString()} {s.currency}
                  </span>
                )}
              </span>
              <button
                type="button"
                onClick={() => onDelete(s.id)}
                disabled={isPending}
                className="text-muted-foreground hover:text-destructive"
                aria-label="Delete scholarship"
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
