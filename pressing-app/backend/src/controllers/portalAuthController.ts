import { Request, Response } from "express";
import bcrypt from "bcryptjs";
import { prisma } from "../lib/prisma";
import { signCustomerToken } from "../lib/jwt";
import { portalLoginSchema, portalRegisterSchema } from "../validators/portalAuthValidators";
import { ApiError } from "../middleware/errorHandler";
import { recordAudit } from "../services/auditService";
import { getDefaultBranchId } from "../services/branchService";

const PUBLIC_SELECT = {
  id: true,
  fullName: true,
  phone: true,
  email: true,
  address: true,
  type: true,
} as const;

export async function register(req: Request, res: Response) {
  const data = portalRegisterSchema.parse(req.body);
  const passwordHash = await bcrypt.hash(data.password, 10);

  const existing = await prisma.customer.findUnique({ where: { phone: data.phone } });

  // A customer walk-in record for this phone may already exist (created
  // in-store by staff, no login). Registering "claims" it instead of
  // erroring, so the portal shows their real order history immediately.
  if (existing) {
    if (existing.passwordHash) {
      throw new ApiError(409, "Un compte existe déjà pour ce numéro de téléphone");
    }
    const customer = await prisma.customer.update({
      where: { id: existing.id },
      data: {
        passwordHash,
        fullName: data.fullName,
        email: data.email ?? existing.email,
        address: data.address ?? existing.address,
        branchId: existing.branchId ?? (await getDefaultBranchId()),
      },
      select: PUBLIC_SELECT,
    });
    const token = signCustomerToken(customer.id);
    await recordAudit({ action: "PORTAL_CLAIM_ACCOUNT", entityType: "Customer", entityId: customer.id });
    return res.status(201).json({ token, customer });
  }

  const customer = await prisma.customer.create({
    data: {
      fullName: data.fullName,
      phone: data.phone,
      email: data.email,
      address: data.address,
      passwordHash,
      branchId: await getDefaultBranchId(),
    },
    select: PUBLIC_SELECT,
  });
  const token = signCustomerToken(customer.id);
  await recordAudit({ action: "PORTAL_REGISTER", entityType: "Customer", entityId: customer.id });
  res.status(201).json({ token, customer });
}

export async function login(req: Request, res: Response) {
  const { phone, password } = portalLoginSchema.parse(req.body);

  const customer = await prisma.customer.findUnique({ where: { phone } });
  if (!customer || !customer.active || !customer.passwordHash) {
    throw new ApiError(401, "Numéro de téléphone ou mot de passe incorrect");
  }
  const valid = await bcrypt.compare(password, customer.passwordHash);
  if (!valid) {
    throw new ApiError(401, "Numéro de téléphone ou mot de passe incorrect");
  }

  const token = signCustomerToken(customer.id);
  res.json({
    token,
    customer: {
      id: customer.id,
      fullName: customer.fullName,
      phone: customer.phone,
      email: customer.email,
      address: customer.address,
      type: customer.type,
    },
  });
}

export async function me(req: Request, res: Response) {
  const customer = await prisma.customer.findUniqueOrThrow({
    where: { id: req.customerId! },
    select: PUBLIC_SELECT,
  });
  res.json(customer);
}
