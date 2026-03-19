import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Link, useLocation } from "react-router-dom";
import { fetchConfig, saveConfig } from "./api";
import type { ConfigData } from "./types";
import AirportList from "./components/AirportList";
import SearchConfigForm from "./components/SearchConfig";
import Results from "./components/Results";
import Trends from "./components/Trends";
import Landing from "./components/Landing";

const NAV_ITEMS = [
  { path: "/deals", label: "오늘의 최저가" },
  { path: "/trends", label: "가격 추이" },
];

function Layout() {
  const location = useLocation();
  const isSettings = location.pathname === "/settings";

  const [config, setConfig] = useState<ConfigData | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");

  useEffect(() => {
    if (isSettings) {
      fetchConfig().then(setConfig).catch(console.error);
    }
  }, [isSettings]);

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
            <Link to="/" className="font-bold text-gray-800 text-base shrink-0 hover:text-blue-600 transition-colors">
              Flight Friend
            </Link>

            <nav className="flex gap-1">
              {NAV_ITEMS.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    location.pathname === item.path
                      ? "bg-blue-50 text-blue-600"
                      : "text-gray-500 hover:text-gray-700 hover:bg-gray-50"
                  }`}
                >
                  {item.label}
                </Link>
              ))}
            </nav>

            {/* 저장 버튼 — 설정 페이지 전용 */}
            {isSettings && (
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
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/deals" element={<Results />} />
          <Route path="/trends" element={<Trends />} />
          <Route
            path="/settings"
            element={
              <div className="space-y-6">
                <AirportList />
                {!config ? (
                  <div className="flex items-center justify-center py-10 text-gray-400">로딩 중…</div>
                ) : (
                  <SearchConfigForm
                    value={config.search_config}
                    onChange={(sc) => setConfig((c) => c ? { ...c, search_config: sc } : c)}
                  />
                )}
              </div>
            }
          />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Layout />
    </BrowserRouter>
  );
}
