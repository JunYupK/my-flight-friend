import { Check, Loader2, X } from "lucide-react";
import ProviderBadge from "@/components/common/ProviderBadge";
import { cn } from "@/lib/utils";
import type { RunSnapshotStatus } from "@/types";

const CELLS: { label: string; kind: string; direction: string | null }[] = [
  { label: "가는편", kind: "oneway", direction: "out" },
  { label: "오는편", kind: "oneway", direction: "in" },
  { label: "왕복", kind: "roundtrip", direction: null },
];

export default function RunProgress({
  snapshots,
  providers,
}: {
  snapshots: RunSnapshotStatus[];
  providers: string[];
}) {
  return (
    <div className="flex flex-wrap gap-1.5" role="status" aria-label="확인 진행 상황">
      {providers.flatMap((p) =>
        CELLS.map((c) => {
          const snap = snapshots.find(
            (s) => s.provider === p && s.kind === c.kind && (c.direction === null || s.direction === c.direction),
          );
          const state = snap ? (snap.status === "ok" ? "ok" : "fail") : "pending";
          return (
            <span
              key={`${p}-${c.label}`}
              className={cn(
                "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs",
                state === "pending" && "text-muted-foreground",
              )}
            >
              <ProviderBadge provider={p} />
              {c.label}
              {state === "ok" && <Check className="size-3 text-emerald-600 dark:text-emerald-400" aria-label="완료" />}
              {state === "fail" && <X className="size-3 text-destructive" aria-label="실패" />}
              {state === "pending" && <Loader2 className="size-3 animate-spin" aria-label="확인 중" />}
            </span>
          );
        }),
      )}
    </div>
  );
}
