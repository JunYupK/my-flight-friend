import { Link } from "react-router-dom";

const FEATURES = [
  {
    title: "오늘의 최저가",
    desc: "ICN 출발 일본 주요 도시 항공권을 실시간 수집합니다. 여러 데이터 소스에서 편도 항공편을 모아 왕복 조합까지 자동으로 만들어, 지금 바로 예약 가능한 최저가를 보여드립니다.",
    link: "/deals",
    cta: "최저가 보기",
    accent: "blue",
  },
  {
    title: "가격 추이 분석",
    desc: "항공권은 언제 사야 가장 쌀까? 매일 수집한 가격 데이터를 바탕으로 출발일별 최저가와 시간에 따른 가격 변동을 차트로 확인하세요. 예약 타이밍을 잡는 데 도움이 됩니다.",
    link: "/trends",
    cta: "추이 보기",
    accent: "purple",
  },
] as const;

const ACCENT = {
  blue: {
    bg: "bg-blue-50",
    border: "border-blue-200",
    text: "text-blue-700",
    btn: "bg-blue-600 hover:bg-blue-700",
  },
  purple: {
    bg: "bg-purple-50",
    border: "border-purple-200",
    text: "text-purple-700",
    btn: "bg-purple-600 hover:bg-purple-700",
  },
};

export default function Landing() {
  return (
    <div className="space-y-16">
      {/* 히어로 */}
      <section className="text-center pt-12 pb-4">
        <h1 className="text-4xl sm:text-5xl font-extrabold text-gray-900 leading-tight">
          Flight Friend
        </h1>
        <p className="mt-4 text-lg text-gray-500 max-w-xl mx-auto leading-relaxed">
          항공권 최저가를 매일 추적합니다.<br />
          복수 소스에서 수집한 데이터로 최적의 예약 타이밍을 찾아보세요.
        </p>
      </section>

      {/* 기능 카드 */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-4xl mx-auto">
        {FEATURES.map((f) => {
          const c = ACCENT[f.accent];
          return (
            <Link
              key={f.link}
              to={f.link}
              className={`flex flex-col ${c.bg} border ${c.border} rounded-2xl p-8 hover:shadow-lg transition-shadow group`}
            >
              <h2 className={`text-2xl font-bold ${c.text}`}>{f.title}</h2>
              <p className="mt-3 text-sm text-gray-600 leading-relaxed flex-1">{f.desc}</p>
              <span
                className={`inline-block mt-6 px-5 py-2 ${c.btn} text-white text-sm font-medium rounded-lg transition-colors`}
              >
                {f.cta}
              </span>
            </Link>
          );
        })}
      </section>

      {/* 푸터 */}
      <footer className="text-center text-xs text-gray-300 pb-8">
        데이터는 Google Flights, Amadeus, Naver 등에서 수집됩니다.
      </footer>
    </div>
  );
}
