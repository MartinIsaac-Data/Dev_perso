import { Request, Response } from "express";
import { prisma } from "../lib/prisma";
import { deliveryCreateSchema, deliveryUpdateSchema } from "../validators/deliveryValidators";
import { ApiError } from "../middleware/errorHandler";
import { recordAudit } from "../services/auditService";
import { STATUS_MESSAGES } from "../services/orderStatusService";
import { notifyOrderStatusChange } from "../services/notificationService";

const deliveryInclude = {
  order: { include: { customer: true } },
  deliverer: { select: { id: true, fullName: true, phone: true } },
};

export async function listDeliveries(req: Request, res: Response) {
  const { status, delivererId, today } = req.query as Record<string, string>;

  const startOfDay = new Date();
  startOfDay.setHours(0, 0, 0, 0);
  const endOfDay = new Date();
  endOfDay.setHours(23, 59, 59, 999);

  const deliveries = await prisma.delivery.findMany({
    where: {
      ...(status ? { status: status as never } : {}),
      ...(delivererId ? { delivererId } : {}),
      ...(today === "true" ? { scheduledDate: { gte: startOfDay, lte: endOfDay } } : {}),
    },
    orderBy: { scheduledDate: "asc" },
    include: deliveryInclude,
  });
  res.json(deliveries);
}

export async function createDelivery(req: Request, res: Response) {
  const data = deliveryCreateSchema.parse(req.body);
  const order = await prisma.order.findUnique({ where: { id: data.orderId } });
  if (!order) throw new ApiError(404, "Order not found");

  const delivery = await prisma.delivery.create({
    data: { ...data, status: data.delivererId ? "ASSIGNED" : "PENDING" },
    include: deliveryInclude,
  });

  await recordAudit({
    userId: req.user!.id,
    action: "CREATE",
    entityType: "Delivery",
    entityId: delivery.id,
    newValue: delivery,
  });

  res.status(201).json(delivery);
}

export async function updateDelivery(req: Request, res: Response) {
  const data = deliveryUpdateSchema.parse(req.body);
  const existing = await prisma.delivery.findUnique({ where: { id: req.params.id } });
  if (!existing) throw new ApiError(404, "Delivery not found");

  const delivery = await prisma.delivery.update({
    where: { id: req.params.id },
    data: {
      ...data,
      status: data.status ?? (data.delivererId && existing.status === "PENDING" ? "ASSIGNED" : undefined),
      deliveredDate: data.status === "DELIVERED" ? new Date() : undefined,
    },
    include: deliveryInclude,
  });

  if (data.status === "DELIVERED") {
    await prisma.order.update({ where: { id: delivery.orderId }, data: { status: "DELIVERED" } });
    await prisma.orderStatusHistory.create({
      data: { orderId: delivery.orderId, status: "DELIVERED", changedById: req.user!.id, note: "Livraison confirmée" },
    });
    await notifyOrderStatusChange(
      delivery.order.customer.phone,
      delivery.orderId,
      STATUS_MESSAGES.DELIVERED(delivery.order.orderNumber)
    );
  } else if (data.status === "IN_TRANSIT" && delivery.order.status !== "OUT_FOR_DELIVERY") {
    await prisma.order.update({ where: { id: delivery.orderId }, data: { status: "OUT_FOR_DELIVERY" } });
    await prisma.orderStatusHistory.create({
      data: { orderId: delivery.orderId, status: "OUT_FOR_DELIVERY", changedById: req.user!.id, note: "Livreur en route" },
    });
    await notifyOrderStatusChange(
      delivery.order.customer.phone,
      delivery.orderId,
      STATUS_MESSAGES.OUT_FOR_DELIVERY(delivery.order.orderNumber)
    );
  } else if (data.status === "FAILED") {
    await notifyOrderStatusChange(
      delivery.order.customer.phone,
      delivery.orderId,
      `La livraison de votre commande ${delivery.order.orderNumber} a échoué. Nous vous recontacterons pour la reprogrammer.`
    );
  }

  await recordAudit({
    userId: req.user!.id,
    action: "UPDATE",
    entityType: "Delivery",
    entityId: delivery.id,
    oldValue: existing,
    newValue: delivery,
  });

  res.json(delivery);
}
