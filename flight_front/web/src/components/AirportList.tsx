import React, { useEffect, useState } from "react";
import type { Airport } from "../types";
import { fetchAirports, upsertAirport, deleteAirport } from "../api";

const EMPTY: Airport = { code: "", name: "", tfs_out: "", tfs_in: "" };

export default function AirportList() {
  const [airports, setAirports] = useState<Airport[]>([]);
  const [editing, setEditing] = useState<Record<string, Airport>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [newAirport, setNewAirport] = useState<Airport>(EMPTY);
  const [adding, setAdding] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);

  const showMsg = (text: string, ok: boolean) => {
    setMsg({ text, ok });
    setTimeout(() => setMsg(null), 3000);
  };

  const load = () =>
    fetchAirports().then((list) => {
      setAirports(list);
      const buf: Record<string, Airport> = {};
      list.forEach((a) => (buf[a.code] = { ...a }));
      setEditing(buf);
    }).catch((e) => showMsg(`로드 실패: ${e.message}`, false));

  useEffect(() => { load(); }, []);

  const handleSave = async (code: string) => {
    setSaving((s) => ({ ...s, [code]: true }));
    try {
      await upsertAirport(editing[code]);
      await load();
      showMsg(`${code} 저장 완료`, true);
    } catch (e: any) {
      showMsg(`저장 실패: ${e.message}`, false);
    } finally {
      setSaving((s) => ({ ...s, [code]: false }));
    }
  };

  const handleDelete = async (code: string) => {
    if (!confirm(`${code} 공항을 삭제하시겠습니까?`)) return;
    try {
      await deleteAirport(code);
      await load();
      showMsg(`${code} 삭제 완료`, true);
    } catch (e: any) {
      showMsg(`삭제 실패: ${e.message}`, false);
    }
  };

  const handleAdd = async () => {
    const code = newAirport.code.trim().toUpperCase();
    const name = newAirport.name.trim();
    if (!code || !name) {
      showMsg("코드와 이름을 모두 입력해주세요", false);
      return;
    }
    setAdding(true);
    try {
      await upsertAirport({ ...newAirport, code, name });
      setNewAirport(EMPTY);
      await load();
      showMsg(`${code} 추가 완료`, true);
    } catch (e: any) {
      showMsg(`추가 실패: ${e.message}`, false);
    } finally {
      setAdding(false);
    }
  };

  const patch = (code: string, field: keyof Airport, val: string) =>
    setEditing((e) => ({ ...e, [code]: { ...e[code], [field]: val } }));

  return (
    <section className="bg-white rounded-xl shadow p-6 space-y-4">
      <div className="flex items-center gap-3">
        <h2 className="text-lg font-semibold">목적지 공항</h2>
        {msg && (
          <span className={`text-sm ${msg.ok ? "text-green-500" : "text-red-500"}`}>
            {msg.text}
          </span>
        )}
      </div>

      <div className="space-y-3">
        {airports.map((airport) => {
          const a = editing[airport.code] ?? airport;
          return (
            <div key={airport.code} className="rounded-lg border-2 border-blue-400">
              {/* 헤더 */}
              <div className="flex items-center gap-3 px-4 py-3 bg-blue-50">
                <span className="font-bold text-sm w-8 text-blue-700">{airport.code}</span>
                <input
                  type="text"
                  value={a.name}
                  onChange={(e) => patch(airport.code, "name", e.target.value)}
                  className="flex-1 text-sm text-blue-700 bg-transparent border-b border-blue-200 focus:outline-none focus:border-blue-500"
                />
                <button
                  onClick={() => handleSave(airport.code)}
                  disabled={saving[airport.code]}
                  className="text-xs px-3 py-1 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
                >
                  {saving[airport.code] ? "저장 중…" : "저장"}
                </button>
                <button
                  onClick={() => handleDelete(airport.code)}
                  className="text-xs px-2 py-1 rounded-lg text-red-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                >
                  삭제
                </button>
              </div>

              {/* tfs 입력 */}
              <div className="px-4 pb-4 pt-2 space-y-2 bg-white">
                {!a.tfs_out && !a.tfs_in && (
                  <p className="text-xs text-gray-400">
                    구글 플라이트에서 ICN↔{airport.code} 편도 검색 후 URL의{" "}
                    <code className="bg-gray-100 px-1 rounded">tfs=</code> 값 붙여넣기
                  </p>
                )}
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-medium text-gray-500">
                    ICN → {airport.code} (출발)
                    {a.tfs_out && <span className="ml-1 text-green-500">✓</span>}
                  </span>
                  <input
                    type="text"
                    placeholder="tfs= 값 또는 전체 URL"
                    value={a.tfs_out}
                    onChange={(e) => patch(airport.code, "tfs_out", e.target.value)}
                    className="border rounded px-3 py-1.5 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-400"
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-medium text-gray-500">
                    {airport.code} → ICN (복귀)
                    {a.tfs_in && <span className="ml-1 text-green-500">✓</span>}
                  </span>
                  <input
                    type="text"
                    placeholder="tfs= 값 또는 전체 URL"
                    value={a.tfs_in}
                    onChange={(e) => patch(airport.code, "tfs_in", e.target.value)}
                    className="border rounded px-3 py-1.5 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-400"
                  />
                </label>
              </div>
            </div>
          );
        })}
      </div>

      {/* 새 목적지 추가 */}
      <div className="space-y-2 pt-2 border-t border-gray-100">
        <p className="text-xs font-medium text-gray-500">새 목적지 추가</p>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="코드 (예: OSA)"
            value={newAirport.code}
            onChange={(e) => setNewAirport((n) => ({ ...n, code: e.target.value.toUpperCase() }))}
            maxLength={3}
            className="w-28 border rounded px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          <input
            type="text"
            placeholder="이름 (예: 오사카)"
            value={newAirport.name}
            onChange={(e) => setNewAirport((n) => ({ ...n, name: e.target.value }))}
            className="flex-1 border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="ICN → 목적지 tfs= 값"
            value={newAirport.tfs_out}
            onChange={(e) => setNewAirport((n) => ({ ...n, tfs_out: e.target.value }))}
            className="flex-1 border rounded px-3 py-1.5 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          <input
            type="text"
            placeholder="목적지 → ICN tfs= 값"
            value={newAirport.tfs_in}
            onChange={(e) => setNewAirport((n) => ({ ...n, tfs_in: e.target.value }))}
            className="flex-1 border rounded px-3 py-1.5 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          <button
            onClick={handleAdd}
            disabled={adding || !newAirport.code.trim() || !newAirport.name.trim()}
            className="px-4 py-1.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-40 transition-colors"
          >
            {adding ? "추가 중…" : "추가"}
          </button>
        </div>
      </div>
    </section>
  );
}
