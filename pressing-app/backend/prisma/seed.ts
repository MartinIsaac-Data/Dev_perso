import { PrismaClient, OrderStatus, ArticleCategory, PaymentMethod, Role } from "@prisma/client";
import bcrypt from "bcryptjs";

const prisma = new PrismaClient();

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
  console.log("Seeding database...");

  await prisma.$transaction([
    prisma.auditLog.deleteMany(),
    prisma.notification.deleteMany(),
    prisma.cashTransaction.deleteMany(),
    prisma.cashRegister.deleteMany(),
    prisma.inventoryTransaction.deleteMany(),
    prisma.product.deleteMany(),
    prisma.expense.deleteMany(),
    prisma.delivery.deleteMany(),
    prisma.payment.deleteMany(),
    prisma.orderStatusHistory.deleteMany(),
    prisma.orderItem.deleteMany(),
    prisma.order.deleteMany(),
    prisma.service.deleteMany(),
    prisma.customer.deleteMany(),
    prisma.setting.deleteMany(),
    prisma.user.deleteMany(),
    prisma.branch.deleteMany(),
  ]);

  // --- Branches -------------------------------------------------------
  const branchMain = await prisma.branch.create({
    data: { name: "Pressing Étoile — Plateau", address: "Avenue Chardy, Plateau, Abidjan", phone: "+225 27 20 30 40 50" },
  });
  const branchAnnex = await prisma.branch.create({
    data: { name: "Pressing Étoile — Cocody", address: "Rue des Jardins, Cocody, Abidjan", phone: "+225 27 22 44 66 88" },
  });

  // --- Users ------------------------------------------------------------
  const passwordHash = await bcrypt.hash("Demo1234!", 10);
  type SeedUser = { email: string; fullName: string; role: Role; branchId: string; position: string };
  const userDefs: SeedUser[] = [
    { email: "superadmin@pressing.demo", fullName: "Aïcha Bamba", role: "SUPER_ADMIN", branchId: branchMain.id, position: "Direction générale" },
    { email: "admin@pressing.demo", fullName: "Moussa Diallo", role: "ADMIN", branchId: branchMain.id, position: "Administrateur" },
    { email: "manager@pressing.demo", fullName: "Fatou Traoré", role: "MANAGER", branchId: branchMain.id, position: "Responsable de boutique" },
    { email: "cashier1@pressing.demo", fullName: "Kossi Yao", role: "CASHIER", branchId: branchMain.id, position: "Caissier" },
    { email: "cashier2@pressing.demo", fullName: "Adjoa Kouassi", role: "CASHIER", branchId: branchAnnex.id, position: "Caissière" },
    { email: "operator1@pressing.demo", fullName: "Bakary Koné", role: "OPERATOR", branchId: branchMain.id, position: "Agent de traitement" },
    { email: "operator2@pressing.demo", fullName: "Grace Mensah", role: "OPERATOR", branchId: branchMain.id, position: "Agent de traitement" },
    { email: "operator3@pressing.demo", fullName: "Ibrahim Ouattara", role: "OPERATOR", branchId: branchAnnex.id, position: "Agent de traitement" },
    { email: "delivery1@pressing.demo", fullName: "Serge N'Guessan", role: "DELIVERY", branchId: branchMain.id, position: "Livreur" },
    { email: "delivery2@pressing.demo", fullName: "Chantal Assi", role: "DELIVERY", branchId: branchAnnex.id, position: "Livreuse" },
  ];

  const users = await Promise.all(
    userDefs.map((u) =>
      prisma.user.create({
        data: { ...u, passwordHash, hireDate: daysAgo(randomInt(60, 400)), phone: `+225 07 ${randomInt(10, 99)} ${randomInt(10, 99)} ${randomInt(10, 99)} ${randomInt(10, 99)}` },
      })
    )
  );
  await prisma.branch.update({ where: { id: branchMain.id }, data: { managerId: users[2].id } });

  const cashiers = users.filter((u) => u.role === "CASHIER" || u.role === "MANAGER" || u.role === "ADMIN");
  const deliverers = users.filter((u) => u.role === "DELIVERY");

  // --- Services -----------------------------------------------------
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
  const services = await Promise.all(
    serviceDefs.map((s) => prisma.service.create({ data: { ...s, description: `${s.name} standard` } }))
  );

  // --- Customers ------------------------------------------------------
  const customerTypes = ["INDIVIDUAL", "INDIVIDUAL", "INDIVIDUAL", "COMPANY", "VIP"] as const;
  const customers = await Promise.all(
    Array.from({ length: 50 }).map((_, i) => {
      const fullName = `${randomItem(FIRST_NAMES)} ${randomItem(LAST_NAMES)}`;
      return prisma.customer.create({
        data: {
          fullName,
          phone: `+225 07${String(10000000 + i * 137).slice(0, 8)}`,
          email: Math.random() > 0.4 ? `${fullName.toLowerCase().replace(/[^a-z]/g, ".")}@example.com` : null,
          address: Math.random() > 0.3 ? `Rue ${randomInt(1, 40)}, ${randomItem(["Plateau", "Cocody", "Marcory", "Yopougon", "Treichville"])}` : null,
          type: randomItem(customerTypes),
          branchId: randomItem([branchMain.id, branchAnnex.id]),
          createdAt: daysAgo(randomInt(0, 300)),
        },
      });
    })
  );

  // --- Articles catalog per category ---------------------------------
  const ARTICLES: Record<ArticleCategory, string[]> = {
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
  const categories = Object.keys(ARTICLES) as ArticleCategory[];
  const colors = ["Blanc", "Noir", "Bleu", "Gris", "Beige", "Rouge", "Vert"];
  const paymentMethods: PaymentMethod[] = ["CASH", "MOBILE_MONEY", "CARD", "BANK_TRANSFER"];

  // --- Orders, items, payments, deliveries, status history -----------
  for (let day = 59; day >= 0; day--) {
    const ordersToday = randomInt(1, 3);
    for (let n = 0; n < ordersToday; n++) {
      const depositDate = daysAgo(day);
      const customer = randomItem(customers);
      const employee = randomItem(cashiers);
      const branchId = customer.branchId ?? branchMain.id;
      const priority = Math.random() > 0.75 ? "EXPRESS" : "NORMAL";
      const itemCount = randomInt(1, 4);

      const items = Array.from({ length: itemCount }).map(() => {
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
          serviceId: service.id,
          isExpress,
          unitPrice,
          totalPrice: unitPrice * quantity,
        };
      });

      const subtotal = items.reduce((sum, i) => sum + i.totalPrice, 0);
      const discount = Math.random() > 0.85 ? Math.round(subtotal * 0.1) : 0;
      const isDelivery = Math.random() > 0.7;
      const deliveryFee = isDelivery ? 1000 : 0;
      const total = subtotal + deliveryFee - discount;

      // Older orders are more likely to be fully resolved.
      let status: OrderStatus;
      if (day > 5) {
        status = randomItem<OrderStatus>(["COMPLETED", "COMPLETED", "DELIVERED", "COMPLETED", "CANCELLED"]);
      } else if (day > 1) {
        status = randomItem<OrderStatus>(["READY", "QUALITY_CHECK", "COMPLETED", "OUT_FOR_DELIVERY", "DELIVERED"]);
      } else {
        status = randomItem<OrderStatus>(["RECEIVED", "INSPECTION", "PROCESSING", "READY"]);
      }

      const paidRoll = Math.random();
      const paidAmount = paidRoll > 0.85 ? Math.round(total * randomInt(30, 70) / 100) : paidRoll > 0.15 ? total : 0;
      const balance = Math.max(0, total - paidAmount);
      const paymentStatus = paidAmount <= 0 ? "UNPAID" : balance <= 0 ? "PAID" : "PARTIAL";

      const estimatedReadyDate = new Date(depositDate);
      estimatedReadyDate.setHours(estimatedReadyDate.getHours() + (priority === "EXPRESS" ? 24 : 48));

      const order = await prisma.order.create({
        data: {
          orderNumber: nextOrderNumber(depositDate),
          customerId: customer.id,
          branchId,
          employeeId: employee.id,
          depositDate,
          estimatedReadyDate,
          completedDate: ["COMPLETED", "DELIVERED"].includes(status) ? new Date(depositDate.getTime() + 36 * 3600_000) : null,
          status,
          priority,
          subtotal,
          discount,
          deliveryFee,
          total,
          paidAmount,
          balance,
          paymentStatus,
          items: { create: items },
          statusHistory: {
            create: { status: "RECEIVED", changedById: employee.id, note: "Commande créée", createdAt: depositDate },
          },
        },
      });

      if (status !== "RECEIVED") {
        await prisma.orderStatusHistory.create({
          data: { orderId: order.id, status, changedById: employee.id, createdAt: new Date(depositDate.getTime() + 3600_000) },
        });
      }

      if (paidAmount > 0) {
        await prisma.payment.create({
          data: {
            orderId: order.id,
            customerId: customer.id,
            amount: paidAmount,
            method: randomItem(paymentMethods),
            receivedById: employee.id,
            paidAt: depositDate,
          },
        });
      }

      if (isDelivery) {
        await prisma.delivery.create({
          data: {
            orderId: order.id,
            type: "DELIVERY",
            address: customer.address ?? "Adresse non précisée",
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
          },
        });
      }
    }
  }

  // --- Expenses ---------------------------------------------------------
  const expenseCategories = ["CHEMICALS", "WATER", "ELECTRICITY", "TRANSPORT", "MAINTENANCE", "SALARIES", "RENT", "OTHER"] as const;
  for (let i = 0; i < 40; i++) {
    const date = daysAgo(randomInt(0, 59));
    await prisma.expense.create({
      data: {
        branchId: randomItem([branchMain.id, branchAnnex.id]),
        date,
        amount: randomInt(2000, 80000),
        category: randomItem(expenseCategories),
        description: "Dépense d'exploitation",
        employeeId: randomItem(users).id,
        paymentMethod: randomItem(paymentMethods),
      },
    });
  }

  // --- Inventory ----------------------------------------------------
  const productDefs = [
    { name: "Lessive liquide 5L", category: "DETERGENT", currentStock: 40, minStock: 15, unit: "bidon" },
    { name: "Adoucissant", category: "SOFTENER", currentStock: 25, minStock: 10, unit: "bidon" },
    { name: "Détachant textile", category: "STAIN_REMOVER", currentStock: 8, minStock: 10, unit: "flacon" },
    { name: "Eau de Javel", category: "BLEACH", currentStock: 30, minStock: 12, unit: "bidon" },
    { name: "Housses plastiques", category: "PACKAGING", currentStock: 500, minStock: 100, unit: "unité" },
    { name: "Sacs de livraison", category: "BAGS", currentStock: 6, minStock: 50, unit: "unité" },
    { name: "Cintres", category: "HANGERS", currentStock: 300, minStock: 100, unit: "unité" },
    { name: "Étiquettes", category: "LABELS", currentStock: 20, minStock: 50, unit: "rouleau" },
  ] as const;
  for (const p of productDefs) {
    const product = await prisma.product.create({
      data: { ...p, branchId: branchMain.id, purchasePrice: randomInt(1500, 15000), supplier: "Fournisseur Ivoire Chimie" },
    });
    await prisma.inventoryTransaction.create({
      data: {
        productId: product.id,
        type: "ENTRY",
        quantity: p.currentStock,
        reason: "Stock initial",
        createdById: users[0].id,
      },
    });
  }

  // --- Cash registers (last 5 days closed, today open) ----------------
  for (let day = 5; day >= 1; day--) {
    const opened = daysAgo(day);
    const register = await prisma.cashRegister.create({
      data: { branchId: branchMain.id, openedById: users[3].id, openedAt: opened, openingBalance: 20000, status: "OPEN" },
    });
    const salesCount = randomInt(3, 8);
    let total = 0;
    for (let s = 0; s < salesCount; s++) {
      const amount = randomInt(1000, 15000);
      total += amount;
      await prisma.cashTransaction.create({
        data: {
          cashRegisterId: register.id,
          type: "SALE",
          amount,
          method: "CASH",
          description: "Vente comptoir",
          createdById: users[3].id,
          createdAt: opened,
        },
      });
    }
    const theoretical = 20000 + total;
    await prisma.cashRegister.update({
      where: { id: register.id },
      data: {
        status: "CLOSED",
        closedById: users[3].id,
        closedAt: opened,
        closingBalanceTheoretical: theoretical,
        closingBalanceActual: theoretical - randomInt(-500, 500),
        variance: randomInt(-500, 500),
      },
    });
  }
  await prisma.cashRegister.create({
    data: { branchId: branchMain.id, openedById: users[3].id, openingBalance: 25000, status: "OPEN" },
  });

  // --- Settings -----------------------------------------------------
  await prisma.setting.createMany({
    data: [
      { key: "businessName", value: "Pressing Étoile" },
      { key: "phone", value: "+225 27 20 30 40 50" },
      { key: "email", value: "contact@pressingetoile.demo" },
      { key: "address", value: "Avenue Chardy, Plateau, Abidjan" },
      { key: "currency", value: "FCFA" },
      { key: "taxRate", value: 0 },
      { key: "openingHours", value: "Lun-Sam 8h-19h" },
      { key: "termsAndConditions", value: "Les articles non retirés après 60 jours ne sont plus garantis." },
    ],
  });

  console.log("Seed complete.");
  console.log("Demo accounts (password: Demo1234!):");
  userDefs.forEach((u) => console.log(`  ${u.role.padEnd(12)} ${u.email}`));
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
