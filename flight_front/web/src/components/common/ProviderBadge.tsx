import { providerMeta } from "@/lib/providers";
import { cn } from "@/lib/utils";

export default function ProviderBadge({ provider, size = "sm" }: { provider: string; size?: "sm" | "md" }) {
  const m = providerMeta(provider);
  return (
    <span
      title={m.label}
      aria-label={m.label}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded font-semibold text-white",
        size === "sm" ? "size-4 text-[10px]" : "size-5 text-xs",
      )}
      style={{ backgroundColor: `var(${m.colorVar})` }}
    >
      {m.initial}
    </span>
  );
}
