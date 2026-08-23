import jwt from "jsonwebtoken";
import { Role } from "@prisma/client";

const JWT_SECRET = process.env.JWT_SECRET || "change-me-in-production";
const JWT_EXPIRES_IN = process.env.JWT_EXPIRES_IN || "8h";

export interface AuthTokenPayload {
  sub: string;
  role: Role;
  branchId: string | null;
  branchIds: string[];
}

export function signToken(payload: AuthTokenPayload): string {
  return jwt.sign(payload, JWT_SECRET, { expiresIn: JWT_EXPIRES_IN } as jwt.SignOptions);
}

export function verifyToken(token: string): AuthTokenPayload {
  const decoded = jwt.verify(token, JWT_SECRET) as AuthTokenPayload & { kind?: string };
  if (decoded.kind) throw new Error("Not a staff token");
  return decoded;
}

// Customer portal tokens are a distinct shape (kind: "customer") so a
// customer's token can never be mistaken for a staff token by either
// verifier, even though both are signed with the same JWT_SECRET.
export interface CustomerTokenPayload {
  sub: string;
  kind: "customer";
}

export function signCustomerToken(customerId: string): string {
  return jwt.sign({ sub: customerId, kind: "customer" }, JWT_SECRET, {
    expiresIn: JWT_EXPIRES_IN,
  } as jwt.SignOptions);
}

export function verifyCustomerToken(token: string): CustomerTokenPayload {
  const decoded = jwt.verify(token, JWT_SECRET) as CustomerTokenPayload & { kind?: string };
  if (decoded.kind !== "customer") throw new Error("Not a customer token");
  return decoded as CustomerTokenPayload;
}
