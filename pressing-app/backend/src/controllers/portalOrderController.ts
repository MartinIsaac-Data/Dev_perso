import { Request, Response } from "express";
import { prisma } from "../lib/prisma";
import { portalOrderCreateSchema } from "../validators/portalOrderValidators";
import { ApiError } from "../middleware/errorHandler";
import { recordAudit } from "../services/auditService";
import { generateOrderNumber } from "../utils/orderNumber";
import { computeItemTotal, computeOrderTotals } from "../services/pricingService";
import { notify } from "../services/notificationService";
import { getDefaultBranchId } from "../services/branchService";

const DELIVERY_FEE = 1000;

const orderInclude = {
  items: { include: { service: true } },
  payments: { orderBy: { paidAt: "desc" as const } },
  delivery: true,
  statusHistory: { orderBy: { createdAt: "asc" as const } },
};

export async function listActiveServices(_req: Request, res: Response) {
  const services = await prisma.service.findMany({
    where: { active: true },
    orderBy: { name: "asc" },
  });
  res.json(services);
}

export async function createOwnOrder(req: Request, res: Response) {
  const data = portalOrderCreateSchema.parse(req.body);
  const customer = await prisma.customer.findUniqueOrThrow({ where: { id: req.customerId! } });

  if (data.fulfillment === "DELIVERY" && !data.deliveryAddress && !customer.address) {
    throw new ApiError(400, "Une adresse de livraison est requise");
  }

  const serviceIds = [...new Set(data.items.map((i) => i.serviceId))];
  const services = await prisma.service.findMany({ where: { id: { in: serviceIds }, active: true } });
  const serviceMap = new Map(services.map((s) => [s.id, s]));
  for (const id of serviceIds) {
    if (!serviceMap.has(id)) throw new ApiError(400, `Service ${id} introuvable`);
  }

  const itemsWithPrice = data.items.map((item) => {
    const service = serviceMap.get(item.serviceId)!;
    const unitPrice = item.isExpress && service.expressPrice ? service.expressPrice : service.price;
    const totalPrice = computeItemTotal({ quantity: item.quantity, unitPrice });
    return { ...item, unitPrice, totalPrice };
  });

  // Defensive: customers registered before this fallback existed, or any
  // future signup path that skips it, must still produce orders staff can
  // actually see (list endpoints filter by the caller's branchId).
  const branchId = customer.branchId ?? (await getDefaultBranchId());

  const deliveryFee = data.fulfillment === "DELIVERY" ? DELIVERY_FEE : 0;
  const totals = computeOrderTotals(
    itemsWithPrice.map((i) => i.totalPrice),
    0,
    deliveryFee
  );

  const order = await prisma.$transaction(async (tx) => {
    const created = await tx.order.create({
      data: {
        orderNumber: generateOrderNumber(),
        customerId: customer.id,
        branchId,
        priority: data.priority,
        subtotal: totals.subtotal,
        discount: totals.discount,
        deliveryFee: totals.deliveryFee,
        total: totals.total,
        paidAmount: 0,
        balance: totals.total,
        paymentStatus: "UNPAID",
        notes: data.notes ? `[Réservation en ligne] ${data.notes}` : "[Réservation en ligne]",
        items: {
          create: itemsWithPrice.map((item) => ({
            category: item.category,
            articleType: item.articleType,
            quantity: item.quantity,
            color: item.color,
            brand: item.brand,
            size: item.size,
            conditionAtReceipt: item.conditionAtReceipt,
            existingStains: item.existingStains,
            existingDamages: item.existingDamages,
            specialInstructions: item.specialInstructions,
            serviceId: item.serviceId,
            isExpress: item.isExpress,
            unitPrice: item.unitPrice,
            totalPrice: item.totalPrice,
          })),
        },
        statusHistory: {
          create: { status: "RECEIVED", note: "Commande passée en ligne par le client" },
        },
      },
      include: orderInclude,
    });

    if (data.fulfillment === "DELIVERY") {
      await tx.delivery.create({
        data: {
          orderId: created.id,
          type: "DELIVERY",
          address: data.deliveryAddress ?? customer.address,
          neighborhood: data.deliveryNeighborhood,
          city: data.deliveryCity,
          phone: customer.phone,
          fee: DELIVERY_FEE,
          status: "PENDING",
        },
      });
    }

    return created;
  });

  await recordAudit({
    action: "PORTAL_ORDER_CREATE",
    entityType: "Order",
    entityId: order.id,
    newValue: order,
  });

  await notify(
    "SMS",
    customer.phone,
    `Votre réservation en ligne ${order.orderNumber} a bien été enregistrée. Total estimé : ${totals.total} FCFA.`,
    { relatedOrderId: order.id }
  );

  res.status(201).json(order);
}

export async function listOwnOrders(req: Request, res: Response) {
  const orders = await prisma.order.findMany({
    where: { customerId: req.customerId! },
    orderBy: { createdAt: "desc" },
    include: { items: true, delivery: true },
  });
  res.json(orders);
}

export async function getOwnOrder(req: Request, res: Response) {
  const order = await prisma.order.findFirst({
    where: { id: req.params.id, customerId: req.customerId! },
    include: orderInclude,
  });
  if (!order) throw new ApiError(404, "Commande introuvable");
  res.json(order);
}
