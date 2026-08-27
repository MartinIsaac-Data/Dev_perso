import { z } from "zod";
import { APPLICATION_STATUSES } from "@/lib/labels";

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

const checkbox = z
  .union([z.boolean(), z.string()])
  .optional()
  .transform((v) => v === true || v === "true" || v === "on");

export const mbaApplicationSchema = z.object({
  programId: z.string().min(1, "Program is required"),
  intake: optionalString,
  round: optionalString,
  deadline: optionalDate,
  status: z.enum(APPLICATION_STATUSES),
  cvReady: checkbox,
  essaysReady: checkbox,
  recommendationsReady: checkbox,
  transcriptReady: checkbox,
  testScoreReady: checkbox,
  englishTestReady: checkbox,
  passportReady: checkbox,
  notes: optionalString,
});

export type MBAApplicationFormValues = z.infer<typeof mbaApplicationSchema>;
