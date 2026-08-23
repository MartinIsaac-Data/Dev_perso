import crypto from "crypto";
import fs from "fs/promises";
import path from "path";

/**
 * Local-disk file storage for this MVP. Render's filesystem is ephemeral
 * (wiped on every deploy/restart), so this is genuinely a development/demo
 * storage backend, not a production-durable one — but it's real: files are
 * actually written and read back, not a fake stored URL. To move to
 * production-durable storage, swap `save`/`read`/`remove` below for calls
 * to an S3-compatible bucket (e.g. Cloudflare R2, AWS S3) and keep every
 * call site (orderItemPhotoController.ts) unchanged, since they only deal
 * in the `filename` this module hands back.
 */
const UPLOAD_ROOT = path.resolve(process.env.UPLOAD_DIR || path.join(__dirname, "../../uploads"));
const ORDER_ITEM_PHOTOS_DIR = path.join(UPLOAD_ROOT, "order-items");

async function ensureDir(dir: string) {
  await fs.mkdir(dir, { recursive: true });
}

function extensionFor(mimeType: string): string {
  switch (mimeType) {
    case "image/jpeg":
      return ".jpg";
    case "image/png":
      return ".png";
    case "image/webp":
      return ".webp";
    default:
      return "";
  }
}

/** Saves a photo buffer under a random filename; returns that filename (what gets stored in the DB). */
export async function saveOrderItemPhoto(buffer: Buffer, mimeType: string): Promise<string> {
  await ensureDir(ORDER_ITEM_PHOTOS_DIR);
  const filename = `${crypto.randomUUID()}${extensionFor(mimeType)}`;
  await fs.writeFile(path.join(ORDER_ITEM_PHOTOS_DIR, filename), buffer);
  return filename;
}

export function orderItemPhotoPath(filename: string): string {
  return path.join(ORDER_ITEM_PHOTOS_DIR, filename);
}

export async function removeOrderItemPhoto(filename: string): Promise<void> {
  await fs.unlink(orderItemPhotoPath(filename)).catch(() => undefined);
}
