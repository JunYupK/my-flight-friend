import React from "react";

const ALL_AIRPORTS: Record<string, string> = {
  TYO: "도쿄 (나리타/하네다)",
  OSA: "오사카 (간사이/이타미)",
  FUK: "후쿠오카",
  CTS: "삿포로 (신치토세)",
  OKA: "오키나와 (나하)",
  NGO: "나고야 (중부)",
  HIJ: "히로시마",
  SDJ: "센다이",
  KIJ: "니가타",
};

interface Props {
  airports: Record<string, string>;
  tfsTemplates: Record<string, string>;
  onAirportsChange: (v: Record<string, string>) => void;
  onTfsChange: (v: Record<string, string>) => void;
}

export default function AirportList({ airports, tfsTemplates, onAirportsChange, onTfsChange }: Props) {
  const toggleAirport = (code: string) => {
    const next = { ...airports };
    if (next[code]) {
      delete next[code];
    } else {
      next[code] = ALL_AIRPORTS[code];
    }
    onAirportsChange(next);
  };

  const setTfs = (key: string, val: string) => {
    onTfsChange({ ...tfsTemplates, [key]: val });
  };

  return (
    <section className="bg-white rounded-xl shadow p-6 space-y-4">
      <h2 className="text-lg font-semibold">목적지 공항</h2>
      <div className="space-y-3">
        {Object.entries(ALL_AIRPORTS).map(([code, name]) => {
          const active = !!airports[code];
          const keyOut = `ICN_${code}`;
          const keyIn  = `${code}_ICN`;
          return (
            <div key={code} className={`rounded-lg border-2 transition-colors ${active ? "border-blue-400" : "border-gray-200"}`}>
              <button
                onClick={() => toggleAirport(code)}
                className={`w-full flex items-center gap-3 px-4 py-3 text-left ${active ? "bg-blue-50" : "bg-gray-50 hover:bg-gray-100"}`}
              >
                <span className={`font-bold text-sm w-8 ${active ? "text-blue-700" : "text-gray-400"}`}>{code}</span>
                <span className={`text-sm ${active ? "text-blue-700" : "text-gray-500"}`}>{name}</span>
                <span className="ml-auto text-xs text-gray-400">{active ? "▲ 활성" : "▼ 비활성"}</span>
              </button>

              <div className="px-4 pb-4 pt-2 space-y-2 bg-white">
                {!tfsTemplates[keyOut] && !tfsTemplates[keyIn] && (
                  <p className="text-xs text-gray-400">
                    구글 플라이트에서 ICN↔{code} 편도 검색 후 URL의 <code className="bg-gray-100 px-1 rounded">tfs=</code> 값 붙여넣기
                  </p>
                )}
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-medium text-gray-500">
                    ICN → {code} (출발)
                    {tfsTemplates[keyOut] && <span className="ml-1 text-green-500">✓</span>}
                  </span>
                  <input
                    type="text"
                    placeholder="tfs= 값"
                    value={tfsTemplates[keyOut] ?? ""}
                    onChange={(e) => setTfs(keyOut, e.target.value)}
                    className="border rounded px-3 py-1.5 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-400"
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-medium text-gray-500">
                    {code} → ICN (복귀)
                    {tfsTemplates[keyIn] && <span className="ml-1 text-green-500">✓</span>}
                  </span>
                  <input
                    type="text"
                    placeholder="tfs= 값"
                    value={tfsTemplates[keyIn] ?? ""}
                    onChange={(e) => setTfs(keyIn, e.target.value)}
                    className="border rounded px-3 py-1.5 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-400"
                  />
                </label>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
