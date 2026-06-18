import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchResults } from "../api";
import type { DestinationGroup } from "../types";
import { formatDate } from "../utils";
import { SourceBadge, TripTypeBadge, FreshnessBanner } from "./DealCard";

const FEATURES = [
  {
    title: "오늘의 최저가",
    desc: "설정된 모든 여행지 항공권을 실시간 수집합니다. 여러 데이터 소스에서 편도 항공편을 모아 왕복 조합까지 자동으로 만들어, 지금 바로 예약 가능한 최저가를 보여드립니다.",
    link: "/deals",
    cta: "최저가 보기",
  },
  {
    title: "가격 추이 분석",
    desc: "항공권은 언제 사야 가장 쌀까? 매일 수집한 가격 데이터를 바탕으로 출발일별 최저가와 시간에 따른 가격 변동을 차트로 확인하세요.",
    link: "/trends",
    cta: "추이 보기",
  },
] as const;

function BestDealRow({ group }: { group: DestinationGroup }) {
  const deal = group.top_deals[0];
  if (!deal) return null;
  return (
    <Link
      to="/deals"
      className="flex items-center gap-3 px-4 py-3 bg-apple-surface border border-apple-tertiary/50 rounded-2xl shadow-apple-sm hover:shadow-apple hover:-translate-y-0.5 transition-all duration-200"
    >
      <div className="flex flex-col min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-semibold text-apple-text truncate">
            {group.destination_name}
          </span>
          <span className="text-[11px] text-apple-secondary">{group.destination}</span>
          <SourceBadge source={deal.source} />
          <TripTypeBadge tripType={deal.trip_type} />
        </div>
        <span className="text-[11px] text-apple-secondary mt-0.5">
          {formatDate(deal.departure_date)} → {formatDate(deal.return_date)} · {deal.stay_nights}박
        </span>
      </div>
      <div className="flex items-baseline gap-1 shrink-0">
        <span className="text-lg font-bold text-apple-text tracking-tight">
          {Math.round(group.min_price).toLocaleString()}
        </span>
        <span className="text-xs text-apple-secondary">원</span>
      </div>
    </Link>
  );
}

export default function Landing() {
  const [groups, setGroups] = useState<DestinationGroup[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetchResults({})
      .then((res) => setGroups([...res].sort((a, b) => a.min_price - b.min_price)))
      .catch(() => setError(true));
  }, []);

  const hasDeals = groups != null && groups.length > 0;

  return (
    <div className="space-y-12 sm:space-y-16">
      {/* 히어로 */}
      <section className="text-center pt-8 sm:pt-14 pb-2">
        <h1 className="text-4xl sm:text-5xl font-bold text-apple-text tracking-tight leading-tight">
          Flight Friend
        </h1>
        <p className="mt-3 sm:mt-5 text-base sm:text-lg text-apple-secondary max-w-md mx-auto leading-relaxed">
          항공권 최저가를 매일 추적합니다.<br />
          최적의 예약 타이밍을 찾아보세요.
        </p>
      </section>

      {/* 오늘의 베스트 딜 */}
      {hasDeals && (
        <section className="max-w-2xl mx-auto space-y-3">
          <div className="flex items-baseline justify-between px-1">
            <h2 className="text-lg font-bold text-apple-text">오늘의 베스트 딜</h2>
            <Link to="/deals" className="text-sm text-apple-blue font-medium hover:underline">
              전체 보기 →
            </Link>
          </div>
          <FreshnessBanner groups={groups} />
          <div className="space-y-2.5">
            {groups.map((g) => (
              <BestDealRow key={g.destination} group={g} />
            ))}
          </div>
        </section>
      )}

      {groups == null && !error && (
        <p className="text-center text-sm text-apple-secondary">딜 불러오는 중…</p>
      )}

      {/* 기능 카드 — 딜이 없거나 보조 안내로 표시 */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-5 max-w-3xl mx-auto">
        {FEATURES.map((f) => (
          <Link
            key={f.link}
            to={f.link}
            className="group flex flex-col bg-apple-surface border border-apple-tertiary/50 rounded-3xl p-7 sm:p-8 shadow-apple hover:shadow-apple-hover hover:-translate-y-0.5 transition-all duration-300"
          >
            <h2 className="text-xl sm:text-2xl font-bold text-apple-text">{f.title}</h2>
            <p className="mt-3 text-sm text-apple-secondary leading-relaxed flex-1">{f.desc}</p>
            <span className="inline-block mt-6 text-apple-blue text-sm font-medium group-hover:underline">
              {f.cta} →
            </span>
          </Link>
        ))}
      </section>

      {/* 푸터 */}
      <footer className="text-center text-xs text-apple-tertiary pb-8">
        데이터는 Google Flights, Amadeus, Naver 등에서 수집됩니다.
      </footer>
    </div>
  );
}
