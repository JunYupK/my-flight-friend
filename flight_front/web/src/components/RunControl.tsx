import React, { useEffect, useRef, useState } from "react";
import { startRun } from "../api";

type Status = "idle" | "running" | "done" | "error";

export default function RunControl() {
  const [status, setStatus]   = useState<Status>("idle");
  const [output, setOutput]   = useState("");
  const [error, setError]     = useState("");
  const wsRef     = useRef<WebSocket | null>(null);
  const outputRef = useRef<HTMLPreElement>(null);

  // 마운트 시 WebSocket 연결 — 서버의 현재 상태/로그를 즉시 수신
  useEffect(() => {
    connect();
    return () => wsRef.current?.close();
  }, []);

  // 출력 자동 스크롤
  useEffect(() => {
    if (outputRef.current)
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
  }, [output]);

  function connect() {
    const ws = new WebSocket(`ws://${location.host}/ws/run`);
    wsRef.current = ws;

    ws.onmessage = ({ data }: MessageEvent<string>) => {
      if (data === "__status__:running") {
        setStatus("running");
      } else if (data === "__status__:done") {
        setStatus("done");
      } else if (data === "__status__:error") {
        setStatus("error");
      } else if (data.startsWith("__status__:")) {
        // idle 등
        setStatus(data.split(":")[1] as Status);
      } else {
        setOutput((prev) => prev + data);
      }
    };

    ws.onclose = () => {
      // 연결 끊기면 2초 후 재연결
      setTimeout(connect, 2000);
    };
  }

  const handleRun = async () => {
    setError("");
    setOutput("");
    setStatus("running");
    try {
      await startRun();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("idle");
    }
  };

  const statusColor: Record<Status, string> = {
    idle:    "text-gray-500",
    running: "text-blue-600",
    done:    "text-green-600",
    error:   "text-red-600",
  };
  const statusLabel: Record<Status, string> = {
    idle:    "대기 중",
    running: "수집 중…",
    done:    "완료",
    error:   "오류",
  };

  return (
    <section className="bg-white rounded-xl shadow p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">수집 실행</h2>
        <span className={`text-sm font-medium ${statusColor[status]}`}>
          {statusLabel[status]}
        </span>
      </div>

      <button
        onClick={handleRun}
        disabled={status === "running"}
        className="px-5 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {status === "running" ? "수집 중…" : "수집 시작"}
      </button>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {output && (
        <pre
          ref={outputRef}
          className="bg-gray-900 text-gray-100 text-xs rounded-lg p-4 h-64 overflow-y-auto whitespace-pre-wrap"
        >
          {output}
        </pre>
      )}
    </section>
  );
}
