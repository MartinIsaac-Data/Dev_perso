/**
 * Generates the demo seed as raw SQL INSERT statements instead of going
 * through Prisma Client. This sandbox can only reach the internet over
 * HTTPS (via the agent proxy) — raw Postgres wire protocol to Neon is
 * blocked — so `npx prisma db seed` can't run here. The Neon MCP tool
 * (`run_sql_transaction`) executes SQL over Neon's API instead, which does
 * work. This script reuses the exact same random-data logic as seed.ts,
 * but records rows in memory and serializes them to SQL instead of calling
 * prisma.x.create(). Output: prisma/seed-statements.json (array of SQL
 * statement strings, FK-safe order, ready for run_sql_transaction).
 */
import crypto from "node:crypto";
import fs from "node:fs";
import bcrypt from "bcryptjs";

function randomItem<T>(arr: readonly T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}
function randomInt(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}
function daysAgo(n: number): Date {
  const d = new Date();
  d.setDate(d.getDate() - n);
  d.setHours(randomInt(8, 18), randomInt(0, 59), 0, 0);
  return d;
}

let orderCounter = 0;
function nextOrderNumber(date: Date): string {
  orderCounter += 1;
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `PR-${y}${m}${d}-${String(orderCounter).padStart(4, "0")}`;
}

// --- in-memory "tables" instead of a real DB ------------------------------
const tables: Record<string, Record<string, unknown>[]> = {};
function insertRow(table: string, row: Record<string, unknown>) {
  const full = { id: crypto.randomUUID(), ...row };
  (tables[table] ??= []).push(full);
  return full;
}

const FIRST_NAMES = [
  "Awa", "Kossi", "Fatou", "Moussa", "Aminata", "Ibrahim", "Adjoa", "Kwame", "Nadia", "Yao",
  "Salimata", "Kofi", "Aicha", "Bakary", "Grace", "Emmanuel", "Rokia", "Didier", "Chantal", "Serge",
  "Mariam", "Paul", "Estelle", "Jean", "Fanta", "Alassane", "Sonia", "Herve", "Rachelle", "Aristide",
  "Nafissatou", "Olivier", "Prisca", "Boubacar", "Larissa", "Cedric", "Assetou", "Landry", "Odile", "Fabrice",
  "Hawa", "Regis", "Bintou", "Armand", "Clarisse", "Souleymane", "Vanessa", "Thierry", "Mah", "Patrick",
];
const LAST_NAMES = [
  "Diallo", "Traore", "Kone", "Ouattara", "Sanogo", "Coulibaly", "Bamba", "Toure", "Konate", "Diarra",
  "Kouassi", "N'Guessan", "Yao", "Kouame", "Assi", "Adjei", "Mensah", "Owusu", "Boateng", "Agbo",
];

async function main() {
  const now = new Date();

  // --- Branches -----------------------------------------------------
  const branchMain = insertRow("branches", {
    name: "Pressing Étoile — Plateau",
    address: "Avenue Chardy, Plateau, Abidjan",
    phone: "+225 27 20 30 40 50",
    managerId: null,
    status: "ACTIVE",
    createdAt: now,
    updatedAt: now,
  });
  const branchAnnex = insertRow("branches", {
    name: "Pressing Étoile — Cocody",
    address: "Rue des Jardins, Cocody, Abidjan",
    phone: "+225 27 22 44 66 88",
    managerId: null,
    status: "ACTIVE",
    createdAt: now,
    updatedAt: now,
  });

  // --- Users ----------------------------------------------------------
  const passwordHash = await bcrypt.hash("Demo1234!", 10);
  const userDefs = [
    { email: "superadmin@pressing.demo", fullName: "Aïcha Bamba", role: "SUPER_ADMIN", branchId: branchMain.id as string, position: "Direction générale" },
    { email: "admin@pressing.demo", fullName: "Moussa Diallo", role: "ADMIN", branchId: branchMain.id as string, position: "Administrateur" },
    { email: "manager@pressing.demo", fullName: "Fatou Traoré", role: "MANAGER", branchId: branchMain.id as string, position: "Responsable de boutique" },
    { email: "cashier1@pressing.demo", fullName: "Kossi Yao", role: "CASHIER", branchId: branchMain.id as string, position: "Caissier" },
    { email: "cashier2@pressing.demo", fullName: "Adjoa Kouassi", role: "CASHIER", branchId: branchAnnex.id as string, position: "Caissière" },
    { email: "operator1@pressing.demo", fullName: "Bakary Koné", role: "OPERATOR", branchId: branchMain.id as string, position: "Agent de traitement" },
    { email: "operator2@pressing.demo", fullName: "Grace Mensah", role: "OPERATOR", branchId: branchMain.id as string, position: "Agent de traitement" },
    { email: "operator3@pressing.demo", fullName: "Ibrahim Ouattara", role: "OPERATOR", branchId: branchAnnex.id as string, position: "Agent de traitement" },
    { email: "delivery1@pressing.demo", fullName: "Serge N'Guessan", role: "DELIVERY", branchId: branchMain.id as string, position: "Livreur" },
    { email: "delivery2@pressing.demo", fullName: "Chantal Assi", role: "DELIVERY", branchId: branchAnnex.id as string, position: "Livreuse" },
  ];

  const users = userDefs.map((u) =>
    insertRow("users", {
      ...u,
      passwordHash,
      hireDate: daysAgo(randomInt(60, 400)),
      phone: `+225 07 ${randomInt(10, 99)} ${randomInt(10, 99)} ${randomInt(10, 99)} ${randomInt(10, 99)}`,
      active: true,
      createdAt: now,
      updatedAt: now,
    })
  );
  branchMain.managerId = users[2].id;

  const cashiers = users.filter((u) => u.role === "CASHIER" || u.role === "MANAGER" || u.role === "ADMIN");
  const deliverers = users.filter((u) => u.role === "DELIVERY");

  // --- Services -------------------------------------------------------
  const serviceDefs = [
    { name: "Lavage", category: "Lavage", price: 1000, expressPrice: 1500, standardDurationHours: 48, expressDurationHours: 24 },
    { name: "Nettoyage à sec", category: "Nettoyage à sec", price: 2000, expressPrice: 3000, standardDurationHours: 48, expressDurationHours: 24 },
    { name: "Repassage", category: "Repassage", price: 500, expressPrice: 800, standardDurationHours: 24, expressDurationHours: 12 },
    { name: "Lavage + repassage", category: "Lavage", price: 1500, expressPrice: 2200, standardDurationHours: 48, expressDurationHours: 24 },
    { name: "Nettoyage costume", category: "Nettoyage à sec", price: 3500, expressPrice: 5000, standardDurationHours: 72, expressDurationHours: 24 },
    { name: "Nettoyage chaussures", category: "Spécial", price: 2500, expressPrice: 3500, standardDurationHours: 48, expressDurationHours: 24 },
    { name: "Nettoyage tapis", category: "Spécial", price: 6000, expressPrice: null, standardDurationHours: 96, expressDurationHours: null },
    { name: "Nettoyage rideaux", category: "Spécial", price: 4000, expressPrice: 6000, standardDurationHours: 72, expressDurationHours: 48 },
    { name: "Lavage couverture", category: "Lavage", price: 3000, expressPrice: 4500, standardDurationHours: 72, expressDurationHours: 24 },
    { name: "Service express", category: "Express", price: 2000, expressPrice: 2000, standardDurationHours: 12, expressDurationHours: 12 },
  ];
  const services = serviceDefs.map((s) =>
    insertRow("services", {
      ...s,
      description: `${s.name} standard`,
      active: true,
      createdAt: now,
      updatedAt: now,
    })
  );

  // --- Customers --------------------------------------------------------
  const customerTypes = ["INDIVIDUAL", "INDIVIDUAL", "INDIVIDUAL", "COMPANY", "VIP"] as const;
  const customers = Array.from({ length: 16 }).map((_, i) => {
    const fullName = `${randomItem(FIRST_NAMES)} ${randomItem(LAST_NAMES)}`;
    return insertRow("customers", {
      fullName,
      phone: `+225 07${String(10000000 + i * 137).slice(0, 8)}`,
      email: Math.random() > 0.4 ? `${fullName.toLowerCase().replace(/[^a-z]/g, ".")}@example.com` : null,
      address: Math.random() > 0.3 ? `Rue ${randomInt(1, 40)}, ${randomItem(["Plateau", "Cocody", "Marcory", "Yopougon", "Treichville"])}` : null,
      birthDate: null,
      type: randomItem(customerTypes),
      notes: null,
      branchId: randomItem([branchMain.id, branchAnnex.id]) as string,
      active: true,
      createdAt: daysAgo(randomInt(0, 300)),
      updatedAt: now,
    });
  });

  // --- Articles catalog per category -----------------------------------
  const ARTICLES: Record<string, string[]> = {
    SHIRT: ["Chemise manches longues", "Chemise manches courtes"],
    TSHIRT: ["T-shirt col rond", "T-shirt polo"],
    PANTS: ["Pantalon classique", "Pantalon en toile"],
    JEANS: ["Jean slim", "Jean droit"],
    SUIT: ["Costume 2 pièces", "Costume 3 pièces"],
    JACKET: ["Veste blazer", "Veste en cuir"],
    DRESS: ["Robe de soirée", "Robe en wax"],
    SKIRT: ["Jupe droite", "Jupe plissée"],
    COAT: ["Manteau d'hiver", "Trench-coat"],
    BEDSHEET: ["Drap simple", "Drap double"],
    BLANKET: ["Couverture polaire", "Couverture en laine"],
    CURTAIN: ["Rideau salon", "Rideau chambre"],
    SHOES: ["Chaussures en cuir", "Baskets"],
    BAG: ["Sac à main", "Sac à dos"],
    OTHER: ["Article divers"],
  };
  const categories = Object.keys(ARTICLES);
  const colors = ["Blanc", "Noir", "Bleu", "Gris", "Beige", "Rouge", "Vert"];
  const paymentMethods = ["CASH", "MOBILE_MONEY", "CARD", "BANK_TRANSFER"];

  // --- Orders, items, payments, deliveries, status history --------------
  // Note: shorter window than the local dev seed (which uses 60 days / 50
  // customers) — this data has to be transcribed through the assistant's
  // own context as SQL text (no direct DB network access from this
  // sandbox), so it's deliberately smaller while staying realistic.
  for (let day = 11; day >= 0; day--) {
    const ordersToday = randomInt(1, 3);
    for (let n = 0; n < ordersToday; n++) {
      const depositDate = daysAgo(day);
      const customer = randomItem(customers);
      const employee = randomItem(cashiers);
      const branchId = (customer.branchId as string) ?? branchMain.id;
      const priority = Math.random() > 0.75 ? "EXPRESS" : "NORMAL";
      const itemCount = randomInt(1, 4);

      const itemDrafts = Array.from({ length: itemCount }).map(() => {
        const category = randomItem(categories);
        const service = randomItem(services);
        const isExpress = priority === "EXPRESS";
        const unitPrice = isExpress && service.expressPrice ? Number(service.expressPrice) : Number(service.price);
        const quantity = randomInt(1, 3);
        return {
          category,
          articleType: randomItem(ARTICLES[category]),
          quantity,
          color: randomItem(colors),
          brand: Math.random() > 0.5 ? randomItem(["Zara", "Nike", "Local", "Generic"]) : null,
          size: Math.random() > 0.5 ? randomItem(["S", "M", "L", "XL"]) : null,
          conditionAtReceipt: randomItem(["Bon état", "Usé", "Neuf"]),
          existingStains: Math.random() > 0.7 ? "Tache légère" : null,
          existingDamages: Math.random() > 0.9 ? "Bouton manquant" : null,
          specialInstructions: null,
          photoUrl: null,
          serviceId: service.id as string,
          isExpress,
          unitPrice,
          totalPrice: unitPrice * quantity,
        };
      });

      const subtotal = itemDrafts.reduce((sum, i) => sum + i.totalPrice, 0);
      const discount = Math.random() > 0.85 ? Math.round(subtotal * 0.1) : 0;
      const isDelivery = Math.random() > 0.7;
      const deliveryFee = isDelivery ? 1000 : 0;
      const total = subtotal + deliveryFee - discount;

      let status: string;
      if (day > 5) {
        status = randomItem(["COMPLETED", "COMPLETED", "DELIVERED", "COMPLETED", "CANCELLED"]);
      } else if (day > 1) {
        status = randomItem(["READY", "QUALITY_CHECK", "COMPLETED", "OUT_FOR_DELIVERY", "DELIVERED"]);
      } else {
        status = randomItem(["RECEIVED", "INSPECTION", "PROCESSING", "READY"]);
      }

      const paidRoll = Math.random();
      const paidAmount = paidRoll > 0.85 ? Math.round((total * randomInt(30, 70)) / 100) : paidRoll > 0.15 ? total : 0;
      const balance = Math.max(0, total - paidAmount);
      const paymentStatus = paidAmount <= 0 ? "UNPAID" : balance <= 0 ? "PAID" : "PARTIAL";

      const estimatedReadyDate = new Date(depositDate);
      estimatedReadyDate.setHours(estimatedReadyDate.getHours() + (priority === "EXPRESS" ? 24 : 48));
      const completedDate = ["COMPLETED", "DELIVERED"].includes(status)
        ? new Date(depositDate.getTime() + 36 * 3600_000)
        : null;

      const order = insertRow("orders", {
        orderNumber: nextOrderNumber(depositDate),
        customerId: customer.id,
        branchId,
        employeeId: employee.id,
        depositDate,
        estimatedReadyDate,
        completedDate,
        status,
        priority,
        subtotal,
        discount,
        deliveryFee,
        total,
        paidAmount,
        balance,
        paymentStatus,
        notes: null,
        createdAt: depositDate,
        updatedAt: now,
      });

      for (const item of itemDrafts) {
        insertRow("order_items", { ...item, orderId: order.id, createdAt: depositDate });
      }

      insertRow("order_status_history", {
        orderId: order.id,
        status: "RECEIVED",
        note: "Commande créée",
        changedById: employee.id,
        createdAt: depositDate,
      });
      if (status !== "RECEIVED") {
        insertRow("order_status_history", {
          orderId: order.id,
          status,
          note: null,
          changedById: employee.id,
          createdAt: new Date(depositDate.getTime() + 3600_000),
        });
      }

      if (paidAmount > 0) {
        insertRow("payments", {
          orderId: order.id,
          customerId: customer.id,
          amount: paidAmount,
          method: randomItem(paymentMethods),
          reference: null,
          receivedById: employee.id,
          notes: null,
          paidAt: depositDate,
        });
      }

      if (isDelivery) {
        insertRow("deliveries", {
          orderId: order.id,
          type: "DELIVERY",
          address: (customer.address as string) ?? "Adresse non précisée",
          neighborhood: null,
          city: "Abidjan",
          phone: customer.phone,
          delivererId: Math.random() > 0.3 ? randomItem(deliverers).id : null,
          fee: deliveryFee,
          scheduledDate: estimatedReadyDate,
          deliveredDate: status === "DELIVERED" || status === "COMPLETED" ? estimatedReadyDate : null,
          status:
            status === "DELIVERED" || status === "COMPLETED"
              ? "DELIVERED"
              : status === "OUT_FOR_DELIVERY"
                ? "IN_TRANSIT"
                : "PENDING",
          createdAt: depositDate,
          updatedAt: now,
        });
      }
    }
  }

  // --- Expenses -----------------------------------------------------
  const expenseCategories = ["CHEMICALS", "WATER", "ELECTRICITY", "TRANSPORT", "MAINTENANCE", "SALARIES", "RENT", "OTHER"];
  for (let i = 0; i < 10; i++) {
    const date = daysAgo(randomInt(0, 11));
    insertRow("expenses", {
      branchId: randomItem([branchMain.id, branchAnnex.id]),
      date,
      amount: randomInt(2000, 80000),
      category: randomItem(expenseCategories),
      description: "Dépense d'exploitation",
      employeeId: randomItem(users).id,
      paymentMethod: randomItem(paymentMethods),
      receiptUrl: null,
      createdAt: date,
    });
  }

  // --- Inventory ------------------------------------------------------
  const productDefs = [
    { name: "Lessive liquide 5L", category: "DETERGENT", currentStock: 40, minStock: 15, unit: "bidon" },
    { name: "Adoucissant", category: "SOFTENER", currentStock: 25, minStock: 10, unit: "bidon" },
    { name: "Détachant textile", category: "STAIN_REMOVER", currentStock: 8, minStock: 10, unit: "flacon" },
    { name: "Eau de Javel", category: "BLEACH", currentStock: 30, minStock: 12, unit: "bidon" },
    { name: "Housses plastiques", category: "PACKAGING", currentStock: 500, minStock: 100, unit: "unité" },
    { name: "Sacs de livraison", category: "BAGS", currentStock: 6, minStock: 50, unit: "unité" },
    { name: "Cintres", category: "HANGERS", currentStock: 300, minStock: 100, unit: "unité" },
    { name: "Étiquettes", category: "LABELS", currentStock: 20, minStock: 50, unit: "rouleau" },
  ];
  for (const p of productDefs) {
    const product = insertRow("products", {
      ...p,
      purchasePrice: randomInt(1500, 15000),
      supplier: "Fournisseur Ivoire Chimie",
      branchId: branchMain.id,
      createdAt: now,
      updatedAt: now,
    });
    insertRow("inventory_transactions", {
      productId: product.id,
      type: "ENTRY",
      quantity: p.currentStock,
      reason: "Stock initial",
      createdById: users[0].id,
      createdAt: now,
    });
  }

  // --- Cash registers (last 5 days closed, today open) -------------------
  for (let day = 5; day >= 1; day--) {
    const opened = daysAgo(day);
    const register = insertRow("cash_registers", {
      branchId: branchMain.id,
      openedById: users[3].id,
      openedAt: opened,
      closedById: null,
      closedAt: null,
      openingBalance: 20000,
      closingBalanceTheoretical: null,
      closingBalanceActual: null,
      variance: null,
      status: "OPEN",
    });
    const salesCount = randomInt(3, 8);
    let total = 0;
    for (let s = 0; s < salesCount; s++) {
      const amount = randomInt(1000, 15000);
      total += amount;
      insertRow("cash_transactions", {
        cashRegisterId: register.id,
        type: "SALE",
        amount,
        method: "CASH",
        description: "Vente comptoir",
        orderId: null,
        expenseId: null,
        createdById: users[3].id,
        createdAt: opened,
      });
    }
    const theoretical = 20000 + total;
    register.status = "CLOSED";
    register.closedById = users[3].id;
    register.closedAt = opened;
    register.closingBalanceTheoretical = theoretical;
    register.closingBalanceActual = theoretical - randomInt(-500, 500);
    register.variance = randomInt(-500, 500);
  }
  insertRow("cash_registers", {
    branchId: branchMain.id,
    openedById: users[3].id,
    openedAt: now,
    closedById: null,
    closedAt: null,
    openingBalance: 25000,
    closingBalanceTheoretical: null,
    closingBalanceActual: null,
    variance: null,
    status: "OPEN",
  });

  // --- Settings -----------------------------------------------------
  const settingDefs: [string, unknown][] = [
    ["businessName", "Pressing Étoile"],
    ["phone", "+225 27 20 30 40 50"],
    ["email", "contact@pressingetoile.demo"],
    ["address", "Avenue Chardy, Plateau, Abidjan"],
    ["currency", "FCFA"],
    ["taxRate", 0],
    ["openingHours", "Lun-Sam 8h-19h"],
    ["termsAndConditions", "Les articles non retirés après 60 jours ne sont plus garantis."],
  ];
  for (const [key, value] of settingDefs) {
    insertRow("settings", { key, value, updatedAt: now });
  }

  // --- Serialize to SQL -------------------------------------------------
  function sqlVal(v: unknown): string {
    if (v === null || v === undefined) return "NULL";
    if (typeof v === "number") return String(v);
    if (typeof v === "boolean") return v ? "true" : "false";
    if (v instanceof Date) return `'${v.toISOString()}'`;
    return `'${String(v).replace(/'/g, "''")}'`;
  }
  function jsonVal(v: unknown): string {
    return `'${JSON.stringify(v).replace(/'/g, "''")}'::jsonb`;
  }

  const TABLE_ORDER = [
    "branches",
    "users",
    "services",
    "customers",
    "orders",
    "order_items",
    "order_status_history",
    "payments",
    "deliveries",
    "expenses",
    "products",
    "inventory_transactions",
    "cash_registers",
    "cash_transactions",
    "settings",
  ];

  const statements: string[] = [];
  const CHUNK = 40;

  for (const table of TABLE_ORDER) {
    const rows = tables[table] ?? [];
    if (rows.length === 0) continue;
    const columns = Object.keys(rows[0]);
    for (let i = 0; i < rows.length; i += CHUNK) {
      const chunk = rows.slice(i, i + CHUNK);
      const valuesSql = chunk
        .map((row) => {
          const vals = columns.map((col) => (table === "settings" && col === "value" ? jsonVal(row[col]) : sqlVal(row[col])));
          return `(${vals.join(", ")})`;
        })
        .join(",\n");
      const colList = columns.map((c) => `"${c}"`).join(", ");
      statements.push(`INSERT INTO "${table}" (${colList}) VALUES\n${valuesSql};`);
    }
  }

  // Plain SQL text (real newlines, no JSON escaping) — far cheaper to read
  // back into context than a JSON-encoded array of the same content.
  // Statements are separated by a marker line since a few string fields
  // (customer/branch names) contain literal semicolons-adjacent characters
  // but never a standalone "--STMT--" line.
  fs.writeFileSync("prisma/seed-statements.sql", statements.join("\n--STMT--\n"));
  const counts = Object.fromEntries(TABLE_ORDER.map((t) => [t, (tables[t] ?? []).length]));
  console.log("Row counts:", counts);
  console.log("Statement count:", statements.length);
  console.log("Demo accounts (password: Demo1234!):");
  userDefs.forEach((u) => console.log(`  ${u.role.padEnd(12)} ${u.email}`));
}

main();
