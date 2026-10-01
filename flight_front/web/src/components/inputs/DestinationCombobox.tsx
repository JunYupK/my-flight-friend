import { useState } from "react";
import { Check, ChevronsUpDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cityName, findAirport, searchAirports } from "@/data/airports";
import { cn } from "@/lib/utils";

const IATA = /^[A-Za-z]{3}$/;

export default function DestinationCombobox({
  value,
  onChange,
}: {
  value: string;
  onChange: (code: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const raw = query.trim();
  const custom = IATA.test(raw) ? raw.toUpperCase() : null;
  const showCustom = custom !== null && findAirport(custom) === null;
  const results = searchAirports(raw);

  const pick = (code: string) => {
    onChange(code);
    setOpen(false);
    setQuery("");
  };

  const label = value ? `${cityName(value) ?? value} (${value})` : null;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between font-normal"
        >
          {label ?? <span className="text-muted-foreground">도시·공항명·코드 검색</span>}
          <ChevronsUpDown className="opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-(--radix-popover-trigger-width) p-0">
        <Command shouldFilter={false}>
          <CommandInput placeholder="나트랑, 후쿠오카, Rome, NRT…" value={query} onValueChange={setQuery} />
          <CommandList>
            {results.length === 0 && !showCustom && <CommandEmpty>일치하는 공항이 없어요</CommandEmpty>}
            <CommandGroup heading={raw ? undefined : "인기 여행지"}>
              {results.map((a) => (
                <CommandItem
                  key={a.code}
                  value={a.code}
                  onSelect={() => pick(a.code)}
                >
                  <Check className={cn("size-4", value === a.code ? "opacity-100" : "opacity-0")} />
                  <span className="font-medium">{a.city}</span>
                  <span className="truncate text-muted-foreground" title={`${a.name} · ${a.country}`}>
                    {a.name} · {a.country}
                  </span>
                  <span className="ml-auto text-xs tabular-nums text-muted-foreground">{a.code}</span>
                </CommandItem>
              ))}
              {showCustom && (
                <CommandItem value={`${custom} 직접 입력 ${raw}`} onSelect={() => pick(custom)}>
                  <span className="font-medium">{custom} 직접 입력</span>
                </CommandItem>
              )}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
