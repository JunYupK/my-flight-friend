import { Clock } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { timeAgo } from "@/utils";

export default function StaleBadge({ observedAt, windowMinutes = 240 }: { observedAt: string; windowMinutes?: number }) {
  const w = windowMinutes % 60 === 0 ? `${windowMinutes / 60}시간` : `${windowMinutes}분`;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex items-center gap-0.5 text-xs text-muted-foreground" aria-label="오래된 가격">
          <Clock className="size-3" />
          {timeAgo(observedAt)}
        </span>
      </TooltipTrigger>
      <TooltipContent>
        {timeAgo(observedAt)} 확인 · 신선도 기준 {w}
      </TooltipContent>
    </Tooltip>
  );
}
