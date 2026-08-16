import { Request, Response } from "express";
import { prisma } from "../lib/prisma";
import { expenseCreateSchema } from "../validators/expenseValidators";
import { recordAudit } from "../services/auditService";
import { branchScope } from "../middleware/auth";

export async function listExpenses(req: Request, res: Response) {
  const { from, to, category } = req.query as Record<string, string>;
  const expenses = await prisma.expense.findMany({
    where: {
      ...branchScope(req.user!),
      ...(category ? { category: category as never } : {}),
      ...(from || to
        ? { date: { ...(from ? { gte: new Date(from) } : {}), ...(to ? { lte: new Date(to) } : {}) } }
        : {}),
    },
    orderBy: { date: "desc" },
    include: { employee: { select: { fullName: true } } },
  });
  res.json(expenses);
}

export async function createExpense(req: Request, res: Response) {
  const data = expenseCreateSchema.parse(req.body);

  const expense = await prisma.$transaction(async (tx) => {
    const created = await tx.expense.create({
      data: { ...data, branchId: data.branchId ?? req.user!.branchId, employeeId: req.user!.id },
    });

    const openRegister = await tx.cashRegister.findFirst({
      where: { status: "OPEN", ...branchScope(req.user!) },
    });
    if (openRegister) {
      await tx.cashTransaction.create({
        data: {
          cashRegisterId: openRegister.id,
          type: "EXPENSE",
          amount: data.amount,
          method: data.paymentMethod,
          description: data.description ?? `Dépense ${data.category}`,
          expenseId: created.id,
          createdById: req.user!.id,
        },
      });
    }

    return created;
  });

  await recordAudit({
    userId: req.user!.id,
    action: "CREATE",
    entityType: "Expense",
    entityId: expense.id,
    newValue: expense,
  });

  res.status(201).json(expense);
}
