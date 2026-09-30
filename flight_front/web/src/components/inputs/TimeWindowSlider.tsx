import { Slider } from "@/components/ui/slider";
import { minutesToHHMM, sliderToWindow, windowToSlider } from "@/utils";

function fmt(m: number): string {
  return m === 1440 ? "24:00" : minutesToHHMM(m);
}

export default function TimeWindowSlider({
  label,
  value,
  onChange,
}: {
  label: string;
  value: [string, string] | null;
  onChange: (v: [string, string] | null) => void;
}) {
  const [a, b] = windowToSlider(value);
  return (
    <div>
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <span className="text-sm font-medium">{label}</span>
        <span className="text-sm tabular-nums text-muted-foreground">
          {value ? `${fmt(a)} – ${fmt(b)}` : "제한 없음"}
        </span>
      </div>
      <Slider
        min={0}
        max={1440}
        step={30}
        minStepsBetweenThumbs={1}
        value={[a, b]}
        onValueChange={(v) => onChange(sliderToWindow([v[0], v[1]]))}
        aria-label={label}
      />
    </div>
  );
}
