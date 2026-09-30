import { Check } from "lucide-react";
import type { ProviderPriceView } from "@/types";
import { cn } from "@/lib/utils";
import Money from "./Money";
import ProviderBadge from "./ProviderBadge";
import StaleBadge from "./StaleBadge";

export default function ProviderPriceRow({
  prices,
  bestProvider,
}: {
  prices: ProviderPriceView[];
  bestProvider: string | null;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
      {prices.map((p, i) => (
        <span key={p.provider} className="inline-flex items-center gap-1.5">
          {i > 0 && <span className="text-muted-foreground">·</span>}
          <span className={cn("inline-flex items-center gap-1.5", p.stale && "opacity-50")}>
            <ProviderBadge provider={p.provider} />
            {p.price != null ? <Money value={p.price} /> : <span className="text-muted-foreground">-</span>}
            {p.provider === bestProvider && <Check className="size-3.5 text-primary" aria-label="최저가" />}
          </span>
          {p.stale && <StaleBadge observedAt={p.observed_at} />}
        </span>
      ))}
    </div>
  );
}
