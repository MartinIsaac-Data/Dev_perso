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

/**
 * Customer-facing wording for each status, sent automatically on every
 * transition (see notifyOrderStatusChange in notificationService.ts) so the
 * order tracking page and the customer's phone always agree.
 */
export const STATUS_MESSAGES: Record<OrderStatus, (orderNumber: string) => string> = {
  RECEIVED: (n) => `Votre commande ${n} a bien été reçue.`,
  INSPECTION: (n) => `Votre commande ${n} est en cours d'inspection.`,
  PROCESSING: (n) => `Votre commande ${n} est en cours de traitement.`,
  QUALITY_CHECK: (n) => `Votre commande ${n} est en contrôle qualité.`,
  READY: (n) => `Votre commande ${n} est prête. Vous pouvez venir la récupérer.`,
  OUT_FOR_DELIVERY: (n) => `Votre commande ${n} est en cours de livraison.`,
  DELIVERED: (n) => `Votre commande ${n} a été livrée. Merci de votre confiance.`,
  COMPLETED: (n) => `Votre commande ${n} est clôturée. Merci de votre confiance !`,
  CANCELLED: (n) => `Votre commande ${n} a été annulée.`,
};
