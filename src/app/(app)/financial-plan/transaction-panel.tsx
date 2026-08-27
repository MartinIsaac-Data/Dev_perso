"use client";

import { useState, useTransition } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { Plus, Receipt, X } from "lucide-react";

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
import { createTransaction, deleteTransaction } from "@/app/(app)/financial-plan/actions";

type Transaction = { id: string; label: string; amount: string; currency: string; date: Date; category: string | null };

export function TransactionPanel({ transactions }: { transactions: Transaction[] }) {
  const [open, setOpen] = useState(false);
  const [isPending, startTransition] = useTransition();
  const { register, handleSubmit, reset } = useForm({
    defaultValues: { label: "", amount: "", currency: "EUR", date: new Date().toISOString().slice(0, 10), category: "" },
  });

  const onSubmit = handleSubmit((values) => {
    startTransition(async () => {
      const result = await createTransaction(values);
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
      const result = await deleteTransaction(id);
      if (!result.ok) toast.error(result.error ?? "Could not delete");
    });
  };

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <p className="flex items-center gap-1.5 text-sm font-medium">
          <Receipt className="size-4 text-muted-foreground" /> Contributions &amp; costs
        </p>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button variant="outline" size="sm">
              <Plus className="size-3.5" /> Add entry
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-sm">
            <DialogHeader>
              <DialogTitle>Add a financial entry</DialogTitle>
              <DialogDescription>A savings contribution, scholarship or MBA-related cost.</DialogDescription>
            </DialogHeader>
            <form onSubmit={onSubmit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <Label>Label</Label>
                <Input {...register("label", { required: true })} />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <Label>Amount</Label>
                  <Input type="number" step="0.01" {...register("amount", { required: true })} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>Currency</Label>
                  <Input {...register("currency")} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <Label>Date</Label>
                  <Input type="date" {...register("date", { required: true })} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>Category</Label>
                  <Input placeholder="savings-contribution…" {...register("category")} />
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
      </div>
      {transactions.length === 0 ? (
        <p className="text-xs text-muted-foreground">No entries logged yet.</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {transactions.map((t) => (
            <li key={t.id} className="flex items-center justify-between rounded-md bg-muted/50 px-3 py-2 text-sm">
              <span>
                {t.label}
                {t.category ? <span className="text-xs text-muted-foreground"> · {t.category}</span> : ""}
                <span className="ml-2 text-xs text-muted-foreground">
                  {t.date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
                </span>
              </span>
              <span className="flex items-center gap-3">
                <span className="font-medium tabular-nums">
                  {Number(t.amount).toLocaleString()} {t.currency}
                </span>
                <button
                  type="button"
                  onClick={() => onDelete(t.id)}
                  disabled={isPending}
                  className="text-muted-foreground hover:text-destructive"
                  aria-label="Delete entry"
                >
                  <X className="size-3.5" />
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
