import { z } from "zod";
import { LEADERSHIP_TYPES } from "@/lib/labels";

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

export const leadershipSchema = z.object({
  type: z.enum(LEADERSHIP_TYPES),
  title: z.string().trim().min(1, "Title is required").max(300),
  organization: optionalString,
  role: optionalString,
  teamSize: z
    .string()
    .optional()
    .transform((v) => (v === "" || v === undefined ? undefined : Number(v))),
  startDate: optionalDate,
  endDate: optionalDate,
  isOngoing: z.boolean().default(false),
  responsibilities: optionalString,
  results: optionalString,
  skillsUsed: csvList,
});

export type LeadershipFormValues = z.infer<typeof leadershipSchema>;
