import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorMessage } from "@/lib/api";

interface ItemPhoto {
  id: string;
  mimeType: string;
  sizeBytes: number;
  createdAt: string;
}

/**
 * Photos live behind requireAuth (never a public URL — see
 * orderItemPhotoController.ts), so a plain <img src> can't load them: the
 * browser wouldn't send the Bearer token. Each thumbnail instead fetches
 * its bytes through the authenticated api client and renders them as an
 * object URL, revoked on unmount to avoid leaking memory.
 */
export function ItemPhotos({ itemId, canEdit }: { itemId: string; canEdit: boolean }) {
  const queryClient = useQueryClient();
  const [uploading, setUploading] = useState(false);

  const { data: photos } = useQuery({
    queryKey: ["item-photos", itemId],
    queryFn: async () => (await api.get<ItemPhoto[]>(`/order-items/${itemId}/photos`)).data,
  });

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append("photo", file);
        await api.post(`/order-items/${itemId}/photos`, form);
      }
      queryClient.invalidateQueries({ queryKey: ["item-photos", itemId] });
    } catch (err) {
      toast.error(apiErrorMessage(err, "Échec de l'envoi de la photo"));
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(photoId: string) {
    try {
      await api.delete(`/order-items/photos/${photoId}`);
      queryClient.invalidateQueries({ queryKey: ["item-photos", itemId] });
    } catch (err) {
      toast.error(apiErrorMessage(err));
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {photos?.map((p) => (
        <PhotoThumb key={p.id} photoId={p.id} canDelete={canEdit} onDelete={() => handleDelete(p.id)} />
      ))}
      {canEdit && (
        <label className="flex h-12 w-12 shrink-0 cursor-pointer items-center justify-center rounded-md border border-dashed border-border text-muted-foreground hover:bg-accent">
          {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Camera className="h-4 w-4" />}
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            capture="environment"
            multiple
            className="hidden"
            onChange={(e) => {
              handleFiles(e.target.files);
              e.target.value = "";
            }}
            disabled={uploading}
          />
        </label>
      )}
      {!photos?.length && !canEdit && <span className="text-xs text-muted-foreground">Aucune photo</span>}
    </div>
  );
}

function PhotoThumb({ photoId, canDelete, onDelete }: { photoId: string; canDelete: boolean; onDelete: () => void }) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    api.get(`/order-items/photos/${photoId}/file`, { responseType: "blob" }).then((res) => {
      if (cancelled) return;
      objectUrl = URL.createObjectURL(res.data as Blob);
      setSrc(objectUrl);
    });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [photoId]);

  return (
    <div className="group relative h-12 w-12 shrink-0 overflow-hidden rounded-md border border-border bg-muted">
      {src && <img src={src} alt="Photo de l'article" className="h-full w-full object-cover" />}
      {canDelete && (
        <button
          type="button"
          onClick={onDelete}
          className="absolute inset-0 hidden items-center justify-center bg-black/50 text-white group-hover:flex"
          aria-label="Supprimer la photo"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
