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
import Monitor from "./components/Monitor";
import Search from "./components/Search";

const NAV_ITEMS = [
  { path: "/deals", label: "최저가" },
  { path: "/trends", label: "추이" },
  { path: "/search", label: "검색" },
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

            {/* Right: save button (settings page only) */}
            {isSettings && (
              <div className="flex items-center gap-2">
                {saveMsg && (
                  <span className={`text-xs ${saveMsg.includes("실패") ? "text-apple-red" : "text-apple-green"}`}>
                    {saveMsg}
                  </span>
                )}
                <button
                  onClick={handleSave}
                  disabled={saving || !config}
                  className="px-4 py-1.5 bg-apple-blue text-white rounded-full text-xs font-medium hover:bg-apple-blue-hover disabled:opacity-40 transition-all duration-200"
                >
                  {saving ? "저장 중…" : "설정 저장"}
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-6 sm:py-10">
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/deals" element={<Results />} />
          <Route path="/trends" element={<Trends />} />
          <Route path="/search" element={<Search />} />
          <Route path="/monitor" element={<Monitor />} />
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
