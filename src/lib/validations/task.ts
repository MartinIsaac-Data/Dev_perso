import { z } from "zod";
import { PRIORITIES, TASK_STATUSES } from "@/lib/labels";

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

export const taskSchema = z.object({
  title: z.string().trim().min(1, "Title is required").max(300),
  description: optionalString,
  category: optionalString,
  priority: z.enum(PRIORITIES),
  status: z.enum(TASK_STATUSES),
  deadline: optionalDate,
});

export type TaskFormValues = z.infer<typeof taskSchema>;
