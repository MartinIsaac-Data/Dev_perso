import { Request, Response } from "express";
import { Decimal } from "@prisma/client/runtime/library";
import { prisma } from "../lib/prisma";
import { cashCloseSchema, cashOpenSchema, cashTransactionSchema } from "../validators/cashValidators";
import { ApiError } from "../middleware/errorHandler";
import { recordAudit } from "../services/auditService";
import { branchScope } from "../middleware/auth";
import { computeTheoreticalBalance } from "../services/cashService";

export async function listCashRegisters(req: Request, res: Response) {
  const { status } = req.query as Record<string, string>;
  const registers = await prisma.cashRegister.findMany({
    where: { ...branchScope(req.user!), ...(status ? { status: status as never } : {}) },
    orderBy: { openedAt: "desc" },
    include: { openedBy: { select: { fullName: true } }, closedBy: { select: { fullName: true } } },
  });
  res.json(registers);
}

export async function getCurrentRegister(req: Request, res: Response) {
  const register = await prisma.cashRegister.findFirst({
    where: { status: "OPEN", ...branchScope(req.user!) },
    include: { transactions: { orderBy: { createdAt: "desc" } } },
  });
  if (!register) return res.json(null);

  const totals = summarizeTransactions(register.transactions, Number(register.openingBalance));
  res.json({ ...register, totals });
}

export async function openRegister(req: Request, res: Response) {
  const data = cashOpenSchema.parse(req.body);
  const existing = await prisma.cashRegister.findFirst({
    where: { status: "OPEN", ...branchScope(req.user!) },
  });
  if (existing) throw new ApiError(400, "A cash register is already open for this branch");

  const register = await prisma.cashRegister.create({
    data: {
      branchId: data.branchId ?? req.user!.branchId,
      openedById: req.user!.id,
      openingBalance: data.openingBalance,
    },
  });

  await recordAudit({
    userId: req.user!.id,
    action: "CASH_OPEN",
    entityType: "CashRegister",
    entityId: register.id,
    newValue: register,
  });

  res.status(201).json(register);
}

export async function closeRegister(req: Request, res: Response) {
  const data = cashCloseSchema.parse(req.body);
  const register = await prisma.cashRegister.findUnique({
    where: { id: req.params.id },
    include: { transactions: true },
  });
  if (!register) throw new ApiError(404, "Cash register not found");
  if (register.status === "CLOSED") throw new ApiError(400, "Cash register already closed");

  const theoretical = computeTheoreticalBalance(register.openingBalance, register.transactions);
  const variance = new Decimal(data.closingBalanceActual).sub(theoretical);

  const updated = await prisma.cashRegister.update({
    where: { id: register.id },
    data: {
      status: "CLOSED",
      closedById: req.user!.id,
      closedAt: new Date(),
      closingBalanceTheoretical: theoretical,
      closingBalanceActual: data.closingBalanceActual,
      variance,
    },
  });

  await recordAudit({
    userId: req.user!.id,
    action: "CASH_CLOSE",
    entityType: "CashRegister",
    entityId: register.id,
    oldValue: register,
    newValue: updated,
  });

  res.json(updated);
}

export async function addCashTransaction(req: Request, res: Response) {
  const data = cashTransactionSchema.parse(req.body);
  const register = await prisma.cashRegister.findUnique({ where: { id: req.params.id } });
  if (!register) throw new ApiError(404, "Cash register not found");
  if (register.status === "CLOSED") throw new ApiError(400, "Cash register is closed");

  const transaction = await prisma.cashTransaction.create({
    data: {
      cashRegisterId: register.id,
      type: data.type,
      amount: Math.abs(data.amount),
      method: data.method,
      description: data.description,
      createdById: req.user!.id,
    },
  });

  await recordAudit({
    userId: req.user!.id,
    action: "CASH_TRANSACTION",
    entityType: "CashRegister",
    entityId: register.id,
    newValue: transaction,
  });

  res.status(201).json(transaction);
}

function summarizeTransactions(
  transactions: { type: string; amount: unknown; method: string }[],
  openingBalance: number
) {
  const totalByMethod = (method: string) =>
    transactions
      .filter((t) => t.method === method && ["SALE", "DEPOSIT"].includes(t.type))
      .reduce((sum, t) => sum + Number(t.amount), 0);

  const totalExpenses = transactions
    .filter((t) => ["EXPENSE", "REFUND", "WITHDRAWAL"].includes(t.type))
    .reduce((sum, t) => sum + Number(t.amount), 0);

  return {
    openingBalance,
    totalCash: totalByMethod("CASH"),
    totalOrangeMoney: totalByMethod("ORANGE_MONEY"),
    totalMtnMomo: totalByMethod("MTN_MOMO"),
    totalCard: totalByMethod("CARD"),
    totalExpenses,
    theoreticalBalance:
      openingBalance +
      totalByMethod("CASH") -
      transactions
        .filter((t) => t.method === "CASH" && ["EXPENSE", "REFUND", "WITHDRAWAL"].includes(t.type))
        .reduce((sum, t) => sum + Number(t.amount), 0),
  };
}
