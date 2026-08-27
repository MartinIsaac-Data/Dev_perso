import { PrismaClient, Prisma } from "@prisma/client";
import { PrismaPg } from "@prisma/adapter-pg";
import bcrypt from "bcryptjs";

const adapter = new PrismaPg({ connectionString: process.env.DATABASE_URL });
const prisma = new PrismaClient({ adapter });

const SEED_EMAIL = process.env.SEED_USER_EMAIL ?? "demo@mbacompass.app";
const SEED_PASSWORD = process.env.SEED_USER_PASSWORD ?? "ChangeMe123!";
const SEED_NAME = process.env.SEED_USER_NAME ?? "Alex Martin";

const SCORING_DIMENSIONS = [
  { key: "ACADEMIC_PROFILE", label: "Academic Profile", defaultWeight: 15, sortOrder: 1 },
  { key: "PROFESSIONAL_EXPERIENCE", label: "Professional Experience", defaultWeight: 15, sortOrder: 2 },
  { key: "LEADERSHIP", label: "Leadership", defaultWeight: 15, sortOrder: 3 },
  { key: "BUSINESS_IMPACT", label: "Business Impact", defaultWeight: 15, sortOrder: 4 },
  { key: "INTERNATIONAL_EXPOSURE", label: "International Exposure", defaultWeight: 10, sortOrder: 5 },
  { key: "GMAT_GRE", label: "GMAT / GRE", defaultWeight: 10, sortOrder: 6 },
  { key: "ENGLISH", label: "English", defaultWeight: 5, sortOrder: 7 },
  { key: "CAREER_PROGRESSION", label: "Career Progression", defaultWeight: 5, sortOrder: 8 },
  { key: "EXTRACURRICULAR", label: "Extracurricular / Community", defaultWeight: 5, sortOrder: 9 },
  { key: "GOAL_CLARITY", label: "Career Goal Clarity", defaultWeight: 5, sortOrder: 10 },
];

async function main() {
  console.log(`Seeding as ${SEED_EMAIL} …`);

  const passwordHash = await bcrypt.hash(SEED_PASSWORD, 10);
  const user = await prisma.user.upsert({
    where: { email: SEED_EMAIL },
    update: {},
    create: { email: SEED_EMAIL, passwordHash, name: SEED_NAME },
  });

  for (const dim of SCORING_DIMENSIONS) {
    await prisma.scoringDimension.upsert({
      where: { key: dim.key },
      update: dim,
      create: dim,
    });
  }

  await prisma.profile.upsert({
    where: { userId: user.id },
    update: {},
    create: {
      userId: user.id,
      fullName: SEED_NAME,
      currentLocation: "Paris, France",
      currentJobTitle: "Supply Chain Manager",
      currentCompany: "Nordis Consumer Goods",
      yearsOfExperience: new Prisma.Decimal(6.5),
      languages: ["French", "English", "Spanish"],
      careerGoalShortTerm:
        "Lead a regional digital supply chain transformation program across 3+ markets.",
      careerGoalLongTerm: "Become a Chief Supply Chain / Operations Officer in consumer goods.",
      mbaRationale:
        "An MBA fills the strategy, finance and general-management gaps that a purely operational career path doesn't cover, and gives access to a peer network for a move into general management.",
      mbaTargetYear: 2030,
      professionalInterests: ["Digital transformation", "Supply chain analytics", "Sustainability"],
      currency: "EUR",
      timezone: "Europe/Paris",
      appMode: "PRE_MBA",
    },
  });

  // ---------------------------------------------------------------------
  // Career
  // ---------------------------------------------------------------------
  const nordis = await prisma.careerExperience.create({
    data: {
      userId: user.id,
      company: "Nordis Consumer Goods",
      role: "Supply Chain Manager",
      department: "Operations",
      location: "Paris, France",
      startDate: new Date("2023-03-01"),
      isCurrent: true,
      employmentType: "FULL_TIME",
      responsibilities:
        "Own S&OP process for the Western Europe cluster; lead a team of 4 planners; manage supplier relationships across 6 countries.",
      teamSize: 4,
      manager: "VP Operations",
      countriesCovered: ["France", "Belgium", "Spain", "Italy"],
      skillsUsed: ["S&OP", "Power BI", "Stakeholder management"],
    },
  });

  const veloxa = await prisma.careerExperience.create({
    data: {
      userId: user.id,
      company: "Veloxa Logistics",
      role: "Supply Chain Analyst",
      department: "Planning",
      location: "Lyon, France",
      startDate: new Date("2020-09-01"),
      endDate: new Date("2023-02-28"),
      employmentType: "FULL_TIME",
      responsibilities: "Built demand forecasting models; automated weekly reporting.",
      teamSize: 0,
      countriesCovered: ["France", "Germany"],
      skillsUsed: ["Forecasting", "Excel", "SQL"],
    },
  });

  await prisma.careerExperience.create({
    data: {
      userId: user.id,
      company: "Veloxa Logistics",
      role: "Supply Chain Intern",
      department: "Planning",
      location: "Lyon, France",
      startDate: new Date("2020-02-01"),
      endDate: new Date("2020-08-31"),
      employmentType: "INTERNSHIP",
      responsibilities: "Supported inventory optimization project.",
      countriesCovered: ["France"],
      skillsUsed: ["Excel", "Inventory management"],
    },
  });

  await prisma.careerAchievement.create({
    data: {
      careerExperienceId: nordis.id,
      title: "Cut stockouts by 22% across the Western Europe cluster",
      description: "Redesigned the replenishment policy and safety-stock model.",
      date: new Date("2024-11-01"),
    },
  });

  // ---------------------------------------------------------------------
  // Projects & impact
  // ---------------------------------------------------------------------
  const projectSeeds = [
    {
      name: "Supply Chain Power BI Dashboard",
      company: "Nordis Consumer Goods",
      date: new Date("2024-02-01"),
      problem: "Weekly reporting took 3 hours of manual Excel consolidation across 4 countries.",
      objective: "Automate the weekly S&OP report and cut preparation time.",
      actions: "Built a Power BI model on top of the ERP export; automated refresh; trained the team.",
      role: "Project lead",
      result: "Reporting time dropped from 3 hours to 30 minutes per cycle.",
      tools: ["Power BI", "SQL"],
      countries: ["France", "Belgium", "Spain", "Italy"],
      careerExperienceId: nordis.id,
      impacts: [
        {
          category: "TIME_SAVED" as const,
          metricName: "Weekly reporting time",
          beforeValue: new Prisma.Decimal(3),
          afterValue: new Prisma.Decimal(0.5),
          unit: "hours",
          annualizedValue: new Prisma.Decimal(130),
          narrative: "2.5 hours saved per weekly reporting cycle, ~130 hours/year.",
        },
      ],
    },
    {
      name: "Safety Stock Redesign",
      company: "Nordis Consumer Goods",
      date: new Date("2024-09-01"),
      problem: "Stockout rate of 9% was driving lost sales in the top 3 markets.",
      objective: "Reduce stockouts without increasing average inventory.",
      actions: "Rebuilt the safety-stock formula using service-level targets per SKU tier.",
      role: "Project lead",
      result: "Stockouts down to 7%, inventory flat.",
      tools: ["Excel", "Python"],
      countries: ["France", "Belgium", "Spain"],
      careerExperienceId: nordis.id,
      impacts: [
        {
          category: "SERVICE_LEVEL" as const,
          metricName: "Stockout rate",
          beforeValue: new Prisma.Decimal(9),
          afterValue: new Prisma.Decimal(7),
          unit: "%",
          narrative: "22% relative reduction in stockout rate with flat inventory.",
        },
      ],
    },
    {
      name: "Demand Forecasting Model",
      company: "Veloxa Logistics",
      date: new Date("2022-05-01"),
      problem: "Forecast accuracy was 61%, causing overproduction and expediting costs.",
      objective: "Improve forecast accuracy for the top 50 SKUs.",
      actions: "Built a statistical forecasting model blending trend, seasonality and promotions.",
      role: "Contributor",
      result: "Forecast accuracy improved to 78% on the top 50 SKUs.",
      tools: ["Python", "Excel"],
      countries: ["France", "Germany"],
      careerExperienceId: veloxa.id,
      impacts: [
        {
          category: "FORECAST_ACCURACY" as const,
          metricName: "Forecast accuracy (top 50 SKUs)",
          beforeValue: new Prisma.Decimal(61),
          afterValue: new Prisma.Decimal(78),
          unit: "%",
          narrative: "17-point improvement in forecast accuracy.",
        },
      ],
    },
    {
      name: "Supplier Consolidation Program",
      company: "Nordis Consumer Goods",
      date: new Date("2025-01-01"),
      problem: "Fragmented supplier base across Western Europe was driving avoidable freight cost.",
      objective: "Consolidate secondary packaging suppliers from 12 to 5.",
      actions: "Ran a joint RFP with procurement; renegotiated volumes.",
      role: "Co-lead with Procurement",
      result: "Reduced packaging cost by 6% annually.",
      tools: ["Excel"],
      countries: ["France", "Belgium", "Spain", "Italy"],
      careerExperienceId: nordis.id,
      impacts: [
        {
          category: "COST_REDUCTION" as const,
          metricName: "Packaging cost",
          beforeValue: new Prisma.Decimal(100),
          afterValue: new Prisma.Decimal(94),
          unit: "index",
          narrative: "6% annual reduction in secondary packaging cost.",
        },
      ],
    },
    {
      name: "Warehouse Slotting Optimization",
      company: "Veloxa Logistics",
      date: new Date("2021-06-01"),
      problem: "Pick times in the Lyon warehouse were above network average.",
      objective: "Reduce average pick time through better slotting.",
      actions: "Analyzed pick-frequency data and re-slotted the top 200 SKUs.",
      role: "Contributor",
      result: "Average pick time down 14%.",
      tools: ["Excel", "SQL"],
      countries: ["France"],
      careerExperienceId: veloxa.id,
      impacts: [
        {
          category: "PRODUCTIVITY" as const,
          metricName: "Average pick time",
          beforeValue: new Prisma.Decimal(100),
          afterValue: new Prisma.Decimal(86),
          unit: "index",
          narrative: "14% reduction in average pick time.",
        },
      ],
    },
  ];

  for (const p of projectSeeds) {
    const { impacts, ...projectData } = p;
    await prisma.project.create({
      data: {
        userId: user.id,
        ...projectData,
        mbaRelevance: "Demonstrates measurable, cross-functional business impact.",
        impacts: { create: impacts },
      },
    });
  }

  // ---------------------------------------------------------------------
  // Skills
  // ---------------------------------------------------------------------
  const skillSeeds = [
    { name: "Power BI", category: "DATA", currentLevel: "ADVANCED", targetLevel: "EXPERT" },
    { name: "S&OP", category: "SUPPLY_CHAIN", currentLevel: "ADVANCED", targetLevel: "EXPERT" },
    { name: "SQL", category: "TECHNICAL", currentLevel: "INTERMEDIATE", targetLevel: "ADVANCED" },
    { name: "Financial modeling", category: "BUSINESS", currentLevel: "BEGINNER", targetLevel: "ADVANCED" },
    { name: "Team leadership", category: "LEADERSHIP", currentLevel: "INTERMEDIATE", targetLevel: "ADVANCED" },
    { name: "Public speaking", category: "COMMUNICATION", currentLevel: "INTERMEDIATE", targetLevel: "ADVANCED" },
    { name: "Project management", category: "PROJECT_MANAGEMENT", currentLevel: "ADVANCED", targetLevel: "EXPERT" },
    { name: "English", category: "LANGUAGE", currentLevel: "ADVANCED", targetLevel: "EXPERT" },
  ] as const;

  for (const s of skillSeeds) {
    await prisma.skill.create({ data: { userId: user.id, ...s } });
  }

  // ---------------------------------------------------------------------
  // Certifications
  // ---------------------------------------------------------------------
  await prisma.certification.createMany({
    data: [
      {
        userId: user.id,
        name: "Microsoft PL-300: Power BI Data Analyst",
        provider: "Microsoft",
        category: "Data",
        status: "PASSED",
        completionDate: new Date("2024-05-15"),
        cost: new Prisma.Decimal(120),
        currency: "EUR",
      },
      {
        userId: user.id,
        name: "APICS CPIM Part 1",
        provider: "ASCM",
        category: "Supply Chain",
        status: "IN_PROGRESS",
        startDate: new Date("2025-09-01"),
        cost: new Prisma.Decimal(890),
        currency: "EUR",
      },
      {
        userId: user.id,
        name: "GMAT Focus Edition",
        provider: "GMAC",
        category: "Standardized test",
        status: "PLANNING",
        cost: new Prisma.Decimal(275),
        currency: "USD",
      },
      {
        userId: user.id,
        name: "TOEFL iBT",
        provider: "ETS",
        category: "English",
        status: "PASSED",
        completionDate: new Date("2023-11-10"),
        score: "112/120",
        cost: new Prisma.Decimal(210),
        currency: "USD",
        expirationDate: new Date("2025-11-10"),
      },
      {
        userId: user.id,
        name: "Project Management Professional (PMP)",
        provider: "PMI",
        category: "Project Management",
        status: "NOT_STARTED",
      },
    ],
  });

  // ---------------------------------------------------------------------
  // Leadership
  // ---------------------------------------------------------------------
  await prisma.leadershipExperience.createMany({
    data: [
      {
        userId: user.id,
        type: "TEAM_LEADERSHIP",
        title: "Planning team lead",
        organization: "Nordis Consumer Goods",
        role: "Manager",
        teamSize: 4,
        startDate: new Date("2023-03-01"),
        isOngoing: true,
        responsibilities: "Day-to-day management of 4 planners across 4 markets.",
        results: "Team engagement score up from 68 to 81 in one year.",
      },
      {
        userId: user.id,
        type: "MENTORING",
        title: "Mentor, Supply Chain Graduate Program",
        organization: "Nordis Consumer Goods",
        teamSize: 2,
        startDate: new Date("2024-01-01"),
        isOngoing: true,
        responsibilities: "Mentoring two graduate hires through their first year.",
      },
      {
        userId: user.id,
        type: "COMMUNITY",
        title: "Treasurer, local youth sports association",
        organization: "AS Lyon Jeunes",
        startDate: new Date("2021-01-01"),
        endDate: new Date("2023-01-01"),
        responsibilities: "Managed a €40k annual budget and 3-person volunteer team.",
      },
    ],
  });

  // ---------------------------------------------------------------------
  // International exposure
  // ---------------------------------------------------------------------
  await prisma.internationalExperience.createMany({
    data: [
      { userId: user.id, country: "France", type: "WORKED_IN_COUNTRY", company: "Nordis Consumer Goods" },
      { userId: user.id, country: "Belgium", type: "MANAGED_STAKEHOLDERS", company: "Nordis Consumer Goods" },
      { userId: user.id, country: "Spain", type: "MANAGED_STAKEHOLDERS", company: "Nordis Consumer Goods" },
      { userId: user.id, country: "Italy", type: "INTERNATIONAL_PROJECT", company: "Nordis Consumer Goods" },
      { userId: user.id, country: "Germany", type: "MULTICULTURAL_TEAM", company: "Veloxa Logistics" },
    ],
  });

  // ---------------------------------------------------------------------
  // MBA programs
  // ---------------------------------------------------------------------
  const programSeeds = [
    {
      schoolName: "INSEAD",
      programName: "MBA",
      country: "France / Singapore",
      city: "Fontainebleau",
      programType: "FULL_TIME" as const,
      durationMonths: 12,
      tuition: new Prisma.Decimal(102000),
      estimatedLivingCost: new Prisma.Decimal(30000),
      currency: "EUR",
      minExperienceYears: new Prisma.Decimal(2),
      avgExperienceYears: new Prisma.Decimal(6),
      gmatRequirement: "No fixed minimum; class average ~690",
      englishRequirement: "TOEFL 100+ or equivalent if not exempt",
      officialWebsite: "https://www.insead.edu/master-programmes/mba",
      isPrimaryTarget: true,
      targetIntake: "August 2030",
      targetYear: 2030,
      lastVerifiedAt: new Date("2026-01-15"),
    },
    {
      schoolName: "NEOMA Business School",
      programName: "Global Executive MBA",
      country: "France",
      city: "Paris / Reims",
      programType: "EXECUTIVE" as const,
      durationMonths: 18,
      tuition: new Prisma.Decimal(49000),
      estimatedLivingCost: new Prisma.Decimal(8000),
      currency: "EUR",
      minExperienceYears: new Prisma.Decimal(5),
      avgExperienceYears: new Prisma.Decimal(12),
      gmatRequirement: "Waivable with sufficient experience",
      officialWebsite: "https://neoma-bs.com",
      targetIntake: "September 2029",
      targetYear: 2029,
      lastVerifiedAt: new Date("2026-01-10"),
    },
    {
      schoolName: "HEC Paris",
      programName: "MBA",
      country: "France",
      city: "Jouy-en-Josas",
      programType: "FULL_TIME" as const,
      durationMonths: 16,
      tuition: new Prisma.Decimal(69000),
      estimatedLivingCost: new Prisma.Decimal(24000),
      currency: "EUR",
      minExperienceYears: new Prisma.Decimal(2),
      avgExperienceYears: new Prisma.Decimal(5),
      gmatRequirement: "Class average ~660",
      officialWebsite: "https://www.hec.edu/en/mba-programs/mba",
      targetIntake: "August 2030",
      targetYear: 2030,
      lastVerifiedAt: new Date("2026-01-12"),
    },
  ];

  for (const program of programSeeds) {
    const created = await prisma.mBAProgram.create({
      data: { userId: user.id, ...program },
    });

    await prisma.mBADimensionWeight.createMany({
      data: SCORING_DIMENSIONS.map((d) => ({
        programId: created.id,
        dimensionKey: d.key,
        weight: new Prisma.Decimal(d.defaultWeight),
      })),
    });

    await prisma.mBADeadline.createMany({
      data: [
        { programId: created.id, round: "Round 1", deadline: new Date(`${program.targetYear! - 1}-09-15`) },
        { programId: created.id, round: "Round 2", deadline: new Date(`${program.targetYear! - 1}-11-15`) },
      ],
    });
  }

  // ---------------------------------------------------------------------
  // Tasks
  // ---------------------------------------------------------------------
  await prisma.task.createMany({
    data: [
      { userId: user.id, title: "Start GMAT Focus Edition prep plan", category: "Test prep", priority: "HIGH", status: "TODO" },
      { userId: user.id, title: "Document Safety Stock Redesign impact with evidence", category: "Evidence", priority: "MEDIUM", status: "TODO" },
      { userId: user.id, title: "Book TOEFL retake before expiration", category: "Test prep", priority: "HIGH", status: "TODO", deadline: new Date("2025-10-01") },
      { userId: user.id, title: "Draft short-term / long-term goal statement", category: "MBA application", priority: "MEDIUM", status: "IN_PROGRESS" },
      { userId: user.id, title: "Research NEOMA GEMBA scholarship options", category: "Financing", priority: "LOW", status: "TODO" },
      { userId: user.id, title: "Set up monthly savings automation", category: "Financing", priority: "MEDIUM", status: "TODO" },
      { userId: user.id, title: "Identify a cross-functional project to lead in 2026", category: "Leadership", priority: "HIGH", status: "TODO" },
      { userId: user.id, title: "Finish APICS CPIM Part 1", category: "Certification", priority: "MEDIUM", status: "IN_PROGRESS" },
      { userId: user.id, title: "Request recommendation letter from VP Operations", category: "MBA application", priority: "LOW", status: "TODO" },
      { userId: user.id, title: "Review INSEAD info session recording", category: "Research", priority: "LOW", status: "DONE" },
    ],
  });

  console.log("Seed complete.");
  console.log(`Login with: ${SEED_EMAIL} / ${SEED_PASSWORD}`);
}

main()
  .catch((err) => {
    console.error(err);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
