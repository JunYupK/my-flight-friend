import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { deleteTrip, patchTrip } from "@/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { cityName } from "@/data/airports";
import type { TripInfo, TripPatchInput, TripView } from "@/types";
import { shortMd } from "@/utils";

function targetText(t: TripInfo): string {
  return t.target_price != null ? String(t.target_price) : "";
}

interface Props {
  view: TripView;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: (view: TripView) => void;
}

export default function TripSettingsSheet({ view, open, onOpenChange, onSaved }: Props) {
  const trip = view.trip;
  const tripId = trip.id;
  const [target, setTarget] = useState(() => targetText(trip));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const seq = useRef(0);
  const navigate = useNavigate();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // 다른 trip으로 이동하면 입력 초기화하고 진행 중 응답을 무효화
  useEffect(() => {
    setTarget(targetText(trip));
    setError("");
    setSaving(false);
    setConfirmOpen(false);
    setDeleting(false);
    return () => {
      seq.current++;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tripId]);

  function save(patch: TripPatchInput) {
    const mine = ++seq.current;
    setSaving(true);
    setError("");
    patchTrip(tripId, patch)
      .then((v) => {
        if (mine !== seq.current || v.trip.id !== tripId) return;
        onSaved(v);
        setTarget(targetText(v.trip));
        toast.success("저장했어요");
      })
      .catch((e: unknown) => {
        if (mine === seq.current) setError(e instanceof Error ? e.message : "저장 실패");
      })
      .finally(() => {
        if (mine === seq.current) setSaving(false);
      });
  }

  function remove() {
    setDeleting(true);
    deleteTrip(tripId)
      .then(() => {
        toast.success("삭제했어요");
        navigate("/");
      })
      .catch((e: unknown) => {
        toast.error(e instanceof Error ? e.message : "삭제 실패");
        setDeleting(false);
      });
  }

  function submitTarget(e: FormEvent) {
    e.preventDefault();
    const text = target.trim();
    const value = text === "" ? null : Number(text);
    if (value !== null && (!Number.isInteger(value) || value <= 0)) {
      setError("목표가는 양의 정수(원)로 입력하세요. 비우면 해제됩니다.");
      return;
    }
    save({ target_price: value });
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-sm">
        <SheetHeader>
          <SheetTitle>설정</SheetTitle>
          <SheetDescription>추적과 목표가를 바꿔요.</SheetDescription>
        </SheetHeader>
        <div className="space-y-6 px-4">
          <div className="flex items-center justify-between gap-3">
            <Label htmlFor="ff-tracking">추적</Label>
            <Switch
              id="ff-tracking"
              checked={trip.tracking}
              disabled={saving || trip.archived}
              onCheckedChange={(v) => save({ tracking: v })}
            />
          </div>
          <form onSubmit={submitTarget} className="space-y-2">
            <Label htmlFor="ff-target">목표가 (원)</Label>
            <div className="flex gap-2">
              <Input
                id="ff-target"
                type="number"
                inputMode="numeric"
                min={1}
                placeholder="없음"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
              />
              <Button type="submit" disabled={saving}>
                {saving ? "저장 중…" : "저장"}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">비우고 저장하면 목표가가 해제돼요.</p>
          </form>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="space-y-2 border-t pt-6">
            <Button
              type="button"
              variant="outline"
              className="w-full border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
              onClick={() => setConfirmOpen(true)}
            >
              Trip 삭제
            </Button>
            <p className="text-xs text-muted-foreground">가격 이력과 알림 기록도 함께 지워져요.</p>
          </div>
        </div>
      </SheetContent>
      <Dialog open={confirmOpen} onOpenChange={(v) => !deleting && setConfirmOpen(v)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>이 여행을 삭제할까요?</DialogTitle>
            <DialogDescription>
              {cityName(trip.destination) ?? trip.destination} {shortMd(trip.out_date)}–{shortMd(trip.ret_date)} ·
              가격 이력과 알림 기록도 함께 지워지고 되돌릴 수 없어요.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline" disabled={deleting}>
                취소
              </Button>
            </DialogClose>
            <Button variant="destructive" disabled={deleting} onClick={remove}>
              {deleting ? "삭제 중…" : "삭제"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Sheet>
  );
}
