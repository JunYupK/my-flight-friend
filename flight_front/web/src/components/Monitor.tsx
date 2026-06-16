import React, { useEffect, useState } from "react";
import { fetchCollectionRuns, fetchRunDetail, fetchCoverage } from "../api";
import type { CollectionRun, CoverageByDestMonth } from "../types";

const STALE_HOURS = 6; // cron 주기(3h)의 2배 — 이보다 오래되면 경고

function coverageColor(legs: number, hoursSinceRun: number): string {
  if (legs === 0) return "bg-apple-red/15 text-apple-red";
  if (hoursSinceRun > STALE_HOURS) return "bg-yellow-100 text-yellow-700";
  return "bg-apple-green/15 text-apple-green";
}

function CoverageHeatmap({ data }: { data: CoverageByDestMonth[] }) {
  if (data.length === 0)
    return <p className="text-sm text-apple-secondary py-4">데이터가 없습니다.</p>;

  const destNames: Record<string, string> = {};
  const pivot: Record<string, Record<string, CoverageByDestMonth>> = {};
  for (const pt of data) {
    destNames[pt.destination] = pt.destination_name;
    if (!pivot[pt.destination]) pivot[pt.destination] = {};
    pivot[pt.destination][pt.month] = pt;
  }

  const months = [...new Set(data.map((d) => d.month))].sort();
  const destinations = Object.keys(pivot).sort();
  const now = Date.now();

  return (
    <div className="overflow-x-auto">
      <table className="border-collapse text-xs min-w-max">
        <thead>
          <tr>
            <th className="text-left pr-4 pb-2 text-apple-secondary font-medium min-w-[80px]">목적지</th>
            {months.map((m) => (
              <th key={m} className="pb-2 px-1 text-apple-secondary font-medium min-w-[64px]">
                {m.slice(5)}월
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {destinations.map((dest) => (
            <tr key={dest}>
              <td className="pr-4 py-1 text-apple-text font-medium whitespace-nowrap">
                {destNames[dest]}
              </td>
              {months.map((m) => {
                const cell = pivot[dest][m];
                if (!cell) {
                  return (
                    <td key={m} className="px-1 py-1">
                      <div className="rounded-lg bg-apple-text/5 h-10 w-16" />
                    </td>
                  );
                }
                const hoursSinceRun = (now - new Date(cell.last_run_at).getTime()) / 3_600_000;
                return (
                  <td key={m} className="px-1 py-1">
                    <div
                      className={`rounded-lg h-10 w-16 flex items-center justify-center font-semibold ${coverageColor(cell.legs, hoursSinceRun)}`}
                      title={`최근 실행: ${cell.last_run_at}`}
                    >
                      {cell.legs}건
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-apple-secondary mt-3">
        <span className="inline-block w-3 h-3 rounded-sm mr-1 align-middle bg-apple-green/40" />정상
        <span className="inline-block w-3 h-3 rounded-sm ml-3 mr-1 align-middle bg-yellow-200" />지연
        <span className="inline-block w-3 h-3 rounded-sm ml-3 mr-1 align-middle bg-apple-red/40" />0건
      </p>
    </div>
  );
}

const STATUS_STYLE: Record<string, { color: string; label: string }> = {
  running: { color: "text-apple-blue",      label: "실행 중" },
  success: { color: "text-apple-green",     label: "성공" },
  partial: { color: "text-yellow-600",      label: "부분 실패" },
  error:   { color: "text-apple-red",       label: "실패" },
};

function formatDuration(sec: number | null): string {
  if (sec == null) return "-";
  if (sec < 60) return `${Math.round(sec)}초`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}분 ${s}초`;
}

function formatTime(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleString("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export default function Monitor() {
  const [runs, setRuns] = useState<CollectionRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [errorLog, setErrorLog] = useState<string | null>(null);
  const [logLoading, setLogLoading] = useState(false);

  const [coverage, setCoverage] = useState<CoverageByDestMonth[]>([]);
  const [coverageLoading, setCoverageLoading] = useState(true);

  useEffect(() => {
    fetchCollectionRuns(50)
      .then(setRuns)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchCoverage()
      .then((res) => setCoverage(res.by_destination_month))
      .catch(console.error)
      .finally(() => setCoverageLoading(false));
  }, []);

  const handleRowClick = async (run: CollectionRun) => {
    if (expandedId === run.id) {
      setExpandedId(null);
      setErrorLog(null);
      return;
    }
    setExpandedId(run.id);
    if (!run.has_error) {
      setErrorLog(null);
      return;
    }
    setLogLoading(true);
    try {
      const detail = await fetchRunDetail(run.id);
      setErrorLog(detail.error_log ?? null);
    } catch {
      setErrorLog("에러 로그 조회 실패");
    } finally {
      setLogLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-apple-secondary">
        로딩 중…
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section className="bg-apple-surface border border-apple-tertiary/50 rounded-2xl shadow-apple p-5 sm:p-6 space-y-4">
        <h2 className="text-base font-semibold text-apple-text">수집 이력</h2>

        {runs.length === 0 ? (
          <p className="text-sm text-apple-secondary">수집 이력이 없습니다.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-apple-text/5 text-apple-secondary">
                  <th className="text-left py-2 px-2 font-medium">시간</th>
                  <th className="text-left py-2 px-2 font-medium">상태</th>
                  <th className="text-right py-2 px-2 font-medium">GF</th>
                  <th className="text-right py-2 px-2 font-medium">총건수</th>
                  <th className="text-right py-2 px-2 font-medium">알림</th>
                  <th className="text-right py-2 px-2 font-medium">소요</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => {
                  const s = STATUS_STYLE[run.status] ?? STATUS_STYLE.error;
                  const isExpanded = expandedId === run.id;
                  return (
                    <React.Fragment key={run.id}>
                      <tr
                        onClick={() => handleRowClick(run)}
                        className={`border-b border-apple-text/5 transition-colors cursor-pointer hover:bg-apple-bg ${
                          isExpanded ? "bg-apple-bg" : ""
                        }`}
                      >
                        <td className="py-2 px-2 text-apple-text whitespace-nowrap">
                          {formatTime(run.started_at)}
                        </td>
                        <td className={`py-2 px-2 font-medium ${s.color}`}>
                          {s.label}
                          {run.has_error && " ⚠"}
                        </td>
                        <td className="py-2 px-2 text-right text-apple-text">
                          {run.google_count}
                        </td>
                        <td className="py-2 px-2 text-right text-apple-text font-medium">
                          {run.total_saved}
                        </td>
                        <td className="py-2 px-2 text-right text-apple-text">
                          {run.alerts_sent}
                        </td>
                        <td className="py-2 px-2 text-right text-apple-secondary whitespace-nowrap">
                          {formatDuration(run.duration_sec)}
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr>
                          <td colSpan={6} className="p-0">
                            <div className="px-3 py-3 bg-apple-bg">
                              {run.has_error ? (
                                logLoading ? (
                                  <p className="text-xs text-apple-secondary">로딩 중…</p>
                                ) : (
                                  <pre className="bg-zinc-900 text-gray-300 text-[11px] leading-relaxed rounded-xl p-4 max-h-64 overflow-y-auto whitespace-pre-wrap">
                                    {errorLog}
                                  </pre>
                                )
                              ) : (
                                <p className="text-xs text-apple-secondary">
                                  에러 없이 정상 완료되었습니다.
                                </p>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="bg-apple-surface border border-apple-tertiary/50 rounded-2xl shadow-apple p-5 sm:p-6 space-y-4">
        <h2 className="text-base font-semibold text-apple-text">목적지 × 월별 수집 현황</h2>
        {coverageLoading ? (
          <p className="text-sm text-apple-secondary py-4">로딩 중…</p>
        ) : (
          <CoverageHeatmap data={coverage} />
        )}
      </section>
    </div>
  );
}
