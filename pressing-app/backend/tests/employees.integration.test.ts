import { afterAll, beforeAll, describe, expect, it } from "vitest";
import request from "supertest";
import { createApp } from "../src/app";
import { prisma } from "../src/lib/prisma";

// Regression coverage for the atomicity bug reported against createEmployee:
// setStaffBranches and recordAudit used to run as separate calls after the
// User row had already committed, so a failure in either left a real,
// usable employee in the database while the caller received an error (a
// retry then hit "Email already in use" for an account that, from the
// UI's perspective, was never created). Everything now runs inside one
// prisma.$transaction.
describe("employee creation", () => {
  const app = createApp();
  let token: string;
  let douala: string;
  let yaounde: string;
  const createdEmails: string[] = [];

  beforeAll(async () => {
    const login = await request(app)
      .post("/api/auth/login")
      .send({ email: "superadmin@pressing.demo", password: "Demo1234!" });
    expect(login.status).toBe(200);
    token = login.body.token;

    const branches = await prisma.branch.findMany({ orderBy: { createdAt: "asc" }, take: 2 });
    if (branches.length < 2) throw new Error("Need at least 2 branches — run `npm run seed` first");
    douala = branches[0].id;
    yaounde = branches[1].id;
  });

  afterAll(async () => {
    await prisma.user.deleteMany({ where: { email: { in: createdEmails } } });
    await prisma.$disconnect();
  });

  function draft(overrides: Record<string, unknown> = {}) {
    const email = `employee-test-${Date.now()}-${Math.random().toString(36).slice(2)}@pressing.demo`;
    createdEmails.push(email);
    return {
      email,
      password: "Demo1234!",
      fullName: "Employé Test",
      role: "CASHIER",
      branchId: douala,
      ...overrides,
    };
  }

  it("creates an employee with a single branch", async () => {
    const payload = draft();
    const res = await request(app).post("/api/employees").set("Authorization", `Bearer ${token}`).send(payload);
    expect(res.status).toBe(201);
    expect(res.body.branchIds).toEqual([douala]);

    const stored = await prisma.user.findUnique({ where: { email: payload.email } });
    expect(stored).not.toBeNull();
  });

  it("creates an employee assigned to multiple branches", async () => {
    const payload = draft({ role: "MANAGER", branchIds: [douala, yaounde] });
    const res = await request(app).post("/api/employees").set("Authorization", `Bearer ${token}`).send(payload);
    expect(res.status).toBe(201);
    expect(res.body.branchIds.sort()).toEqual([douala, yaounde].sort());

    const assignments = await prisma.staffBranch.findMany({ where: { userId: res.body.id } });
    expect(assignments).toHaveLength(2);
  });

  it("creates an employee with no branch at all", async () => {
    const payload = draft({ branchId: undefined, role: "OPERATOR" });
    const res = await request(app).post("/api/employees").set("Authorization", `Bearer ${token}`).send(payload);
    expect(res.status).toBe(201);
    expect(res.body.branchIds).toEqual([]);
  });

  it("rejects a duplicate email without creating a second row", async () => {
    const payload = draft();
    const first = await request(app).post("/api/employees").set("Authorization", `Bearer ${token}`).send(payload);
    expect(first.status).toBe(201);

    const second = await request(app).post("/api/employees").set("Authorization", `Bearer ${token}`).send(payload);
    expect(second.status).toBe(409);

    const count = await prisma.user.count({ where: { email: payload.email } });
    expect(count).toBe(1);
  });

  it("rejects invalid role/validation input before touching the database", async () => {
    const payload = draft({ role: "NOT_A_REAL_ROLE" });
    const res = await request(app).post("/api/employees").set("Authorization", `Bearer ${token}`).send(payload);
    expect(res.status).toBe(400);

    const stored = await prisma.user.findUnique({ where: { email: payload.email } });
    expect(stored).toBeNull();
  });

  it("rolls back the whole creation — no orphaned user — when branch assignment fails", async () => {
    const payload = draft({ branchIds: ["00000000-0000-0000-0000-000000000000"] });
    const res = await request(app).post("/api/employees").set("Authorization", `Bearer ${token}`).send(payload);
    expect(res.status).toBeGreaterThanOrEqual(400);

    const stored = await prisma.user.findUnique({ where: { email: payload.email } });
    expect(stored).toBeNull();

    // The email is free again — a corrected retry must succeed, not hit
    // "Email already in use" for a user that (from the caller's view) was
    // never created.
    const retry = await request(app)
      .post("/api/employees")
      .set("Authorization", `Bearer ${token}`)
      .send({ ...payload, branchIds: [douala] });
    expect(retry.status).toBe(201);
  });

  it("a CASHIER cannot create employees", async () => {
    const cashierLogin = await request(app)
      .post("/api/auth/login")
      .send({ email: "cashier1@pressing.demo", password: "Demo1234!" });
    const res = await request(app)
      .post("/api/employees")
      .set("Authorization", `Bearer ${cashierLogin.body.token}`)
      .send(draft());
    expect(res.status).toBe(403);
  });
});
