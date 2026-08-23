import { describe, expect, it } from "vitest";
import { computeTheoreticalBalance, signedAmount } from "../src/services/cashService";

describe("signedAmount", () => {
  it("treats sales and deposits as inflows", () => {
    expect(signedAmount("SALE", 1000).toNumber()).toBe(1000);
    expect(signedAmount("DEPOSIT", 1000).toNumber()).toBe(1000);
  });

  it("treats expenses, refunds and withdrawals as outflows", () => {
    expect(signedAmount("EXPENSE", 1000).toNumber()).toBe(-1000);
    expect(signedAmount("REFUND", 1000).toNumber()).toBe(-1000);
    expect(signedAmount("WITHDRAWAL", 1000).toNumber()).toBe(-1000);
  });

  it("keeps the adjustment's own sign", () => {
    expect(signedAmount("ADJUSTMENT", -500).toNumber()).toBe(-500);
    expect(signedAmount("ADJUSTMENT", 500).toNumber()).toBe(500);
  });
});

describe("computeTheoreticalBalance", () => {
  it("only counts cash-method transactions", () => {
    const balance = computeTheoreticalBalance(10000, [
      { type: "SALE", amount: 5000, method: "CASH" },
      { type: "SALE", amount: 8000, method: "ORANGE_MONEY" },
      { type: "EXPENSE", amount: 2000, method: "CASH" },
    ]);
    expect(balance.toNumber()).toBe(13000);
  });
});
