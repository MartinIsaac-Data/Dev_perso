import { Request, Response } from "express";
import { prisma } from "../lib/prisma";
import { paymentIntentInitiateSchema } from "../validators/paymentIntentValidators";
import { ApiError } from "../middleware/errorHandler";
import { checkPaymentIntent, initiatePaymentIntent, assertIntentVisible } from "../services/paymentIntentService";

export async function initiateOrderMobileMoneyPayment(req: Request, res: Response) {
  const data = paymentIntentInitiateSchema.parse(req.body);
  const order = await prisma.order.findUnique({ where: { id: req.params.id } });
  if (!order) throw new ApiError(404, "Order not found");
  assertIntentVisible(req.user!, order.branchId);

  const { intent, redirectUrl } = await initiatePaymentIntent({
    orderId: order.id,
    provider: data.provider,
    phone: data.phone,
    amount: data.amount,
    initiatedById: req.user!.id,
  });

  res.status(201).json({ ...intent, redirectUrl });
}

export async function getPaymentIntentStatusForStaff(req: Request, res: Response) {
  const intent = await prisma.paymentIntent.findUnique({
    where: { id: req.params.id },
    include: { order: { select: { branchId: true } } },
  });
  if (!intent) throw new ApiError(404, "Payment intent not found");
  assertIntentVisible(req.user!, intent.order.branchId);

  const updated = await checkPaymentIntent(intent.id);
  res.json(updated);
}
