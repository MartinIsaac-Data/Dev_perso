import { Decimal } from "@prisma/client/runtime/library";

export interface PricedItemInput {
  quantity: number;
  unitPrice: Decimal | number | string;
}

/** unitPrice * quantity, rounded to 2 decimals — used for every order item. */
export function computeItemTotal(item: PricedItemInput): Decimal {
  const unit = new Decimal(item.unitPrice);
  return unit.mul(item.quantity).toDecimalPlaces(2);
}

export interface OrderTotals {
  subtotal: Decimal;
  discount: Decimal;
  deliveryFee: Decimal;
  total: Decimal;
}

/** subtotal + deliveryFee - discount = total, per section 9 of the spec. */
export function computeOrderTotals(
  itemTotals: Decimal[],
  discount: Decimal | number | string = 0,
  deliveryFee: Decimal | number | string = 0
): OrderTotals {
  const subtotal = itemTotals
    .reduce((sum, t) => sum.add(t), new Decimal(0))
    .toDecimalPlaces(2);
  const discountDecimal = new Decimal(discount).toDecimalPlaces(2);
  const deliveryFeeDecimal = new Decimal(deliveryFee).toDecimalPlaces(2);
  const total = subtotal
    .add(deliveryFeeDecimal)
    .sub(discountDecimal)
    .toDecimalPlaces(2);
  return {
    subtotal,
    discount: discountDecimal,
    deliveryFee: deliveryFeeDecimal,
    total: total.isNegative() ? new Decimal(0) : total,
  };
}

export type PaymentStatusValue = "UNPAID" | "PARTIAL" | "PAID" | "REFUNDED";

export function computeBalance(total: Decimal | number | string, paidAmount: Decimal | number | string) {
  const totalDecimal = new Decimal(total);
  const paidDecimal = new Decimal(paidAmount);
  const balance = totalDecimal.sub(paidDecimal).toDecimalPlaces(2);
  return balance.isNegative() ? new Decimal(0) : balance;
}

export function computePaymentStatus(
  total: Decimal | number | string,
  paidAmount: Decimal | number | string
): PaymentStatusValue {
  const totalDecimal = new Decimal(total);
  const paidDecimal = new Decimal(paidAmount);
  if (paidDecimal.lte(0)) return "UNPAID";
  if (paidDecimal.gte(totalDecimal)) return "PAID";
  return "PARTIAL";
}
