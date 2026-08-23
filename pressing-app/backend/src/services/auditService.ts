import { Prisma } from "@prisma/client";
import { prisma } from "../lib/prisma";

type Db = Prisma.TransactionClient | typeof prisma;

interface AuditParams {
  userId?: string | null;
  action: string;
  entityType: string;
  entityId?: string | null;
  oldValue?: unknown;
  newValue?: unknown;
  ipAddress?: string | null;
}

/** Pass a transaction client as `db` to make the audit entry atomic with the change it's logging. */
export async function recordAudit(params: AuditParams, db: Db = prisma) {
  await db.auditLog.create({
    data: {
      userId: params.userId ?? null,
      action: params.action,
      entityType: params.entityType,
      entityId: params.entityId ?? null,
      oldValue: params.oldValue === undefined ? undefined : (params.oldValue as object),
      newValue: params.newValue === undefined ? undefined : (params.newValue as object),
      ipAddress: params.ipAddress ?? null,
    },
  });
}
