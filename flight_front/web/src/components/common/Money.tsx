import { formatWon } from "@/utils";
import { cn } from "@/lib/utils";

export default function Money({ value, className }: { value: number; className?: string }) {
  return <span className={cn("tabular-nums", className)}>{formatWon(value)}</span>;
}
