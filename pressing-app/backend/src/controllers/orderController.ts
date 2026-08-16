import { Request, Response } from "express";
import QRCode from "qrcode";
import { prisma } from "../lib/prisma";
import {
  orderCreateSchema,
  orderStatusSchema,
  orderUpdateSchema,
  paymentCreateSchema,
} from "../validators/orderValidators";
import { ApiError } from "../middleware/errorHandler";
import { recordAudit } from "../services/auditService";
import { generateOrderNumber } from "../utils/orderNumber";
import { computeBalance, computeItemTotal, computeOrderTotals, computePaymentStatus } from "../services/pricingService";
import { canTransition } from "../services/orderStatusService";
import { branchScope } from "../middleware/auth";
import { notify } from "../services/notificationService";

const orderInclude = {
  customer: true,
  employee: { select: { id: true, fullName: true } },
  items: { include: { service: true } },
  payments: { orderBy: { paidAt: "desc" as const } },
  delivery: true,
  statusHistory: { orderBy: { createdAt: "asc" as const } },
};

export async function listOrders(req: Request, res: Response) {
  const { status, customerId, search, from, to, page = "1", pageSize = "20" } = req.query as Record<
    string,
    string
  >;
  const take = Math.min(Number(pageSize) || 20, 100);
  const skip = (Math.max(Number(page) || 1, 1) - 1) * take;

  const where = {
    ...branchScope(req.user!),
    ...(status ? { status: status as never } : {}),
    ...(customerId ? { customerId } : {}),
    ...(from || to
      ? {
          depositDate: {
            ...(from ? { gte: new Date(from) } : {}),
            ...(to ? { lte: new Date(to) } : {}),
          },
        }
      : {}),
    ...(search
      ? {
          OR: [
            { orderNumber: { contains: search, mode: "insensitive" as const } },
            { customer: { fullName: { contains: search, mode: "insensitive" as const } } },
            { customer: { phone: { contains: search } } },
          ],
        }
      : {}),
  };

  const [orders, total] = await Promise.all([
    prisma.order.findMany({
      where,
      orderBy: { createdAt: "desc" },
      take,
      skip,
      include: { customer: true, items: true },
    }),
    prisma.order.count({ where }),
  ]);

  res.json({ data: orders, total, page: Number(page) || 1, pageSize: take });
}

export async function getOrder(req: Request, res: Response) {
  const order = await prisma.order.findUnique({
    where: { id: req.params.id },
    include: orderInclude,
  });
  if (!order) throw new ApiError(404, "Order not found");
  res.json(order);
}

export async function createOrder(req: Request, res: Response) {
  const data = orderCreateSchema.parse(req.body);

  const customer = await prisma.customer.findUnique({ where: { id: data.customerId } });
  if (!customer) throw new ApiError(404, "Customer not found");

  const serviceIds = [...new Set(data.items.map((i) => i.serviceId))];
  const services = await prisma.service.findMany({ where: { id: { in: serviceIds } } });
  const serviceMap = new Map(services.map((s) => [s.id, s]));
  for (const id of serviceIds) {
    if (!serviceMap.has(id)) throw new ApiError(400, `Service ${id} not found`);
  }

  const itemsWithPrice = data.items.map((item) => {
    const service = serviceMap.get(item.serviceId)!;
    const unitPrice = item.isExpress && service.expressPrice ? service.expressPrice : service.price;
    const totalPrice = computeItemTotal({ quantity: item.quantity, unitPrice });
    return { ...item, unitPrice, totalPrice };
  });

  const totals = computeOrderTotals(
    itemsWithPrice.map((i) => i.totalPrice),
    data.discount,
    data.deliveryFee
  );

  const initialPaidAmount = data.initialPayment?.amount ?? 0;
  const balance = computeBalance(totals.total, initialPaidAmount);
  const paymentStatus = computePaymentStatus(totals.total, initialPaidAmount);

  const order = await prisma.$transaction(async (tx) => {
    const created = await tx.order.create({
      data: {
        orderNumber: generateOrderNumber(),
        customerId: data.customerId,
        branchId: data.branchId ?? req.user!.branchId,
        employeeId: req.user!.id,
        priority: data.priority,
        estimatedReadyDate: data.estimatedReadyDate,
        subtotal: totals.subtotal,
        discount: totals.discount,
        deliveryFee: totals.deliveryFee,
        total: totals.total,
        paidAmount: initialPaidAmount,
        balance,
        paymentStatus,
        notes: data.notes,
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
            photoUrl: item.photoUrl,
            serviceId: item.serviceId,
            isExpress: item.isExpress,
            unitPrice: item.unitPrice,
            totalPrice: item.totalPrice,
          })),
        },
        statusHistory: {
          create: { status: "RECEIVED", changedById: req.user!.id, note: "Commande créée" },
        },
      },
      include: orderInclude,
    });

    if (data.initialPayment) {
      await tx.payment.create({
        data: {
          orderId: created.id,
          customerId: data.customerId,
          amount: data.initialPayment.amount,
          method: data.initialPayment.method,
          reference: data.initialPayment.reference,
          receivedById: req.user!.id,
        },
      });

      const openRegister = await tx.cashRegister.findFirst({
        where: { status: "OPEN", ...branchScope(req.user!) },
      });
      if (openRegister) {
        await tx.cashTransaction.create({
          data: {
            cashRegisterId: openRegister.id,
            type: "SALE",
            amount: data.initialPayment.amount,
            method: data.initialPayment.method,
            description: `Paiement initial commande ${created.orderNumber}`,
            orderId: created.id,
            createdById: req.user!.id,
          },
        });
      }
    }

    return created;
  });

  await recordAudit({
    userId: req.user!.id,
    action: "CREATE",
    entityType: "Order",
    entityId: order.id,
    newValue: order,
  });

  await notify("SMS", customer.phone, `Votre commande ${order.orderNumber} a bien été reçue.`, {
    relatedOrderId: order.id,
  });

  res.status(201).json(order);
}

export async function updateOrder(req: Request, res: Response) {
  const data = orderUpdateSchema.parse(req.body);
  const existing = await prisma.order.findUnique({ where: { id: req.params.id }, include: { items: true } });
  if (!existing) throw new ApiError(404, "Order not found");

  const discount = data.discount ?? Number(existing.discount);
  const deliveryFee = data.deliveryFee ?? Number(existing.deliveryFee);
  const totals = computeOrderTotals(
    existing.items.map((i) => i.totalPrice),
    discount,
    deliveryFee
  );
  const balance = computeBalance(totals.total, existing.paidAmount);
  const paymentStatus = computePaymentStatus(totals.total, existing.paidAmount);

  const order = await prisma.order.update({
    where: { id: req.params.id },
    data: {
      priority: data.priority,
      estimatedReadyDate: data.estimatedReadyDate,
      notes: data.notes,
      discount: totals.discount,
      deliveryFee: totals.deliveryFee,
      total: totals.total,
      balance,
      paymentStatus,
    },
    include: orderInclude,
  });

  await recordAudit({
    userId: req.user!.id,
    action: "UPDATE",
    entityType: "Order",
    entityId: order.id,
    oldValue: existing,
    newValue: order,
  });

  res.json(order);
}

export async function updateOrderStatus(req: Request, res: Response) {
  const { status, note } = orderStatusSchema.parse(req.body);
  const existing = await prisma.order.findUnique({
    where: { id: req.params.id },
    include: { customer: true },
  });
  if (!existing) throw new ApiError(404, "Order not found");

  if (!canTransition(existing.status, status)) {
    throw new ApiError(400, `Cannot move order from ${existing.status} to ${status}`);
  }

  const order = await prisma.$transaction(async (tx) => {
    const updated = await tx.order.update({
      where: { id: req.params.id },
      data: {
        status,
        completedDate: status === "COMPLETED" ? new Date() : existing.completedDate,
      },
      include: orderInclude,
    });
    await tx.orderStatusHistory.create({
      data: { orderId: existing.id, status, note, changedById: req.user!.id },
    });
    return updated;
  });

  await recordAudit({
    userId: req.user!.id,
    action: "STATUS_CHANGE",
    entityType: "Order",
    entityId: order.id,
    oldValue: { status: existing.status },
    newValue: { status },
  });

  if (status === "READY") {
    await notify(
      "SMS",
      existing.customer.phone,
      `Votre commande ${existing.orderNumber} est prête. Vous pouvez venir la récupérer.`,
      { relatedOrderId: existing.id }
    );
  }
  if (status === "DELIVERED") {
    await notify(
      "SMS",
      existing.customer.phone,
      `Votre commande ${existing.orderNumber} a été livrée. Merci de votre confiance.`,
      { relatedOrderId: existing.id }
    );
  }

  res.json(order);
}

export async function addPayment(req: Request, res: Response) {
  const data = paymentCreateSchema.parse(req.body);
  const order = await prisma.order.findUnique({ where: { id: req.params.id } });
  if (!order) throw new ApiError(404, "Order not found");

  const currentPaid = Number(order.paidAmount) + data.amount;
  if (currentPaid > Number(order.total) + 0.01) {
    throw new ApiError(400, "Payment exceeds order balance");
  }
  const balance = computeBalance(order.total, currentPaid);
  const paymentStatus = computePaymentStatus(order.total, currentPaid);

  const updated = await prisma.$transaction(async (tx) => {
    await tx.payment.create({
      data: {
        orderId: order.id,
        customerId: order.customerId,
        amount: data.amount,
        method: data.method,
        reference: data.reference,
        notes: data.notes,
        receivedById: req.user!.id,
      },
    });

    const result = await tx.order.update({
      where: { id: order.id },
      data: { paidAmount: currentPaid, balance, paymentStatus },
      include: orderInclude,
    });

    const openRegister = await tx.cashRegister.findFirst({
      where: { status: "OPEN", ...branchScope(req.user!) },
    });
    if (openRegister) {
      await tx.cashTransaction.create({
        data: {
          cashRegisterId: openRegister.id,
          type: "SALE",
          amount: data.amount,
          method: data.method,
          description: `Paiement commande ${order.orderNumber}`,
          orderId: order.id,
          createdById: req.user!.id,
        },
      });
    }

    return result;
  });

  await recordAudit({
    userId: req.user!.id,
    action: "PAYMENT",
    entityType: "Order",
    entityId: order.id,
    newValue: { amount: data.amount, method: data.method },
  });

  res.status(201).json(updated);
}

export async function getTicket(req: Request, res: Response) {
  const order = await prisma.order.findUnique({
    where: { id: req.params.id },
    include: orderInclude,
  });
  if (!order) throw new ApiError(404, "Order not found");

  const trackingUrl = `${process.env.CORS_ORIGIN?.split(",")[0] ?? ""}/track?order=${order.orderNumber}`;
  const qrCodeDataUrl = await QRCode.toDataURL(trackingUrl);

  res.json({ order, qrCodeDataUrl, trackingUrl });
}
