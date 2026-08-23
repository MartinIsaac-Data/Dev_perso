import { Request, Response } from "express";
import multer from "multer";
import { prisma } from "../lib/prisma";
import { ApiError } from "../middleware/errorHandler";
import { assertBranchAccess } from "../middleware/auth";
import { recordAudit } from "../services/auditService";
import { orderItemPhotoPath, removeOrderItemPhoto, saveOrderItemPhoto } from "../services/storageService";

const ALLOWED_MIME_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const MAX_SIZE_BYTES = 5 * 1024 * 1024; // 5MB — enough for a phone photo, small enough to keep uploads fast at the counter.

export const photoUploadMiddleware = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: MAX_SIZE_BYTES },
  fileFilter: (_req, file, cb) => {
    if (!ALLOWED_MIME_TYPES.has(file.mimetype)) {
      cb(new ApiError(400, "Type de fichier non supporté (JPEG, PNG ou WebP uniquement)"));
      return;
    }
    cb(null, true);
  },
}).single("photo");

async function loadItemWithBranch(itemId: string) {
  const item = await prisma.orderItem.findUnique({
    where: { id: itemId },
    include: { order: { select: { branchId: true } } },
  });
  if (!item) throw new ApiError(404, "Article introuvable");
  return item;
}

export async function uploadOrderItemPhoto(req: Request, res: Response) {
  const item = await loadItemWithBranch(req.params.itemId);
  assertBranchAccess(req.user!, item.order.branchId);

  if (!req.file) throw new ApiError(400, "Aucun fichier reçu");

  const filename = await saveOrderItemPhoto(req.file.buffer, req.file.mimetype);
  const photo = await prisma.orderItemPhoto.create({
    data: {
      orderItemId: item.id,
      filename,
      mimeType: req.file.mimetype,
      sizeBytes: req.file.size,
      uploadedById: req.user!.id,
    },
  });

  await recordAudit({
    userId: req.user!.id,
    action: "CREATE",
    entityType: "OrderItemPhoto",
    entityId: photo.id,
    newValue: { orderItemId: item.id, filename, sizeBytes: req.file.size },
  });

  res.status(201).json(photo);
}

export async function listOrderItemPhotos(req: Request, res: Response) {
  const item = await loadItemWithBranch(req.params.itemId);
  assertBranchAccess(req.user!, item.order.branchId);

  const photos = await prisma.orderItemPhoto.findMany({
    where: { orderItemId: item.id },
    orderBy: { createdAt: "asc" },
  });
  res.json(photos);
}

async function loadPhotoWithBranch(photoId: string) {
  const photo = await prisma.orderItemPhoto.findUnique({
    where: { id: photoId },
    include: { orderItem: { include: { order: { select: { branchId: true } } } } },
  });
  if (!photo) throw new ApiError(404, "Photo introuvable");
  return photo;
}

/** Streams the actual file — never a public URL, always behind requireAuth + branch scope. */
export async function getOrderItemPhotoFile(req: Request, res: Response) {
  const photo = await loadPhotoWithBranch(req.params.photoId);
  assertBranchAccess(req.user!, photo.orderItem.order.branchId);

  res.setHeader("Content-Type", photo.mimeType);
  res.setHeader("Cache-Control", "private, max-age=86400");
  res.sendFile(orderItemPhotoPath(photo.filename), (err) => {
    if (err && !res.headersSent) res.status(404).json({ error: "Fichier introuvable" });
  });
}

export async function deleteOrderItemPhoto(req: Request, res: Response) {
  const photo = await loadPhotoWithBranch(req.params.photoId);
  assertBranchAccess(req.user!, photo.orderItem.order.branchId);

  await prisma.orderItemPhoto.delete({ where: { id: photo.id } });
  await removeOrderItemPhoto(photo.filename);

  await recordAudit({
    userId: req.user!.id,
    action: "DELETE",
    entityType: "OrderItemPhoto",
    entityId: photo.id,
    oldValue: { orderItemId: photo.orderItemId, filename: photo.filename },
  });

  res.status(204).send();
}
