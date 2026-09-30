import { CreditCard } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import Money from "./Money";

export default function CondPriceTag({ price, label }: { price: number; label: string | null }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex max-w-full items-center gap-1 text-xs text-muted-foreground">
          <CreditCard className="size-3 shrink-0" />
          <Money value={price} />
          {label && <span className="truncate">{label}</span>}
        </span>
      </TooltipTrigger>
      <TooltipContent>{label ? `${label} 적용 시` : "조건 적용 시"}</TooltipContent>
    </Tooltip>
  );
}
