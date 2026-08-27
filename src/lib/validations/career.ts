import { z } from "zod";
import { EMPLOYMENT_TYPES } from "@/lib/labels";

const optionalDate = z
  .string()
  .optional()
  .transform((v) => (v === "" || v === undefined ? undefined : v));

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

export const careerExperienceSchema = z.object({
  company: z.string().trim().min(1, "Company is required").max(300),
  role: z.string().trim().min(1, "Role is required").max(300),
  department: optionalString,
  location: optionalString,
  startDate: z.string().min(1, "Start date is required"),
  endDate: optionalDate,
  isCurrent: z.boolean().default(false),
  employmentType: z.enum(EMPLOYMENT_TYPES),
  responsibilities: optionalString,
  teamSize: z
    .string()
    .optional()
    .transform((v) => (v === "" || v === undefined ? undefined : Number(v))),
  manager: optionalString,
  countriesCovered: csvList,
  skillsUsed: csvList,
});

export type CareerExperienceFormValues = z.infer<typeof careerExperienceSchema>;

export const achievementSchema = z.object({
  title: z.string().trim().min(1, "Title is required").max(300),
  description: optionalString,
  date: optionalDate,
});

export type AchievementFormValues = z.infer<typeof achievementSchema>;
