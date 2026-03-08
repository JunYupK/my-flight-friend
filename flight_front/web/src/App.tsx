import React, { useEffect, useState } from "react";
import { fetchConfig, saveConfig } from "./api";
import type { ConfigData } from "./types";
import AirportList from "./components/AirportList";
import SearchConfigForm from "./components/SearchConfig";
import RunControl from "./components/RunControl";
import Results from "./components/Results";

type Tab = "results" | "settings";

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
      {/* 헤더 */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4">
          <div className="flex items-center h-14 gap-6">
            <span className="font-bold text-gray-800 text-base shrink-0">✈ Flight Friend</span>

            {/* 탭 */}
            <nav className="flex gap-1">
              {(["results", "settings"] as Tab[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    tab === t
                      ? "bg-blue-50 text-blue-600"
                      : "text-gray-500 hover:text-gray-700 hover:bg-gray-50"
                  }`}
                >
                  {t === "results" ? "수집 결과" : "설정"}
                </button>
              ))}
            </nav>

            {/* 저장 버튼 (설정 탭일 때만) */}
            {tab === "settings" && (
              <div className="ml-auto flex items-center gap-3">
                {saveMsg && (
                  <span
                    className={`text-sm ${
                      saveMsg.includes("실패") ? "text-red-500" : "text-green-500"
                    }`}
                  >
                    {saveMsg}
                  </span>
                )}
                <button
                  onClick={handleSave}
                  disabled={saving || !config}
                  className="px-4 py-1.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
                >
                  {saving ? "저장 중…" : "저장"}
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* 본문 */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        {tab === "results" && <Results />}

        {tab === "settings" && (
          <>
            {!config ? (
              <div className="flex items-center justify-center py-20 text-gray-400">
                로딩 중…
              </div>
            ) : (
              <div className="space-y-6">
                <AirportList
                  airports={config.japan_airports}
                  tfsTemplates={config.tfs_templates}
                  onAirportsChange={(ja) => setConfig((c) => c ? { ...c, japan_airports: ja } : c)}
                  onTfsChange={(tfs) => setConfig((c) => c ? { ...c, tfs_templates: tfs } : c)}
                />
                <SearchConfigForm
                  value={config.search_config}
                  onChange={(sc) => setConfig((c) => c ? { ...c, search_config: sc } : c)}
                />
                <RunControl />
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
