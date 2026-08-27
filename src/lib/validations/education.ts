import { z } from "zod";

const optionalDate = z
  .string()
  .optional()
  .transform((v) => (v === "" || v === undefined ? undefined : v));

const optionalString = z
  .string()
  .trim()
  .max(500)
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

export const educationSchema = z.object({
  degree: z.string().trim().min(1, "Degree is required").max(300),
  university: z.string().trim().min(1, "University is required").max(300),
  field: optionalString,
  country: optionalString,
  startDate: optionalDate,
  endDate: optionalDate,
  gradeGpa: optionalString,
  honors: optionalString,
  relevantCoursework: csvList,
  documentUrl: optionalString,
});

export type EducationFormValues = z.infer<typeof educationSchema>;
