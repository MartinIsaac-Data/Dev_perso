import type { Role } from "@/types";

/**
 * Where each role lands right after login (and what "/" redirects to for
 * them). Management roles get the analytics Dashboard; front-line roles
 * get a task-focused Workspace instead — see permissions.ts on the backend
 * for the matching removal of dashboard:read from their permission set.
 */
export function landingRouteForRole(role: Role): string {
  switch (role) {
    case "CASHIER":
      return "/workspace/cashier";
    case "OPERATOR":
      return "/workspace/operator";
    case "DELIVERY":
      return "/workspace/delivery";
    default:
      return "/";
  }
}
