import { Router } from "express";
import { asyncHandler } from "../middleware/asyncHandler";
import { requireAuth, requirePermission } from "../middleware/auth";
import {
  deleteOrderItemPhoto,
  getOrderItemPhotoFile,
  listOrderItemPhotos,
  photoUploadMiddleware,
  uploadOrderItemPhoto,
} from "../controllers/orderItemPhotoController";

export const orderItemPhotoRoutes = Router();
orderItemPhotoRoutes.use(requireAuth);

orderItemPhotoRoutes.get("/:itemId/photos", requirePermission("orders:read"), asyncHandler(listOrderItemPhotos));
orderItemPhotoRoutes.post(
  "/:itemId/photos",
  requirePermission("orders:write"),
  photoUploadMiddleware,
  asyncHandler(uploadOrderItemPhoto)
);
orderItemPhotoRoutes.get(
  "/photos/:photoId/file",
  requirePermission("orders:read"),
  asyncHandler(getOrderItemPhotoFile)
);
orderItemPhotoRoutes.delete(
  "/photos/:photoId",
  requirePermission("orders:write"),
  asyncHandler(deleteOrderItemPhoto)
);
