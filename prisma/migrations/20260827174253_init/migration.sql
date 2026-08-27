-- CreateSchema
CREATE SCHEMA IF NOT EXISTS "public";

-- CreateEnum
CREATE TYPE "AppMode" AS ENUM ('PRE_MBA', 'POST_MBA');

-- CreateEnum
CREATE TYPE "EmploymentType" AS ENUM ('FULL_TIME', 'PART_TIME', 'INTERNSHIP', 'CONTRACT', 'FREELANCE');

-- CreateEnum
CREATE TYPE "ImpactCategory" AS ENUM ('COST_REDUCTION', 'REVENUE', 'PRODUCTIVITY', 'TIME_SAVED', 'QUALITY', 'SERVICE_LEVEL', 'INVENTORY', 'FORECAST_ACCURACY', 'CUSTOMER_SATISFACTION', 'RISK_REDUCTION', 'AUTOMATION', 'DIGITAL_TRANSFORMATION');

-- CreateEnum
CREATE TYPE "EvidenceType" AS ENUM ('PDF', 'IMAGE', 'EXCEL', 'POWERPOINT', 'WORD', 'CERTIFICATE', 'EMAIL_SCREENSHOT', 'KPI_REPORT', 'MANAGER_FEEDBACK', 'PERFORMANCE_REVIEW', 'OTHER');

-- CreateEnum
CREATE TYPE "SkillCategory" AS ENUM ('TECHNICAL', 'BUSINESS', 'LEADERSHIP', 'DATA', 'SUPPLY_CHAIN', 'PROJECT_MANAGEMENT', 'COMMUNICATION', 'LANGUAGE');

-- CreateEnum
CREATE TYPE "SkillLevel" AS ENUM ('BEGINNER', 'INTERMEDIATE', 'ADVANCED', 'EXPERT');

-- CreateEnum
CREATE TYPE "CertificationStatus" AS ENUM ('NOT_STARTED', 'PLANNING', 'IN_PROGRESS', 'EXAM_SCHEDULED', 'PASSED', 'FAILED', 'EXPIRED');

-- CreateEnum
CREATE TYPE "LeadershipType" AS ENUM ('PROJECT_LEADERSHIP', 'TEAM_LEADERSHIP', 'MENTORING', 'TEACHING', 'COMMUNITY', 'ENTREPRENEURSHIP');

-- CreateEnum
CREATE TYPE "StoryTag" AS ENUM ('LEADERSHIP', 'FAILURE', 'CONFLICT', 'INNOVATION', 'TEAMWORK', 'ETHICS', 'INTERNATIONAL', 'PROBLEM_SOLVING', 'ACHIEVEMENT', 'RESILIENCE', 'DIVERSITY', 'CAREER_TRANSITION', 'COMMUNITY', 'ENTREPRENEURSHIP');

-- CreateEnum
CREATE TYPE "InternationalExposureType" AS ENUM ('WORKED_IN_COUNTRY', 'MANAGED_STAKEHOLDERS', 'MANAGED_SUPPLY', 'INTERNATIONAL_PROJECT', 'INTERNATIONAL_CLIENT', 'MULTICULTURAL_TEAM', 'BUSINESS_TRAVEL');

-- CreateEnum
CREATE TYPE "ProgramType" AS ENUM ('FULL_TIME', 'EXECUTIVE', 'PART_TIME', 'ONLINE');

-- CreateEnum
CREATE TYPE "ScholarshipStatus" AS ENUM ('RESEARCHING', 'PLANNED', 'APPLYING', 'SUBMITTED', 'AWARDED', 'REJECTED');

-- CreateEnum
CREATE TYPE "ApplicationStatus" AS ENUM ('RESEARCHING', 'PREPARING', 'READY', 'SUBMITTED', 'INTERVIEW', 'ADMITTED', 'WAITLISTED', 'REJECTED');

-- CreateEnum
CREATE TYPE "Priority" AS ENUM ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW');

-- CreateEnum
CREATE TYPE "MilestoneStatus" AS ENUM ('PLANNED', 'IN_PROGRESS', 'DONE', 'AT_RISK');

-- CreateEnum
CREATE TYPE "TaskStatus" AS ENUM ('TODO', 'IN_PROGRESS', 'BLOCKED', 'DONE');

-- CreateTable
CREATE TABLE "users" (
    "id" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "passwordHash" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "users_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "profiles" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "fullName" TEXT NOT NULL,
    "currentLocation" TEXT,
    "dateOfBirth" TIMESTAMP(3),
    "currentJobTitle" TEXT,
    "currentCompany" TEXT,
    "yearsOfExperience" DECIMAL(4,1),
    "languages" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "careerGoalShortTerm" TEXT,
    "careerGoalLongTerm" TEXT,
    "mbaRationale" TEXT,
    "mbaTargetYear" INTEGER,
    "professionalInterests" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "currency" TEXT NOT NULL DEFAULT 'EUR',
    "timezone" TEXT NOT NULL DEFAULT 'Europe/Paris',
    "appMode" "AppMode" NOT NULL DEFAULT 'PRE_MBA',
    "avatarUrl" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "profiles_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "career_experiences" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "company" TEXT NOT NULL,
    "role" TEXT NOT NULL,
    "department" TEXT,
    "location" TEXT,
    "startDate" TIMESTAMP(3) NOT NULL,
    "endDate" TIMESTAMP(3),
    "isCurrent" BOOLEAN NOT NULL DEFAULT false,
    "employmentType" "EmploymentType" NOT NULL DEFAULT 'FULL_TIME',
    "responsibilities" TEXT,
    "teamSize" INTEGER,
    "manager" TEXT,
    "countriesCovered" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "skillsUsed" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "career_experiences_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "career_achievements" (
    "id" TEXT NOT NULL,
    "careerExperienceId" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "description" TEXT,
    "date" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "career_achievements_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "projects" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "careerExperienceId" TEXT,
    "name" TEXT NOT NULL,
    "company" TEXT,
    "date" TIMESTAMP(3),
    "problem" TEXT,
    "context" TEXT,
    "objective" TEXT,
    "actions" TEXT,
    "role" TEXT,
    "stakeholders" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "skillsUsed" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "tools" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "countries" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "result" TEXT,
    "mbaRelevance" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "projects_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "project_impacts" (
    "id" TEXT NOT NULL,
    "projectId" TEXT NOT NULL,
    "category" "ImpactCategory" NOT NULL,
    "metricName" TEXT NOT NULL,
    "beforeValue" DECIMAL(14,2),
    "afterValue" DECIMAL(14,2),
    "unit" TEXT,
    "annualizedValue" DECIMAL(14,2),
    "narrative" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "project_impacts_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "evidence" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "type" "EvidenceType" NOT NULL,
    "date" TIMESTAMP(3),
    "description" TEXT,
    "tags" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "fileUrl" TEXT,
    "projectId" TEXT,
    "achievementId" TEXT,
    "certificationId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "evidence_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "skills" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "category" "SkillCategory" NOT NULL,
    "currentLevel" "SkillLevel" NOT NULL DEFAULT 'BEGINNER',
    "targetLevel" "SkillLevel" NOT NULL DEFAULT 'ADVANCED',
    "notes" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "skills_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "skill_assessments" (
    "id" TEXT NOT NULL,
    "skillId" TEXT NOT NULL,
    "level" "SkillLevel" NOT NULL,
    "assessedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "source" TEXT,
    "notes" TEXT,

    CONSTRAINT "skill_assessments_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "certifications" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "provider" TEXT NOT NULL,
    "category" TEXT,
    "status" "CertificationStatus" NOT NULL DEFAULT 'NOT_STARTED',
    "startDate" TIMESTAMP(3),
    "examDate" TIMESTAMP(3),
    "completionDate" TIMESTAMP(3),
    "score" TEXT,
    "cost" DECIMAL(10,2),
    "currency" TEXT NOT NULL DEFAULT 'EUR',
    "expirationDate" TIMESTAMP(3),
    "certificateUrl" TEXT,
    "notes" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "certifications_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "courses" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "provider" TEXT,
    "type" TEXT,
    "completedAt" TIMESTAMP(3),
    "hours" DECIMAL(6,1),
    "notes" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "courses_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "education" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "degree" TEXT NOT NULL,
    "university" TEXT NOT NULL,
    "field" TEXT,
    "country" TEXT,
    "startDate" TIMESTAMP(3),
    "endDate" TIMESTAMP(3),
    "gradeGpa" TEXT,
    "honors" TEXT,
    "relevantCoursework" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "documentUrl" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "education_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "leadership_experiences" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "type" "LeadershipType" NOT NULL,
    "title" TEXT NOT NULL,
    "organization" TEXT,
    "role" TEXT,
    "teamSize" INTEGER,
    "startDate" TIMESTAMP(3),
    "endDate" TIMESTAMP(3),
    "isOngoing" BOOLEAN NOT NULL DEFAULT false,
    "responsibilities" TEXT,
    "results" TEXT,
    "skillsUsed" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "leadership_experiences_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "leadership_stories" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "projectId" TEXT,
    "title" TEXT NOT NULL,
    "situation" TEXT,
    "task" TEXT,
    "action" TEXT,
    "result" TEXT,
    "reflection" TEXT,
    "tags" "StoryTag"[] DEFAULT ARRAY[]::"StoryTag"[],
    "mbaRelevanceScore" INTEGER,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "leadership_stories_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "international_experiences" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "country" TEXT NOT NULL,
    "company" TEXT,
    "project" TEXT,
    "role" TEXT,
    "type" "InternationalExposureType" NOT NULL,
    "startDate" TIMESTAMP(3),
    "endDate" TIMESTAMP(3),
    "team" TEXT,
    "responsibilities" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "international_experiences_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "mba_programs" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "schoolName" TEXT NOT NULL,
    "programName" TEXT NOT NULL,
    "country" TEXT,
    "city" TEXT,
    "campus" TEXT,
    "programType" "ProgramType" NOT NULL DEFAULT 'FULL_TIME',
    "durationMonths" INTEGER,
    "tuition" DECIMAL(12,2),
    "estimatedLivingCost" DECIMAL(12,2),
    "currency" TEXT NOT NULL DEFAULT 'EUR',
    "minExperienceYears" DECIMAL(4,1),
    "avgExperienceYears" DECIMAL(4,1),
    "gmatRequirement" TEXT,
    "greRequirement" TEXT,
    "englishRequirement" TEXT,
    "officialWebsite" TEXT,
    "notes" TEXT,
    "isPrimaryTarget" BOOLEAN NOT NULL DEFAULT false,
    "isArchived" BOOLEAN NOT NULL DEFAULT false,
    "targetIntake" TEXT,
    "targetYear" INTEGER,
    "lastVerifiedAt" TIMESTAMP(3),
    "sourceUrl" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "mba_programs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "mba_requirements" (
    "id" TEXT NOT NULL,
    "programId" TEXT NOT NULL,
    "label" TEXT NOT NULL,
    "value" TEXT,
    "notes" TEXT,
    "lastVerifiedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "mba_requirements_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "mba_deadlines" (
    "id" TEXT NOT NULL,
    "programId" TEXT NOT NULL,
    "round" TEXT NOT NULL,
    "deadline" TIMESTAMP(3) NOT NULL,
    "notes" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "mba_deadlines_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "mba_scholarships" (
    "id" TEXT NOT NULL,
    "programId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "amount" DECIMAL(12,2),
    "currency" TEXT NOT NULL DEFAULT 'EUR',
    "eligibility" TEXT,
    "deadline" TIMESTAMP(3),
    "status" "ScholarshipStatus" NOT NULL DEFAULT 'RESEARCHING',
    "requirements" TEXT,
    "website" TEXT,
    "notes" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "mba_scholarships_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "mba_dimension_weights" (
    "id" TEXT NOT NULL,
    "programId" TEXT NOT NULL,
    "dimensionKey" TEXT NOT NULL,
    "weight" DECIMAL(5,2) NOT NULL,

    CONSTRAINT "mba_dimension_weights_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "scoring_dimensions" (
    "key" TEXT NOT NULL,
    "label" TEXT NOT NULL,
    "description" TEXT,
    "defaultWeight" DECIMAL(5,2) NOT NULL,
    "sortOrder" INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT "scoring_dimensions_pkey" PRIMARY KEY ("key")
);

-- CreateTable
CREATE TABLE "mba_assessments" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "programId" TEXT NOT NULL,
    "totalScore" INTEGER NOT NULL,
    "isSimulation" BOOLEAN NOT NULL DEFAULT false,
    "scenarioLabel" TEXT,
    "breakdown" JSONB NOT NULL,
    "computedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "mba_assessments_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "mba_applications" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "programId" TEXT NOT NULL,
    "intake" TEXT,
    "round" TEXT,
    "deadline" TIMESTAMP(3),
    "status" "ApplicationStatus" NOT NULL DEFAULT 'RESEARCHING',
    "cvReady" BOOLEAN NOT NULL DEFAULT false,
    "essaysReady" BOOLEAN NOT NULL DEFAULT false,
    "recommendationsReady" BOOLEAN NOT NULL DEFAULT false,
    "transcriptReady" BOOLEAN NOT NULL DEFAULT false,
    "testScoreReady" BOOLEAN NOT NULL DEFAULT false,
    "englishTestReady" BOOLEAN NOT NULL DEFAULT false,
    "passportReady" BOOLEAN NOT NULL DEFAULT false,
    "notes" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "mba_applications_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "goals" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "description" TEXT,
    "horizon" TEXT,
    "targetDate" TIMESTAMP(3),
    "isAchieved" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "goals_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "roadmaps" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "startYear" INTEGER NOT NULL,
    "endYear" INTEGER NOT NULL,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "roadmaps_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "roadmap_milestones" (
    "id" TEXT NOT NULL,
    "roadmapId" TEXT NOT NULL,
    "year" INTEGER NOT NULL,
    "title" TEXT NOT NULL,
    "objective" TEXT,
    "deadline" TIMESTAMP(3),
    "status" "MilestoneStatus" NOT NULL DEFAULT 'PLANNED',
    "priority" "Priority" NOT NULL DEFAULT 'MEDIUM',
    "kpi" TEXT,
    "dependsOnId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "roadmap_milestones_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "tasks" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "description" TEXT,
    "category" TEXT,
    "priority" "Priority" NOT NULL DEFAULT 'MEDIUM',
    "status" "TaskStatus" NOT NULL DEFAULT 'TODO',
    "deadline" TIMESTAMP(3),
    "milestoneId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "tasks_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "financial_plans" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "targetProgramId" TEXT,
    "targetYear" INTEGER,
    "tuition" DECIMAL(12,2),
    "livingCost" DECIMAL(12,2),
    "travelCost" DECIMAL(12,2),
    "visaCost" DECIMAL(12,2),
    "insuranceCost" DECIMAL(12,2),
    "otherCost" DECIMAL(12,2),
    "currency" TEXT NOT NULL DEFAULT 'EUR',
    "currentSavings" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "monthlyContribution" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "annualContributionGrowthPct" DECIMAL(5,2) NOT NULL DEFAULT 0,
    "expectedAnnualReturnPct" DECIMAL(5,2) NOT NULL DEFAULT 0,
    "scholarshipTarget" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "employerSponsorship" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "studentLoanTarget" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "familySupport" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "financial_plans_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "financial_transactions" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "label" TEXT NOT NULL,
    "amount" DECIMAL(12,2) NOT NULL,
    "currency" TEXT NOT NULL DEFAULT 'EUR',
    "date" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "category" TEXT,
    "notes" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "financial_transactions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ai_recommendations" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "reason" TEXT NOT NULL,
    "recommendedAction" TEXT NOT NULL,
    "expectedImpact" TEXT,
    "deadline" TIMESTAMP(3),
    "priority" "Priority" NOT NULL DEFAULT 'MEDIUM',
    "source" TEXT NOT NULL DEFAULT 'rule_engine',
    "isDismissed" BOOLEAN NOT NULL DEFAULT false,
    "isCompleted" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ai_recommendations_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ai_conversations" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "title" TEXT NOT NULL DEFAULT 'New conversation',
    "messages" JSONB[] DEFAULT ARRAY[]::JSONB[],
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ai_conversations_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "reflections" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "periodLabel" TEXT NOT NULL,
    "content" JSONB NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "reflections_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "documents" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "type" TEXT,
    "fileUrl" TEXT,
    "notes" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "documents_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "notifications" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "message" TEXT NOT NULL,
    "category" TEXT,
    "isRead" BOOLEAN NOT NULL DEFAULT false,
    "dueAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "notifications_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "audit_logs" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "action" TEXT NOT NULL,
    "entity" TEXT NOT NULL,
    "entityId" TEXT,
    "metadata" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "audit_logs_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "users_email_key" ON "users"("email");

-- CreateIndex
CREATE UNIQUE INDEX "profiles_userId_key" ON "profiles"("userId");

-- CreateIndex
CREATE INDEX "career_experiences_userId_idx" ON "career_experiences"("userId");

-- CreateIndex
CREATE INDEX "career_achievements_careerExperienceId_idx" ON "career_achievements"("careerExperienceId");

-- CreateIndex
CREATE INDEX "projects_userId_idx" ON "projects"("userId");

-- CreateIndex
CREATE INDEX "project_impacts_projectId_idx" ON "project_impacts"("projectId");

-- CreateIndex
CREATE INDEX "evidence_userId_idx" ON "evidence"("userId");

-- CreateIndex
CREATE INDEX "skills_userId_idx" ON "skills"("userId");

-- CreateIndex
CREATE INDEX "skill_assessments_skillId_idx" ON "skill_assessments"("skillId");

-- CreateIndex
CREATE INDEX "certifications_userId_idx" ON "certifications"("userId");

-- CreateIndex
CREATE INDEX "courses_userId_idx" ON "courses"("userId");

-- CreateIndex
CREATE INDEX "education_userId_idx" ON "education"("userId");

-- CreateIndex
CREATE INDEX "leadership_experiences_userId_idx" ON "leadership_experiences"("userId");

-- CreateIndex
CREATE INDEX "leadership_stories_userId_idx" ON "leadership_stories"("userId");

-- CreateIndex
CREATE INDEX "international_experiences_userId_idx" ON "international_experiences"("userId");

-- CreateIndex
CREATE INDEX "mba_programs_userId_idx" ON "mba_programs"("userId");

-- CreateIndex
CREATE INDEX "mba_requirements_programId_idx" ON "mba_requirements"("programId");

-- CreateIndex
CREATE INDEX "mba_deadlines_programId_idx" ON "mba_deadlines"("programId");

-- CreateIndex
CREATE INDEX "mba_scholarships_programId_idx" ON "mba_scholarships"("programId");

-- CreateIndex
CREATE UNIQUE INDEX "mba_dimension_weights_programId_dimensionKey_key" ON "mba_dimension_weights"("programId", "dimensionKey");

-- CreateIndex
CREATE INDEX "mba_assessments_userId_programId_idx" ON "mba_assessments"("userId", "programId");

-- CreateIndex
CREATE INDEX "mba_applications_userId_idx" ON "mba_applications"("userId");

-- CreateIndex
CREATE INDEX "goals_userId_idx" ON "goals"("userId");

-- CreateIndex
CREATE INDEX "roadmaps_userId_idx" ON "roadmaps"("userId");

-- CreateIndex
CREATE INDEX "roadmap_milestones_roadmapId_idx" ON "roadmap_milestones"("roadmapId");

-- CreateIndex
CREATE INDEX "tasks_userId_idx" ON "tasks"("userId");

-- CreateIndex
CREATE INDEX "financial_plans_userId_idx" ON "financial_plans"("userId");

-- CreateIndex
CREATE INDEX "financial_transactions_userId_idx" ON "financial_transactions"("userId");

-- CreateIndex
CREATE INDEX "ai_recommendations_userId_idx" ON "ai_recommendations"("userId");

-- CreateIndex
CREATE INDEX "ai_conversations_userId_idx" ON "ai_conversations"("userId");

-- CreateIndex
CREATE INDEX "reflections_userId_idx" ON "reflections"("userId");

-- CreateIndex
CREATE INDEX "documents_userId_idx" ON "documents"("userId");

-- CreateIndex
CREATE INDEX "notifications_userId_idx" ON "notifications"("userId");

-- CreateIndex
CREATE INDEX "audit_logs_userId_idx" ON "audit_logs"("userId");

-- AddForeignKey
ALTER TABLE "profiles" ADD CONSTRAINT "profiles_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "career_experiences" ADD CONSTRAINT "career_experiences_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "career_achievements" ADD CONSTRAINT "career_achievements_careerExperienceId_fkey" FOREIGN KEY ("careerExperienceId") REFERENCES "career_experiences"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "projects" ADD CONSTRAINT "projects_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "projects" ADD CONSTRAINT "projects_careerExperienceId_fkey" FOREIGN KEY ("careerExperienceId") REFERENCES "career_experiences"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "project_impacts" ADD CONSTRAINT "project_impacts_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "projects"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "evidence" ADD CONSTRAINT "evidence_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "evidence" ADD CONSTRAINT "evidence_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "projects"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "evidence" ADD CONSTRAINT "evidence_achievementId_fkey" FOREIGN KEY ("achievementId") REFERENCES "career_achievements"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "evidence" ADD CONSTRAINT "evidence_certificationId_fkey" FOREIGN KEY ("certificationId") REFERENCES "certifications"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "skills" ADD CONSTRAINT "skills_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "skill_assessments" ADD CONSTRAINT "skill_assessments_skillId_fkey" FOREIGN KEY ("skillId") REFERENCES "skills"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "certifications" ADD CONSTRAINT "certifications_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "courses" ADD CONSTRAINT "courses_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "education" ADD CONSTRAINT "education_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "leadership_experiences" ADD CONSTRAINT "leadership_experiences_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "leadership_stories" ADD CONSTRAINT "leadership_stories_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "leadership_stories" ADD CONSTRAINT "leadership_stories_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "projects"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "international_experiences" ADD CONSTRAINT "international_experiences_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "mba_programs" ADD CONSTRAINT "mba_programs_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "mba_requirements" ADD CONSTRAINT "mba_requirements_programId_fkey" FOREIGN KEY ("programId") REFERENCES "mba_programs"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "mba_deadlines" ADD CONSTRAINT "mba_deadlines_programId_fkey" FOREIGN KEY ("programId") REFERENCES "mba_programs"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "mba_scholarships" ADD CONSTRAINT "mba_scholarships_programId_fkey" FOREIGN KEY ("programId") REFERENCES "mba_programs"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "mba_dimension_weights" ADD CONSTRAINT "mba_dimension_weights_programId_fkey" FOREIGN KEY ("programId") REFERENCES "mba_programs"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "mba_assessments" ADD CONSTRAINT "mba_assessments_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "mba_assessments" ADD CONSTRAINT "mba_assessments_programId_fkey" FOREIGN KEY ("programId") REFERENCES "mba_programs"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "mba_applications" ADD CONSTRAINT "mba_applications_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "mba_applications" ADD CONSTRAINT "mba_applications_programId_fkey" FOREIGN KEY ("programId") REFERENCES "mba_programs"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "goals" ADD CONSTRAINT "goals_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "roadmaps" ADD CONSTRAINT "roadmaps_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "roadmap_milestones" ADD CONSTRAINT "roadmap_milestones_roadmapId_fkey" FOREIGN KEY ("roadmapId") REFERENCES "roadmaps"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "roadmap_milestones" ADD CONSTRAINT "roadmap_milestones_dependsOnId_fkey" FOREIGN KEY ("dependsOnId") REFERENCES "roadmap_milestones"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_milestoneId_fkey" FOREIGN KEY ("milestoneId") REFERENCES "roadmap_milestones"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "financial_plans" ADD CONSTRAINT "financial_plans_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "financial_transactions" ADD CONSTRAINT "financial_transactions_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ai_recommendations" ADD CONSTRAINT "ai_recommendations_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ai_conversations" ADD CONSTRAINT "ai_conversations_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "reflections" ADD CONSTRAINT "reflections_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "documents" ADD CONSTRAINT "documents_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "notifications" ADD CONSTRAINT "notifications_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "audit_logs" ADD CONSTRAINT "audit_logs_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

