import { Wallet } from "lucide-react";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { PageHeader } from "@/components/shared/page-header";
import { KpiCard } from "@/components/shared/kpi-card";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FinancialPlanForm, type FinancialPlanValues } from "@/app/(app)/financial-plan/financial-plan-form";
import { SavingsChart } from "@/app/(app)/financial-plan/savings-chart";
import { TransactionPanel } from "@/app/(app)/financial-plan/transaction-panel";

export default async function FinancialPlanPage() {
  const userId = await requireUserId();
  const [plan, transactions] = await Promise.all([
    prisma.financialPlan.findFirst({ where: { userId } }),
    prisma.financialTransaction.findMany({ where: { userId }, orderBy: { date: "desc" } }),
  ]);

  const totalCost =
    Number(plan?.tuition ?? 0) +
    Number(plan?.livingCost ?? 0) +
    Number(plan?.travelCost ?? 0) +
    Number(plan?.visaCost ?? 0) +
    Number(plan?.insuranceCost ?? 0) +
    Number(plan?.otherCost ?? 0);

  const plannedFunding =
    Number(plan?.currentSavings ?? 0) +
    Number(plan?.scholarshipTarget ?? 0) +
    Number(plan?.employerSponsorship ?? 0) +
    Number(plan?.studentLoanTarget ?? 0) +
    Number(plan?.familySupport ?? 0);

  const gap = totalCost - plannedFunding;
  const currency = plan?.currency ?? "EUR";

  const currentYear = new Date().getFullYear();
  const targetYear = plan?.targetYear ?? currentYear + 4;
  const currentSavings = Number(plan?.currentSavings ?? 0);
  const monthlyContribution = Number(plan?.monthlyContribution ?? 0);
  const contributionGrowth = Number(plan?.annualContributionGrowthPct ?? 0) / 100;
  const expectedReturn = Number(plan?.expectedAnnualReturnPct ?? 0) / 100;

  const projection: { year: number; balance: number }[] = [{ year: currentYear, balance: currentSavings }];
  let balance = currentSavings;
  for (let year = currentYear + 1; year <= targetYear; year++) {
    const yearsElapsed = year - currentYear - 1;
    const annualContribution = monthlyContribution * 12 * Math.pow(1 + contributionGrowth, yearsElapsed);
    balance = balance * (1 + expectedReturn) + annualContribution;
    projection.push({ year, balance: Math.round(balance) });
  }

  const initialValues: FinancialPlanValues = {
    targetYear: plan?.targetYear?.toString() ?? "",
    tuition: plan?.tuition?.toString() ?? "",
    livingCost: plan?.livingCost?.toString() ?? "",
    travelCost: plan?.travelCost?.toString() ?? "",
    visaCost: plan?.visaCost?.toString() ?? "",
    insuranceCost: plan?.insuranceCost?.toString() ?? "",
    otherCost: plan?.otherCost?.toString() ?? "",
    currency: plan?.currency ?? "EUR",
    currentSavings: plan?.currentSavings?.toString() ?? "0",
    monthlyContribution: plan?.monthlyContribution?.toString() ?? "0",
    annualContributionGrowthPct: plan?.annualContributionGrowthPct?.toString() ?? "0",
    expectedAnnualReturnPct: plan?.expectedAnnualReturnPct?.toString() ?? "0",
    scholarshipTarget: plan?.scholarshipTarget?.toString() ?? "0",
    employerSponsorship: plan?.employerSponsorship?.toString() ?? "0",
    studentLoanTarget: plan?.studentLoanTarget?.toString() ?? "0",
    familySupport: plan?.familySupport?.toString() ?? "0",
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Financial Plan"
        description="Estimated cost, funding sources, and a savings projection toward your target year."
      />

      {plan && totalCost > 0 && (
        <div className="grid gap-4 sm:grid-cols-3">
          <KpiCard label="Estimated total cost" value={`${totalCost.toLocaleString()} ${currency}`} icon={Wallet} />
          <KpiCard label="Planned funding" value={`${plannedFunding.toLocaleString()} ${currency}`} />
          <KpiCard
            label={gap > 0 ? "Funding gap" : "Projected surplus"}
            value={`${Math.abs(gap).toLocaleString()} ${currency}`}
            trend={{
              direction: gap > 0 ? "down" : "up",
              label: gap > 0 ? "Still to secure" : "Covered",
            }}
          />
        </div>
      )}

      {(monthlyContribution > 0 || currentSavings > 0) && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Savings projection</CardTitle>
            <CardDescription>
              A planning projection assuming steady contributions and returns — not a guarantee.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <SavingsChart data={projection} targetCost={totalCost} />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent>
          <TransactionPanel
            transactions={transactions.map((t) => ({
              id: t.id,
              label: t.label,
              amount: t.amount.toString(),
              currency: t.currency,
              date: t.date,
              category: t.category,
            }))}
          />
        </CardContent>
      </Card>

      <FinancialPlanForm initialValues={initialValues} />
    </div>
  );
}
