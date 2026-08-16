import { Request, Response } from "express";
import { prisma } from "../lib/prisma";
import {
  inventoryTransactionSchema,
  productCreateSchema,
  productUpdateSchema,
} from "../validators/inventoryValidators";
import { ApiError } from "../middleware/errorHandler";
import { recordAudit } from "../services/auditService";
import { branchScope } from "../middleware/auth";

export async function listProducts(req: Request, res: Response) {
  const { lowStock } = req.query as Record<string, string>;
  const products = await prisma.product.findMany({
    where: { ...branchScope(req.user!) },
    orderBy: { name: "asc" },
  });
  const filtered =
    lowStock === "true" ? products.filter((p) => Number(p.currentStock) <= Number(p.minStock)) : products;
  res.json(filtered);
}

export async function createProduct(req: Request, res: Response) {
  const data = productCreateSchema.parse(req.body);
  const product = await prisma.product.create({
    data: { ...data, branchId: data.branchId ?? req.user!.branchId },
  });
  await recordAudit({
    userId: req.user!.id,
    action: "CREATE",
    entityType: "Product",
    entityId: product.id,
    newValue: product,
  });
  res.status(201).json(product);
}

export async function updateProduct(req: Request, res: Response) {
  const data = productUpdateSchema.parse(req.body);
  const existing = await prisma.product.findUnique({ where: { id: req.params.id } });
  if (!existing) throw new ApiError(404, "Product not found");

  const product = await prisma.product.update({ where: { id: req.params.id }, data });
  await recordAudit({
    userId: req.user!.id,
    action: "UPDATE",
    entityType: "Product",
    entityId: product.id,
    oldValue: existing,
    newValue: product,
  });
  res.json(product);
}

export async function addInventoryTransaction(req: Request, res: Response) {
  const data = inventoryTransactionSchema.parse(req.body);
  const product = await prisma.product.findUnique({ where: { id: req.params.id } });
  if (!product) throw new ApiError(404, "Product not found");

  const delta =
    data.type === "ENTRY" ? Math.abs(data.quantity) : data.type === "EXIT" ? -Math.abs(data.quantity) : data.quantity;

  const newStock = Number(product.currentStock) + delta;
  if (newStock < 0) throw new ApiError(400, "Resulting stock cannot be negative");

  const [transaction] = await prisma.$transaction([
    prisma.inventoryTransaction.create({
      data: {
        productId: product.id,
        type: data.type,
        quantity: data.quantity,
        reason: data.reason,
        createdById: req.user!.id,
      },
    }),
    prisma.product.update({ where: { id: product.id }, data: { currentStock: newStock } }),
  ]);

  await recordAudit({
    userId: req.user!.id,
    action: "INVENTORY_TRANSACTION",
    entityType: "Product",
    entityId: product.id,
    newValue: transaction,
  });

  res.status(201).json(transaction);
}
