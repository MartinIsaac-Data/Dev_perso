-- CreateEnum
CREATE TYPE "OrderSource" AS ENUM ('PHYSICAL', 'ONLINE');

-- AlterTable
ALTER TABLE "orders" ADD COLUMN     "source" "OrderSource" NOT NULL DEFAULT 'PHYSICAL';

-- CreateTable
CREATE TABLE "order_item_photos" (
    "id" TEXT NOT NULL,
    "orderItemId" TEXT NOT NULL,
    "filename" TEXT NOT NULL,
    "mimeType" TEXT NOT NULL,
    "sizeBytes" INTEGER NOT NULL,
    "uploadedById" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "order_item_photos_pkey" PRIMARY KEY ("id")
);

-- AddForeignKey
ALTER TABLE "order_item_photos" ADD CONSTRAINT "order_item_photos_orderItemId_fkey" FOREIGN KEY ("orderItemId") REFERENCES "order_items"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "order_item_photos" ADD CONSTRAINT "order_item_photos_uploadedById_fkey" FOREIGN KEY ("uploadedById") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;

