"use client";

import { useState, useTransition } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

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
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { updateProfile } from "@/app/(app)/settings/actions";

export type ProfileFormInitialValues = {
  fullName: string;
  currentLocation: string;
  dateOfBirth: string;
  currentJobTitle: string;
  currentCompany: string;
  yearsOfExperience: string;
  languages: string;
  careerGoalShortTerm: string;
  careerGoalLongTerm: string;
  mbaRationale: string;
  mbaTargetYear: string;
  professionalInterests: string;
  currency: string;
  timezone: string;
  appMode: "PRE_MBA" | "POST_MBA";
};

export function ProfileForm({ initialValues }: { initialValues: ProfileFormInitialValues }) {
  const [isPending, startTransition] = useTransition();
  const [appMode, setAppMode] = useState(initialValues.appMode);
  const { register, handleSubmit } = useForm({
    defaultValues: initialValues,
  });

  const onSubmit = handleSubmit((values) => {
    startTransition(async () => {
      const result = await updateProfile({ ...values, appMode });
      if (result.ok) {
        toast.success("Profile updated");
      } else {
        toast.error(result.error ?? "Could not update profile");
      }
    });
  });

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Identity</CardTitle>
          <CardDescription>Who you are — shown across the app.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Field label="Full name">
            <Input {...register("fullName")} />
          </Field>
          <Field label="Current location">
            <Input {...register("currentLocation")} placeholder="Paris, France" />
          </Field>
          <Field label="Date of birth">
            <Input type="date" {...register("dateOfBirth")} />
          </Field>
          <Field label="Application mode">
            <Select value={appMode} onValueChange={(v) => setAppMode(v as typeof appMode)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="PRE_MBA">Pre-MBA — preparing to apply</SelectItem>
                <SelectItem value="POST_MBA">Post-MBA — focused on career progression</SelectItem>
              </SelectContent>
            </Select>
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Current role</CardTitle>
          <CardDescription>Used in the Career Snapshot and readiness inputs.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Field label="Current job title">
            <Input {...register("currentJobTitle")} />
          </Field>
          <Field label="Current company">
            <Input {...register("currentCompany")} />
          </Field>
          <Field label="Years of experience">
            <Input type="number" step="0.5" min="0" {...register("yearsOfExperience")} />
          </Field>
          <Field label="Languages" hint="Comma-separated, e.g. French, English, Spanish">
            <Input {...register("languages")} />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Career goals &amp; MBA rationale</CardTitle>
          <CardDescription>
            The Goal Consistency Engine and AI Advisor will read these — be specific.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <Field label="Short-term goal (3–5 years)">
            <Textarea rows={2} {...register("careerGoalShortTerm")} />
          </Field>
          <Field label="Long-term goal (10+ years)">
            <Textarea rows={2} {...register("careerGoalLongTerm")} />
          </Field>
          <Field label="Why an MBA, why now?">
            <Textarea rows={3} {...register("mbaRationale")} />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="MBA target year">
              <Input type="number" min="2026" max="2045" {...register("mbaTargetYear")} />
            </Field>
            <Field label="Professional interests" hint="Comma-separated">
              <Input {...register("professionalInterests")} />
            </Field>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Preferences</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Field label="Currency">
            <Input {...register("currency")} placeholder="EUR" />
          </Field>
          <Field label="Timezone">
            <Input {...register("timezone")} placeholder="Europe/Paris" />
          </Field>
        </CardContent>
      </Card>

      <Separator />

      <div className="flex justify-end">
        <Button type="submit" disabled={isPending}>
          {isPending ? "Saving…" : "Save changes"}
        </Button>
      </div>
    </form>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{label}</Label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}
