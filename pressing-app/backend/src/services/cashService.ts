import { CashTransactionType } from "@prisma/client";
import { Decimal } from "@prisma/client/runtime/library";

const INFLOW: CashTransactionType[] = ["SALE", "DEPOSIT"];
const OUTFLOW: CashTransactionType[] = ["EXPENSE", "REFUND", "WITHDRAWAL"];

/** Adjustment transactions carry their own sign; every other type is fixed by its kind. */
export function signedAmount(type: CashTransactionType, amount: Decimal | number | string): Decimal {
  const value = new Decimal(amount).abs();
  if (INFLOW.includes(type)) return value;
  if (OUTFLOW.includes(type)) return value.neg();
  return new Decimal(amount);
}

export function computeTheoreticalBalance(
  openingBalance: Decimal | number | string,
  transactions: { type: CashTransactionType; amount: Decimal | number | string; method: string }[]
): Decimal {
  return transactions
    .filter((t) => t.method === "CASH")
    .reduce((sum, t) => sum.add(signedAmount(t.type, t.amount)), new Decimal(openingBalance));
}
