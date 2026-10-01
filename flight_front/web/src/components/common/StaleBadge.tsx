import { useContext } from "react";
import { Clock } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { timeAgo } from "@/utils";
import { StaleWindowContext } from "./StaleWindowContext";

export default function StaleBadge({ observedAt, windowMinutes }: { observedAt: string; windowMinutes?: number }) {
  const ctxWindow = useContext(StaleWindowContext);
  const mins = windowMinutes ?? ctxWindow;
  const w = mins % 60 === 0 ? `${mins / 60}시간` : `${mins}분`;
  const full = `${timeAgo(observedAt)} 확인 · 신선도 기준 ${w}`;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex items-center gap-0.5 text-xs text-muted-foreground" aria-label="오래된 가격" title={full}>
          <Clock className="size-3" />
          {timeAgo(observedAt)}
        </span>
      </TooltipTrigger>
      <TooltipContent>{full}</TooltipContent>
    </Tooltip>
  );
}
