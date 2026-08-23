import type { OrderStatus, OrderSource, PaymentStatus, DeliveryStatusValue } from "@/types";

type Tone = "default" | "success" | "warning" | "destructive" | "muted";

export const ORDER_STATUS_LABELS: Record<OrderStatus, string> = {
  RECEIVED: "Reçue",
  INSPECTION: "Inspection",
  PROCESSING: "En traitement",
  QUALITY_CHECK: "Contrôle qualité",
  READY: "Prête",
  OUT_FOR_DELIVERY: "En livraison",
  DELIVERED: "Livrée",
  COMPLETED: "Terminée",
  CANCELLED: "Annulée",
};

export const ORDER_STATUS_TONE: Record<OrderStatus, Tone> = {
  RECEIVED: "muted",
  INSPECTION: "default",
  PROCESSING: "default",
  QUALITY_CHECK: "warning",
  READY: "success",
  OUT_FOR_DELIVERY: "default",
  DELIVERED: "success",
  COMPLETED: "success",
  CANCELLED: "destructive",
};

export const ORDER_STATUS_FLOW: OrderStatus[] = [
  "RECEIVED",
  "INSPECTION",
  "PROCESSING",
  "QUALITY_CHECK",
  "READY",
  "OUT_FOR_DELIVERY",
  "DELIVERED",
  "COMPLETED",
];

export const PAYMENT_STATUS_LABELS: Record<PaymentStatus, string> = {
  UNPAID: "Non payée",
  PARTIAL: "Partiel",
  PAID: "Payée",
  REFUNDED: "Remboursée",
};

export const PAYMENT_STATUS_TONE: Record<PaymentStatus, Tone> = {
  UNPAID: "destructive",
  PARTIAL: "warning",
  PAID: "success",
  REFUNDED: "muted",
};

export const DELIVERY_STATUS_LABELS: Record<DeliveryStatusValue, string> = {
  PENDING: "En attente",
  ASSIGNED: "Assignée",
  PICKED_UP: "Récupérée",
  IN_TRANSIT: "En route",
  DELIVERED: "Livrée",
  FAILED: "Échec",
};

export const ORDER_SOURCE_LABELS: Record<OrderSource, string> = {
  PHYSICAL: "🏪 Boutique",
  ONLINE: "🌐 En ligne",
};

export const ARTICLE_CATEGORY_LABELS: Record<string, string> = {
  SHIRT: "Chemise",
  TSHIRT: "T-shirt",
  PANTS: "Pantalon",
  JEANS: "Jean",
  SUIT: "Costume",
  JACKET: "Veste",
  DRESS: "Robe",
  SKIRT: "Jupe",
  COAT: "Manteau",
  BEDSHEET: "Drap",
  BLANKET: "Couverture",
  CURTAIN: "Rideau",
  SHOES: "Chaussures",
  BAG: "Sac",
  OTHER: "Autre",
};
