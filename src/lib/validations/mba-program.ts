import { z } from "zod";
import { PROGRAM_TYPES } from "@/lib/labels";

const optionalString = z
  .string()
  .trim()
  .max(2000)
  .optional()
  .transform((v) => (v === "" ? undefined : v));

const optionalDate = z
  .string()
  .optional()
  .transform((v) => (v === "" || v === undefined ? undefined : v));

const optionalNumber = z
  .string()
  .optional()
  .transform((v) => (v === "" || v === undefined ? undefined : Number(v)));

export const mbaProgramSchema = z.object({
  schoolName: z.string().trim().min(1, "School name is required").max(300),
  programName: z.string().trim().min(1, "Program name is required").max(300),
  country: optionalString,
  city: optionalString,
  campus: optionalString,
  programType: z.enum(PROGRAM_TYPES),
  durationMonths: optionalNumber,
  tuition: optionalNumber,
  estimatedLivingCost: optionalNumber,
  currency: z.string().trim().min(1).max(10).default("EUR"),
  minExperienceYears: optionalNumber,
  avgExperienceYears: optionalNumber,
  gmatRequirement: optionalString,
  greRequirement: optionalString,
  englishRequirement: optionalString,
  officialWebsite: optionalString,
  notes: optionalString,
  targetIntake: optionalString,
  targetYear: optionalNumber,
  lastVerifiedAt: optionalDate,
  sourceUrl: optionalString,
});

export type MBAProgramFormValues = z.infer<typeof mbaProgramSchema>;

export const mbaDeadlineSchema = z.object({
  round: z.string().trim().min(1, "Round is required").max(100),
  deadline: z.string().min(1, "Deadline is required"),
  notes: optionalString,
});

export const mbaScholarshipSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(300),
  amount: optionalNumber,
  currency: z.string().trim().min(1).max(10).default("EUR"),
  eligibility: optionalString,
  deadline: optionalDate,
  status: z.enum(["RESEARCHING", "PLANNED", "APPLYING", "SUBMITTED", "AWARDED", "REJECTED"]),
  requirements: optionalString,
  website: optionalString,
  notes: optionalString,
});
