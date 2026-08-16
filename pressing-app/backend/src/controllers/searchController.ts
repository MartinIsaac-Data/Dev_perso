import { Request, Response } from "express";
import { prisma } from "../lib/prisma";
import { branchScope } from "../middleware/auth";

export async function globalSearch(req: Request, res: Response) {
  const q = ((req.query.q as string) || "").trim();
  if (q.length < 2) return res.json({ customers: [], orders: [], articles: [] });

  const scope = branchScope(req.user!);

  const [customers, orders, articles] = await Promise.all([
    prisma.customer.findMany({
      where: {
        active: true,
        ...scope,
        OR: [
          { fullName: { contains: q, mode: "insensitive" } },
          { phone: { contains: q } },
        ],
      },
      take: 5,
      select: { id: true, fullName: true, phone: true },
    }),
    prisma.order.findMany({
      where: {
        ...scope,
        OR: [
          { orderNumber: { contains: q, mode: "insensitive" } },
          { customer: { phone: { contains: q } } },
        ],
      },
      take: 5,
      select: { id: true, orderNumber: true, status: true, customer: { select: { fullName: true } } },
    }),
    prisma.orderItem.findMany({
      where: { articleType: { contains: q, mode: "insensitive" }, order: scope },
      take: 5,
      select: { id: true, articleType: true, category: true, orderId: true, order: { select: { orderNumber: true } } },
    }),
  ]);

  res.json({ customers, orders, articles });
}
