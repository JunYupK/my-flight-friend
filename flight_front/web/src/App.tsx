import React, { useEffect, useState } from "react";
import { fetchConfig, saveConfig } from "./api";
import type { ConfigData } from "./types";
import AirportList from "./components/AirportList";
import SearchConfigForm from "./components/SearchConfig";
import RunControl from "./components/RunControl";
import Results from "./components/Results";
import Trends from "./components/Trends";

type Tab = "results" | "trends" | "settings";

const TAB_LABELS: Record<Tab, string> = {
  results: "오늘의 최저가",
  trends: "가격 추이",
  settings: "설정",
};

export default function App() {
  const [tab, setTab] = useState<Tab>("results");
  const [config, setConfig] = useState<ConfigData | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");

  useEffect(() => {
    fetchConfig().then(setConfig).catch(console.error);
  }, []);

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    setSaveMsg("");
    try {
      await saveConfig(config);
      setSaveMsg("저장되었습니다.");
    } catch {
      setSaveMsg("저장 실패");
    } finally {
      setSaving(false);
      setTimeout(() => setSaveMsg(""), 3000);
    }
  };

  return (
    <div className="min-h-screen bg-gray-100">
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4">
          <div className="flex items-center h-14 gap-2 sm:gap-6">
            <span className="font-bold text-gray-800 text-base shrink-0">Flight Friend</span>

            <nav className="flex gap-1">
              {(["results", "trends", "settings"] as Tab[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    tab === t
                      ? "bg-blue-50 text-blue-600"
                      : "text-gray-500 hover:text-gray-700 hover:bg-gray-50"
                  }`}
                >
                  {TAB_LABELS[t]}
                </button>
              ))}
            </nav>

            {/* 저장 버튼 — 검색 설정 전용 */}
            {tab === "settings" && (
              <div className="ml-auto flex items-center gap-3">
                {saveMsg && (
                  <span className={`text-sm ${saveMsg.includes("실패") ? "text-red-500" : "text-green-500"}`}>
                    {saveMsg}
                  </span>
                )}
                <button
                  onClick={handleSave}
                  disabled={saving || !config}
                  className="px-4 py-1.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
                >
                  {saving ? "저장 중…" : <><span className="hidden sm:inline">검색 설정 </span>저장</>}
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-8">
        {tab === "results" && <Results />}

        {tab === "trends" && <Trends />}

        {tab === "settings" && (
          <div className="space-y-6">
            {/* 공항 목록 — 독립 저장 */}
            <AirportList />

            {/* 검색 설정 — 헤더 저장 버튼 */}
            {!config ? (
              <div className="flex items-center justify-center py-10 text-gray-400">로딩 중…</div>
            ) : (
              <SearchConfigForm
                value={config.search_config}
                onChange={(sc) => setConfig((c) => c ? { ...c, search_config: sc } : c)}
              />
            )}

            <RunControl />
          </div>
        )}
      </main>
    </div>
  );
}
