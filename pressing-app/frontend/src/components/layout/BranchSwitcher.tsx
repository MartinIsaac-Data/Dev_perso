import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Building2, Check, ChevronDown } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import type { Branch } from "@/types";

/**
 * Visible only for staff assigned to more than one branch (see
 * StaffBranch in the backend). Lets them view "all my agencies" combined
 * or narrow down to one — the X-Active-Branch header does the actual
 * filtering server-side (see api.ts and middleware/auth.ts).
 */
export function BranchSwitcher() {
  const { user, activeBranchId, setActiveBranch } = useAuth();
  const [open, setOpen] = useState(false);

  const { data: branches } = useQuery({
    queryKey: ["my-branches"],
    queryFn: async () => (await api.get<Branch[]>("/branches")).data,
    enabled: (user?.branchIds.length ?? 0) > 1,
  });

  if (!user || user.branchIds.length <= 1) return null;

  const current = branches?.find((b) => b.id === activeBranchId);
  const label = current ? current.name : "Toutes mes agences";

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:bg-accent"
      >
        <Building2 className="h-3.5 w-3.5" />
        <span className="hidden max-w-[10rem] truncate sm:inline">{label}</span>
        <ChevronDown className="h-3.5 w-3.5" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-20" onClick={() => setOpen(false)} />
          <div className="absolute left-0 top-full z-30 mt-1 w-56 rounded-md border border-border bg-card p-1 shadow-lg">
            <button
              onClick={() => {
                setActiveBranch(null);
                setOpen(false);
              }}
              className="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-sm hover:bg-accent"
            >
              Toutes mes agences
              {!activeBranchId && <Check className="h-4 w-4 text-primary" />}
            </button>
            <div className="my-1 border-t border-border" />
            {branches?.map((b) => (
              <button
                key={b.id}
                onClick={() => {
                  setActiveBranch(b.id);
                  setOpen(false);
                }}
                className="flex w-full items-center justify-between gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-accent"
              >
                <span className="truncate">{b.name}</span>
                {activeBranchId === b.id && <Check className="h-4 w-4 shrink-0 text-primary" />}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
