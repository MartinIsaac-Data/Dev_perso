import { Request, Response } from "express";
import { randomInt } from "crypto";
import bcrypt from "bcryptjs";
import { prisma } from "../lib/prisma";
import { signCustomerToken } from "../lib/jwt";
import {
  portalForgotPasswordSchema,
  portalLoginSchema,
  portalRegisterSchema,
  portalResetPasswordSchema,
} from "../validators/portalAuthValidators";
import { ApiError } from "../middleware/errorHandler";
import { recordAudit } from "../services/auditService";
import { getDefaultBranchId } from "../services/branchService";
import { notify } from "../services/notificationService";

const RESET_CODE_TTL_MS = 15 * 60 * 1000;
const GENERIC_RESET_MESSAGE =
  "Si ce numéro est associé à un compte, un code de réinitialisation vient d'être envoyé par SMS.";

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

export async function forgotPassword(req: Request, res: Response) {
  const { phone } = portalForgotPasswordSchema.parse(req.body);

  const customer = await prisma.customer.findUnique({ where: { phone } });
  // Same generic response whether or not the phone matches an account, so
  // this endpoint can't be used to enumerate registered customers.
  if (customer && customer.passwordHash) {
    const code = randomInt(100000, 1000000).toString();
    const resetCodeHash = await bcrypt.hash(code, 10);
    await prisma.customer.update({
      where: { id: customer.id },
      data: { resetCodeHash, resetCodeExpiresAt: new Date(Date.now() + RESET_CODE_TTL_MS) },
    });
    const message = `Votre code de réinitialisation Pressing Étoile : ${code}. Valable 15 minutes.`;
    await Promise.all([notify("SMS", phone, message), notify("WHATSAPP", phone, message)]);
  }

  res.json({ message: GENERIC_RESET_MESSAGE });
}

export async function resetPassword(req: Request, res: Response) {
  const { phone, code, newPassword } = portalResetPasswordSchema.parse(req.body);

  const customer = await prisma.customer.findUnique({ where: { phone } });
  if (!customer?.resetCodeHash || !customer.resetCodeExpiresAt || customer.resetCodeExpiresAt < new Date()) {
    throw new ApiError(400, "Code invalide ou expiré");
  }
  const valid = await bcrypt.compare(code, customer.resetCodeHash);
  if (!valid) {
    throw new ApiError(400, "Code invalide ou expiré");
  }

  const passwordHash = await bcrypt.hash(newPassword, 10);
  await prisma.customer.update({
    where: { id: customer.id },
    data: { passwordHash, resetCodeHash: null, resetCodeExpiresAt: null },
  });
  await recordAudit({ action: "PORTAL_RESET_PASSWORD", entityType: "Customer", entityId: customer.id });

  res.json({ message: "Mot de passe mis à jour, vous pouvez vous connecter." });
}

export async function me(req: Request, res: Response) {
  const customer = await prisma.customer.findUniqueOrThrow({
    where: { id: req.customerId! },
    select: PUBLIC_SELECT,
  });
  res.json(customer);
}
