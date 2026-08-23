-- AlterTable
ALTER TABLE "customers" ADD COLUMN     "resetCodeExpiresAt" TIMESTAMP(3),
ADD COLUMN     "resetCodeHash" TEXT;

