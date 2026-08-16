import { OrderStatus } from "@prisma/client";

const TRANSITIONS: Record<OrderStatus, OrderStatus[]> = {
  RECEIVED: ["INSPECTION", "CANCELLED"],
  INSPECTION: ["PROCESSING", "CANCELLED"],
  PROCESSING: ["QUALITY_CHECK", "CANCELLED"],
  QUALITY_CHECK: ["PROCESSING", "READY", "CANCELLED"],
  READY: ["OUT_FOR_DELIVERY", "DELIVERED", "COMPLETED", "CANCELLED"],
  OUT_FOR_DELIVERY: ["DELIVERED", "CANCELLED"],
  DELIVERED: ["COMPLETED"],
  COMPLETED: [],
  CANCELLED: [],
};

export function canTransition(from: OrderStatus, to: OrderStatus): boolean {
  if (from === to) return false;
  return TRANSITIONS[from]?.includes(to) ?? false;
}

export function nextPossibleStatuses(from: OrderStatus): OrderStatus[] {
  return TRANSITIONS[from] ?? [];
}
