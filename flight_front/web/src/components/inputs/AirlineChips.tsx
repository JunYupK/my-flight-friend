import { useState } from "react";
import { X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";

const IATA2 = /^[A-Z0-9]{2}$/;

export default function AirlineChips({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string[];
  onChange: (v: string[]) => void;
}) {
  const [draft, setDraft] = useState("");

  const add = () => {
    const code = draft.trim().toUpperCase();
    if (IATA2.test(code) && !value.includes(code)) onChange([...value, code]);
    setDraft("");
  };

  return (
    <div>
      <span className="mb-1.5 block text-sm font-medium">{label}</span>
      <div className="flex flex-wrap items-center gap-1.5">
        {value.map((c) => (
          <Badge key={c} variant="secondary" className="gap-1">
            {c}
            <button type="button" aria-label={`${c} 삭제`} onClick={() => onChange(value.filter((x) => x !== c))}>
              <X className="size-3" />
            </button>
          </Badge>
        ))}
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value.toUpperCase().slice(0, 2))}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          onBlur={add}
          placeholder="KE"
          aria-label={`${label} 코드 입력`}
          className="h-8 w-20"
        />
      </div>
    </div>
  );
}
