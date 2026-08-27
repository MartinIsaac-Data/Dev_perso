"use client";

import { useTransition } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createRoadmap } from "@/app/(app)/roadmap/actions";

export function CreateRoadmapForm({ suggestedEndYear }: { suggestedEndYear: number }) {
  const [isPending, startTransition] = useTransition();
  const currentYear = new Date().getFullYear();
  const { register, handleSubmit } = useForm({
    defaultValues: { name: "MBA Roadmap", startYear: String(currentYear), endYear: String(suggestedEndYear) },
  });

  const onSubmit = handleSubmit((values) => {
    startTransition(async () => {
      const result = await createRoadmap(values);
      if (!result.ok) toast.error(result.error ?? "Something went wrong");
    });
  });

  return (
    <form onSubmit={onSubmit} className="mx-auto flex max-w-sm flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="name">Roadmap name</Label>
        <Input id="name" {...register("name", { required: true })} />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="startYear">Start year</Label>
          <Input id="startYear" type="number" {...register("startYear", { required: true })} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="endYear">End year</Label>
          <Input id="endYear" type="number" {...register("endYear", { required: true })} />
        </div>
      </div>
      <Button type="submit" disabled={isPending}>
        {isPending ? "Creating…" : "Create roadmap"}
      </Button>
    </form>
  );
}
