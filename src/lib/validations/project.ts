import { z } from "zod";
import { IMPACT_CATEGORIES } from "@/lib/labels";

const optionalDate = z
  .string()
  .optional()
  .transform((v) => (v === "" || v === undefined ? undefined : v));

const optionalString = z
  .string()
  .trim()
  .max(4000)
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

export const projectSchema = z.object({
  name: z.string().trim().min(1, "Project name is required").max(300),
  company: optionalString,
  date: optionalDate,
  problem: optionalString,
  context: optionalString,
  objective: optionalString,
  actions: optionalString,
  role: optionalString,
  stakeholders: csvList,
  skillsUsed: csvList,
  tools: csvList,
  countries: csvList,
  result: optionalString,
  mbaRelevance: optionalString,
  careerExperienceId: z
    .string()
    .optional()
    .transform((v) => (v === "" || v === undefined || v === "none" ? undefined : v)),
});

export type ProjectFormValues = z.infer<typeof projectSchema>;

export const projectImpactSchema = z.object({
  category: z.enum(IMPACT_CATEGORIES),
  metricName: z.string().trim().min(1, "Metric name is required").max(200),
  beforeValue: z
    .string()
    .optional()
    .transform((v) => (v === "" || v === undefined ? undefined : Number(v))),
  afterValue: z
    .string()
    .optional()
    .transform((v) => (v === "" || v === undefined ? undefined : Number(v))),
  unit: optionalString,
  annualizedValue: z
    .string()
    .optional()
    .transform((v) => (v === "" || v === undefined ? undefined : Number(v))),
  narrative: optionalString,
});

export type ProjectImpactFormValues = z.infer<typeof projectImpactSchema>;
