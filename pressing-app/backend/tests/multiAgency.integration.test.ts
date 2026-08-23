import { afterAll, beforeAll, describe, expect, it } from "vitest";
import request from "supertest";
import { createApp } from "../src/app";
import { prisma } from "../src/lib/prisma";

// Solange Etoundi (manager@pressing.demo) is seeded with StaffBranch
// assignments to both Cameroon demo branches (Douala + Yaoundé) — see
// prisma/seed.ts. This exercises the multi-agency access model end to end:
// JWT branchIds, the X-Active-Branch header, and branch-scoped list queries.
describe("multi-agency access", () => {
  const app = createApp();
  let managerToken: string;
  let managerBranchIds: string[];
  let singleBranchToken: string;
  let singleBranchId: string;

  beforeAll(async () => {
    const managerLogin = await request(app)
      .post("/api/auth/login")
      .send({ email: "manager@pressing.demo", password: "Demo1234!" });
    expect(managerLogin.status).toBe(200);
    managerToken = managerLogin.body.token;
    managerBranchIds = managerLogin.body.user.branchIds;

    const cashierLogin = await request(app)
      .post("/api/auth/login")
      .send({ email: "cashier1@pressing.demo", password: "Demo1234!" });
    expect(cashierLogin.status).toBe(200);
    singleBranchToken = cashierLogin.body.token;
    singleBranchId = cashierLogin.body.user.branchId;
  });

  afterAll(async () => {
    await prisma.$disconnect();
  });

  it("gives the multi-agency manager both branch ids in the token payload", () => {
    expect(managerBranchIds).toHaveLength(2);
  });

  it("lists both assigned branches for the multi-agency manager", async () => {
    const res = await request(app).get("/api/branches").set("Authorization", `Bearer ${managerToken}`);
    expect(res.status).toBe(200);
    expect(res.body.map((b: { id: string }) => b.id).sort()).toEqual([...managerBranchIds].sort());
  });

  it("lists only the assigned branch for a single-branch employee", async () => {
    const res = await request(app).get("/api/branches").set("Authorization", `Bearer ${singleBranchToken}`);
    expect(res.status).toBe(200);
    expect(res.body).toHaveLength(1);
    expect(res.body[0].id).toBe(singleBranchId);
  });

  it("shows orders from every assigned branch when no active branch is selected", async () => {
    const res = await request(app).get("/api/orders?pageSize=100").set("Authorization", `Bearer ${managerToken}`);
    expect(res.status).toBe(200);
    const branchIdsSeen = new Set(res.body.data.map((o: { branchId: string }) => o.branchId));
    for (const id of branchIdsSeen) {
      expect(managerBranchIds).toContain(id);
    }
    const dbCount = await prisma.order.count({ where: { branchId: { in: managerBranchIds } } });
    expect(res.body.data.length <= dbCount).toBe(true);
  });

  it("narrows orders to a single branch via the X-Active-Branch header", async () => {
    const [firstBranchId] = managerBranchIds;
    const res = await request(app)
      .get("/api/orders?pageSize=100")
      .set("Authorization", `Bearer ${managerToken}`)
      .set("X-Active-Branch", firstBranchId);
    expect(res.status).toBe(200);
    for (const order of res.body.data) {
      expect(order.branchId).toBe(firstBranchId);
    }
  });

  it("rejects an X-Active-Branch header for a branch the caller is not assigned to", async () => {
    const res = await request(app)
      .get("/api/orders")
      .set("Authorization", `Bearer ${singleBranchToken}`)
      .set("X-Active-Branch", managerBranchIds.find((id) => id !== singleBranchId)!);
    expect(res.status).toBe(403);
  });
});
