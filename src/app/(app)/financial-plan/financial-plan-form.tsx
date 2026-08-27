"use client";

import { useTransition } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { upsertFinancialPlan } from "@/app/(app)/financial-plan/actions";

export type FinancialPlanValues = {
  targetYear: string;
  tuition: string;
  livingCost: string;
  travelCost: string;
  visaCost: string;
  insuranceCost: string;
  otherCost: string;
  currency: string;
  currentSavings: string;
  monthlyContribution: string;
  annualContributionGrowthPct: string;
  expectedAnnualReturnPct: string;
  scholarshipTarget: string;
  employerSponsorship: string;
  studentLoanTarget: string;
  familySupport: string;
};

export function FinancialPlanForm({ initialValues }: { initialValues: FinancialPlanValues }) {
  const [isPending, startTransition] = useTransition();
  const { register, handleSubmit } = useForm<FinancialPlanValues>({ defaultValues: initialValues });

  const onSubmit = handleSubmit((values) => {
    startTransition(async () => {
      const result = await upsertFinancialPlan(values);
      if (result.ok) toast.success("Financial plan updated");
      else toast.error(result.error ?? "Something went wrong");
    });
  });

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Estimated cost</CardTitle>
          <CardDescription>What the MBA is expected to cost, all-in.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-3">
          <Field label="Target year">
            <Input type="number" {...register("targetYear")} />
          </Field>
          <Field label="Currency">
            <Input {...register("currency")} />
          </Field>
          <Field label="Tuition">
            <Input type="number" step="100" {...register("tuition")} />
          </Field>
          <Field label="Living cost">
            <Input type="number" step="100" {...register("livingCost")} />
          </Field>
          <Field label="Travel">
            <Input type="number" step="50" {...register("travelCost")} />
          </Field>
          <Field label="Visa">
            <Input type="number" step="50" {...register("visaCost")} />
          </Field>
          <Field label="Insurance">
            <Input type="number" step="50" {...register("insuranceCost")} />
          </Field>
          <Field label="Other">
            <Input type="number" step="50" {...register("otherCost")} />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Savings projection</CardTitle>
          <CardDescription>Used to project your balance year by year.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Field label="Current savings">
            <Input type="number" step="100" {...register("currentSavings")} />
          </Field>
          <Field label="Monthly contribution">
            <Input type="number" step="50" {...register("monthlyContribution")} />
          </Field>
          <Field label="Annual contribution growth (%)">
            <Input type="number" step="1" {...register("annualContributionGrowthPct")} />
          </Field>
          <Field label="Expected annual return (%)">
            <Input type="number" step="0.5" {...register("expectedAnnualReturnPct")} />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Funding sources</CardTitle>
          <CardDescription>Targets, not yet-secured amounts.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Field label="Scholarship target">
            <Input type="number" step="100" {...register("scholarshipTarget")} />
          </Field>
          <Field label="Employer sponsorship">
            <Input type="number" step="100" {...register("employerSponsorship")} />
          </Field>
          <Field label="Student loan target">
            <Input type="number" step="100" {...register("studentLoanTarget")} />
          </Field>
          <Field label="Family support">
            <Input type="number" step="100" {...register("familySupport")} />
          </Field>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button type="submit" disabled={isPending}>
          {isPending ? "Saving…" : "Save financial plan"}
        </Button>
      </div>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  );
}
