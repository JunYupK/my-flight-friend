import React, { useEffect, useState } from "react";
import { fetchCollectionRuns, fetchRunDetail } from "../api";
import type { CollectionRun } from "../types";

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

  useEffect(() => {
    fetchCollectionRuns(50)
      .then(setRuns)
      .catch(console.error)
      .finally(() => setLoading(false));
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
      <section className="bg-white rounded-2xl shadow-apple p-5 sm:p-6 space-y-4">
        <h2 className="text-base font-semibold text-apple-text">수집 이력</h2>

        {runs.length === 0 ? (
          <p className="text-sm text-apple-secondary">수집 이력이 없습니다.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-black/5 text-apple-secondary">
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
                        className={`border-b border-black/5 transition-colors cursor-pointer hover:bg-apple-bg ${
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
                                  <pre className="bg-apple-text text-gray-300 text-[11px] leading-relaxed rounded-xl p-4 max-h-64 overflow-y-auto whitespace-pre-wrap">
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
    </div>
  );
}
