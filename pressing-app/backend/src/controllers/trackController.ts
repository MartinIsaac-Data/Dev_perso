import { Request, Response } from "express";
import { prisma } from "../lib/prisma";
import { ApiError } from "../middleware/errorHandler";

export async function trackOrder(req: Request, res: Response) {
  const { orderNumber, phone } = req.query as Record<string, string>;
  if (!orderNumber && !phone) {
    throw new ApiError(400, "Provide orderNumber or phone");
  }

  const orders = await prisma.order.findMany({
    where: {
      ...(orderNumber ? { orderNumber } : {}),
      ...(phone ? { customer: { phone } } : {}),
    },
    orderBy: { createdAt: "desc" },
    take: 10,
    select: {
      id: true,
      orderNumber: true,
      status: true,
      depositDate: true,
      estimatedReadyDate: true,
      completedDate: true,
      total: true,
      paidAmount: true,
      balance: true,
      customer: { select: { fullName: true } },
      statusHistory: { orderBy: { createdAt: "asc" }, select: { status: true, createdAt: true, note: true } },
      items: { select: { articleType: true, quantity: true } },
    },
  });

  if (orders.length === 0) throw new ApiError(404, "No order found");
  res.json(orders);
}
