import { z } from "zod";

export const portalRegisterSchema = z.object({
  fullName: z.string().min(2),
  phone: z.string().min(6),
  email: z.string().email().optional().nullable(),
  address: z.string().optional().nullable(),
  password: z.string().min(6),
});

// "identifier" is a phone number or an email — login, forgot-password and
// reset-password all accept either (see findAccountByIdentifier in
// portalAuthController.ts).
export const portalLoginSchema = z.object({
  identifier: z.string().min(3),
  password: z.string().min(1),
});

export const portalForgotPasswordSchema = z.object({
  identifier: z.string().min(3),
});

export const portalResetPasswordSchema = z.object({
  identifier: z.string().min(3),
  code: z.string().length(6),
  newPassword: z.string().min(6),
});
