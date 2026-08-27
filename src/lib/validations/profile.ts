import { z } from "zod";

const optionalString = z
  .string()
  .trim()
  .max(2000)
  .optional()
  .transform((v) => (v === "" ? undefined : v));

const csvList = z
  .string()
  .optional()
  .transform((v) =>
    (v ?? "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
  );

export const profileSchema = z.object({
  fullName: z.string().trim().min(1, "Full name is required").max(200),
  currentLocation: optionalString,
  dateOfBirth: optionalString,
  currentJobTitle: optionalString,
  currentCompany: optionalString,
  yearsOfExperience: z
    .string()
    .optional()
    .transform((v) => (v === "" || v === undefined ? undefined : Number(v))),
  languages: csvList,
  careerGoalShortTerm: optionalString,
  careerGoalLongTerm: optionalString,
  mbaRationale: optionalString,
  mbaTargetYear: z
    .string()
    .optional()
    .transform((v) => (v === "" || v === undefined ? undefined : Number(v))),
  professionalInterests: csvList,
  currency: z.string().trim().min(1).max(10).default("EUR"),
  timezone: z.string().trim().min(1).max(100).default("Europe/Paris"),
  appMode: z.enum(["PRE_MBA", "POST_MBA"]).default("PRE_MBA"),
});

export type ProfileFormValues = z.infer<typeof profileSchema>;
