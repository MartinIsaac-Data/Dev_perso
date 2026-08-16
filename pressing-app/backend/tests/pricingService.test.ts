import { describe, expect, it } from "vitest";
import {
  computeBalance,
  computeItemTotal,
  computeOrderTotals,
  computePaymentStatus,
} from "../src/services/pricingService";

describe("computeItemTotal", () => {
  it("multiplies unit price by quantity", () => {
    expect(computeItemTotal({ quantity: 3, unitPrice: 1000 }).toNumber()).toBe(3000);
  });

  it("rounds to 2 decimal places", () => {
    expect(computeItemTotal({ quantity: 1, unitPrice: 1000.004 }).toNumber()).toBe(1000);
    expect(computeItemTotal({ quantity: 3, unitPrice: 999.995 }).toNumber()).toBe(2999.99);
  });
});

describe("computeOrderTotals", () => {
  it("computes subtotal + deliveryFee - discount = total", () => {
    const totals = computeOrderTotals([1000, 1500, 500], 200, 1000);
    expect(totals.subtotal.toNumber()).toBe(3000);
    expect(totals.total.toNumber()).toBe(3800);
  });

  it("never returns a negative total", () => {
    const totals = computeOrderTotals([1000], 5000, 0);
    expect(totals.total.toNumber()).toBe(0);
  });

  it("handles an empty item list", () => {
    const totals = computeOrderTotals([], 0, 0);
    expect(totals.subtotal.toNumber()).toBe(0);
    expect(totals.total.toNumber()).toBe(0);
  });
});

describe("computeBalance / computePaymentStatus", () => {
  it("reports UNPAID when nothing has been paid", () => {
    expect(computePaymentStatus(5000, 0)).toBe("UNPAID");
    expect(computeBalance(5000, 0).toNumber()).toBe(5000);
  });

  it("reports PARTIAL when paid less than total", () => {
    expect(computePaymentStatus(5000, 2000)).toBe("PARTIAL");
    expect(computeBalance(5000, 2000).toNumber()).toBe(3000);
  });

  it("reports PAID when fully paid, balance floors at 0", () => {
    expect(computePaymentStatus(5000, 5000)).toBe("PAID");
    expect(computeBalance(5000, 5000).toNumber()).toBe(0);
    expect(computeBalance(5000, 6000).toNumber()).toBe(0);
  });
});
