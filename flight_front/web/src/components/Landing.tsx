import { Link } from "react-router-dom";

const FEATURES = [
  {
    title: "오늘의 최저가",
    desc: "ICN 출발 일본 주요 도시 항공권을 실시간 수집합니다. 여러 데이터 소스에서 편도 항공편을 모아 왕복 조합까지 자동으로 만들어, 지금 바로 예약 가능한 최저가를 보여드립니다.",
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

export default function Landing() {
  return (
    <div className="space-y-16 sm:space-y-24">
      {/* 히어로 */}
      <section className="text-center pt-12 sm:pt-20 pb-4">
        <h1 className="text-4xl sm:text-6xl font-bold text-apple-text tracking-tight leading-tight">
          Flight Friend
        </h1>
        <p className="mt-4 sm:mt-6 text-base sm:text-lg text-apple-secondary max-w-md mx-auto leading-relaxed">
          항공권 최저가를 매일 추적합니다.<br />
          최적의 예약 타이밍을 찾아보세요.
        </p>
      </section>

      {/* 기능 카드 */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-5 max-w-3xl mx-auto">
        {FEATURES.map((f) => (
          <Link
            key={f.link}
            to={f.link}
            className="group flex flex-col bg-white rounded-3xl p-7 sm:p-8 shadow-apple hover:shadow-apple-hover hover:-translate-y-0.5 transition-all duration-300"
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
