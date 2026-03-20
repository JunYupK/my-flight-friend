import React, { useEffect, useRef, useState } from "react";
import { startRun } from "../api";

type Status = "idle" | "running" | "done" | "error";

export default function RunControl() {
  const [status, setStatus]   = useState<Status>("idle");
  const [output, setOutput]   = useState("");
  const [error, setError]     = useState("");
  const wsRef     = useRef<WebSocket | null>(null);
  const outputRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    connect();
    return () => wsRef.current?.close();
  }, []);

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
        setStatus(data.split(":")[1] as Status);
      } else {
        setOutput((prev) => prev + data);
      }
    };

    ws.onclose = () => {
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
    idle:    "text-apple-secondary",
    running: "text-apple-blue",
    done:    "text-apple-green",
    error:   "text-apple-red",
  };
  const statusLabel: Record<Status, string> = {
    idle:    "대기 중",
    running: "수집 중…",
    done:    "완료",
    error:   "오류",
  };

  return (
    <section className="bg-white rounded-2xl shadow-apple p-5 sm:p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-apple-text">수집 실행</h2>
        <span className={`text-xs font-medium ${statusColor[status]}`}>
          {statusLabel[status]}
        </span>
      </div>

      <button
        onClick={handleRun}
        disabled={status === "running"}
        className="px-5 py-2.5 bg-apple-blue text-white rounded-full text-sm font-medium hover:bg-apple-blue-hover disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-200"
      >
        {status === "running" ? "수집 중…" : "수집 시작"}
      </button>

      {error && <p className="text-xs text-apple-red">{error}</p>}

      {output && (
        <pre
          ref={outputRef}
          className="bg-apple-text text-gray-300 text-[11px] leading-relaxed rounded-2xl p-4 h-64 overflow-y-auto whitespace-pre-wrap"
        >
          {output}
        </pre>
      )}
    </section>
  );
}
