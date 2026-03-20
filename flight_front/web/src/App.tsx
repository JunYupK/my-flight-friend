import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Link, useLocation } from "react-router-dom";
import { fetchConfig, saveConfig } from "./api";
import type { ConfigData } from "./types";
import AirportList from "./components/AirportList";
import SearchConfigForm from "./components/SearchConfig";
import Results from "./components/Results";
import Trends from "./components/Trends";
import Landing from "./components/Landing";
import RunControl from "./components/RunControl";

const NAV_ITEMS = [
  { path: "/deals", label: "최저가" },
  { path: "/trends", label: "추이" },
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
    <div className="min-h-screen bg-apple-bg">
      {/* Glass header */}
      <header className="sticky top-0 z-30 backdrop-blur-xl bg-white/72 border-b border-black/5">
        <div className="max-w-5xl mx-auto px-4 sm:px-6">
          <div className="flex items-center justify-between h-12">
            {/* Left: logo + nav */}
            <div className="flex items-center gap-1 sm:gap-2">
              <Link
                to="/"
                className="font-semibold text-apple-text text-sm tracking-tight shrink-0 hover:opacity-70 transition-opacity mr-1 sm:mr-3"
              >
                Flight Friend
              </Link>

              <nav className="flex gap-0.5">
                {NAV_ITEMS.map((item) => (
                  <Link
                    key={item.path}
                    to={item.path}
                    className={`px-3 py-1 rounded-full text-xs font-medium transition-all duration-200 ${
                      location.pathname === item.path
                        ? "bg-apple-text text-white"
                        : "text-apple-secondary hover:text-apple-text hover:bg-black/5"
                    }`}
                  >
                    {item.label}
                  </Link>
                ))}
              </nav>
            </div>

            {/* Right: settings link or save button */}
            <div className="flex items-center gap-2">
              {saveMsg && (
                <span className={`text-xs ${saveMsg.includes("실패") ? "text-apple-red" : "text-apple-green"}`}>
                  {saveMsg}
                </span>
              )}
              {isSettings ? (
                <button
                  onClick={handleSave}
                  disabled={saving || !config}
                  className="px-4 py-1.5 bg-apple-blue text-white rounded-full text-xs font-medium hover:bg-apple-blue-hover disabled:opacity-40 transition-all duration-200"
                >
                  {saving ? "저장 중…" : "설정 저장"}
                </button>
              ) : (
                <Link
                  to="/settings"
                  className={`p-1.5 rounded-full transition-all duration-200 ${
                    isSettings
                      ? "bg-apple-text text-white"
                      : "text-apple-secondary hover:text-apple-text hover:bg-black/5"
                  }`}
                  aria-label="설정"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="3" />
                    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
                  </svg>
                </Link>
              )}
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-6 sm:py-10">
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
                  <div className="flex items-center justify-center py-10 text-apple-secondary">로딩 중…</div>
                ) : (
                  <SearchConfigForm
                    value={config.search_config}
                    onChange={(sc) => setConfig((c) => c ? { ...c, search_config: sc } : c)}
                  />
                )}
                <RunControl />
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
