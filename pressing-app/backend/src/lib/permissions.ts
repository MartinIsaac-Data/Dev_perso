import { Role } from "@prisma/client";

export const PERMISSIONS = [
  "customers:read",
  "customers:write",
  "services:read",
  "services:write",
  "orders:read",
  "orders:write",
  "orders:status",
  "payments:write",
  "deliveries:read",
  "deliveries:write",
  "cash:read",
  "cash:manage",
  "expenses:read",
  "expenses:write",
  "inventory:read",
  "inventory:write",
  "employees:read",
  "employees:write",
  "reports:read",
  "settings:read",
  "settings:write",
  "audit:read",
  "branches:manage",
  "dashboard:read",
] as const;

export type Permission = (typeof PERMISSIONS)[number];

// A role-to-permission matrix, kept in code for v1 instead of a dynamic
// Permission table (see PLAN.md). Adding a role or a permission means
// editing this file, which is a much smaller surface than a mis-seeded
// database table would be.
const ROLE_PERMISSIONS: Record<Role, Permission[]> = {
  SUPER_ADMIN: [...PERMISSIONS],
  ADMIN: [...PERMISSIONS].filter((p) => p !== "branches:manage"),
  MANAGER: [
    "customers:read",
    "customers:write",
    "services:read",
    "services:write",
    "orders:read",
    "orders:write",
    "orders:status",
    "payments:write",
    "deliveries:read",
    "deliveries:write",
    "cash:read",
    "cash:manage",
    "expenses:read",
    "expenses:write",
    "inventory:read",
    "inventory:write",
    "employees:read",
    "reports:read",
    "settings:read",
    "dashboard:read",
  ],
  CASHIER: [
    "customers:read",
    "customers:write",
    "services:read",
    "orders:read",
    "orders:write",
    "orders:status",
    "payments:write",
    "deliveries:read",
    "cash:read",
    "cash:manage",
    "expenses:read",
    "expenses:write",
    "dashboard:read",
  ],
  OPERATOR: [
    "customers:read",
    "services:read",
    "orders:read",
    "orders:status",
    "deliveries:read",
    "inventory:read",
    "dashboard:read",
  ],
  DELIVERY: ["orders:read", "deliveries:read", "deliveries:write", "dashboard:read"],
};

export function roleHasPermission(role: Role, permission: Permission): boolean {
  return ROLE_PERMISSIONS[role]?.includes(permission) ?? false;
}

export function permissionsForRole(role: Role): Permission[] {
  return ROLE_PERMISSIONS[role] ?? [];
}
