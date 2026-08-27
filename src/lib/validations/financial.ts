import { z } from "zod";

const optionalNumber = z
  .string()
  .optional()
  .transform((v) => (v === "" || v === undefined ? undefined : Number(v)));

const numberOrZero = z
  .string()
  .optional()
  .transform((v) => (v === "" || v === undefined ? 0 : Number(v)));

export const financialPlanSchema = z.object({
  targetYear: optionalNumber,
  tuition: optionalNumber,
  livingCost: optionalNumber,
  travelCost: optionalNumber,
  visaCost: optionalNumber,
  insuranceCost: optionalNumber,
  otherCost: optionalNumber,
  currency: z.string().trim().min(1).max(10).default("EUR"),
  currentSavings: numberOrZero,
  monthlyContribution: numberOrZero,
  annualContributionGrowthPct: numberOrZero,
  expectedAnnualReturnPct: numberOrZero,
  scholarshipTarget: numberOrZero,
  employerSponsorship: numberOrZero,
  studentLoanTarget: numberOrZero,
  familySupport: numberOrZero,
});

export type FinancialPlanFormValues = z.infer<typeof financialPlanSchema>;

export const transactionSchema = z.object({
  label: z.string().trim().min(1, "Label is required").max(300),
  amount: z.string().min(1, "Amount is required").transform(Number),
  currency: z.string().trim().min(1).max(10).default("EUR"),
  date: z.string().min(1, "Date is required"),
  category: z
    .string()
    .trim()
    .max(200)
    .optional()
    .transform((v) => (v === "" ? undefined : v)),
  notes: z
    .string()
    .trim()
    .max(1000)
    .optional()
    .transform((v) => (v === "" ? undefined : v)),
});

export type TransactionFormValues = z.infer<typeof transactionSchema>;
