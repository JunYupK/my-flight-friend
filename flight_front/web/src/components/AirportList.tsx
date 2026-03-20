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
    <section className="bg-white rounded-2xl shadow-apple p-5 sm:p-6 space-y-5">
      <div className="flex items-center gap-3">
        <h2 className="text-base font-semibold text-apple-text">목적지 공항</h2>
        {msg && (
          <span className={`text-xs ${msg.ok ? "text-apple-green" : "text-apple-red"}`}>
            {msg.text}
          </span>
        )}
      </div>

      <div className="space-y-3">
        {airports.map((airport) => {
          const a = editing[airport.code] ?? airport;
          return (
            <div key={airport.code} className="rounded-xl bg-apple-bg overflow-hidden">
              {/* 헤더 */}
              <div className="flex items-center gap-3 px-4 py-3">
                <span className="font-bold text-sm text-apple-blue w-10 shrink-0">{airport.code}</span>
                <input
                  type="text"
                  value={a.name}
                  onChange={(e) => patch(airport.code, "name", e.target.value)}
                  className="flex-1 text-sm text-apple-text bg-transparent border-b border-apple-tertiary/30 focus:outline-none focus:border-apple-blue transition-colors min-w-0"
                />
                <button
                  onClick={() => handleSave(airport.code)}
                  disabled={saving[airport.code]}
                  className="text-xs px-3 py-1 rounded-full bg-apple-blue text-white hover:bg-apple-blue-hover disabled:opacity-40 transition-all duration-200 shrink-0"
                >
                  {saving[airport.code] ? "저장 중…" : "저장"}
                </button>
                <button
                  onClick={() => handleDelete(airport.code)}
                  className="text-xs px-2 py-1 rounded-full text-apple-red hover:bg-apple-red/10 transition-all duration-200 shrink-0"
                >
                  삭제
                </button>
              </div>

              {/* tfs 입력 */}
              <div className="px-4 pb-4 pt-1 space-y-2">
                {!a.tfs_out && !a.tfs_in && (
                  <p className="text-[11px] text-apple-secondary">
                    구글 플라이트에서 ICN↔{airport.code} 편도 검색 후 URL의{" "}
                    <code className="bg-white px-1 rounded text-apple-blue">tfs=</code> 값 붙여넣기
                  </p>
                )}
                <label className="flex flex-col gap-1">
                  <span className="text-[11px] font-medium text-apple-secondary">
                    ICN → {airport.code} (출발)
                    {a.tfs_out && <span className="ml-1 text-apple-green">✓</span>}
                  </span>
                  <input
                    type="text"
                    placeholder="tfs= 값 또는 전체 URL"
                    value={a.tfs_out}
                    onChange={(e) => patch(airport.code, "tfs_out", e.target.value)}
                    className="bg-white rounded-xl px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-apple-blue/30 shadow-apple-sm"
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-[11px] font-medium text-apple-secondary">
                    {airport.code} → ICN (복귀)
                    {a.tfs_in && <span className="ml-1 text-apple-green">✓</span>}
                  </span>
                  <input
                    type="text"
                    placeholder="tfs= 값 또는 전체 URL"
                    value={a.tfs_in}
                    onChange={(e) => patch(airport.code, "tfs_in", e.target.value)}
                    className="bg-white rounded-xl px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-apple-blue/30 shadow-apple-sm"
                  />
                </label>
              </div>
            </div>
          );
        })}
      </div>

      {/* 새 목적지 추가 */}
      <div className="space-y-3 pt-3 border-t border-apple-tertiary/20">
        <p className="text-xs font-medium text-apple-secondary">새 목적지 추가</p>
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            type="text"
            placeholder="코드 (예: OSA)"
            value={newAirport.code}
            onChange={(e) => setNewAirport((n) => ({ ...n, code: e.target.value.toUpperCase() }))}
            maxLength={3}
            className="w-full sm:w-24 bg-apple-bg rounded-xl px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-apple-blue/30"
          />
          <input
            type="text"
            placeholder="이름 (예: 오사카)"
            value={newAirport.name}
            onChange={(e) => setNewAirport((n) => ({ ...n, name: e.target.value }))}
            className="flex-1 bg-apple-bg rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-apple-blue/30"
          />
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            type="text"
            placeholder="ICN → 목적지 tfs= 값"
            value={newAirport.tfs_out}
            onChange={(e) => setNewAirport((n) => ({ ...n, tfs_out: e.target.value }))}
            className="flex-1 bg-apple-bg rounded-xl px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-apple-blue/30"
          />
          <input
            type="text"
            placeholder="목적지 → ICN tfs= 값"
            value={newAirport.tfs_in}
            onChange={(e) => setNewAirport((n) => ({ ...n, tfs_in: e.target.value }))}
            className="flex-1 bg-apple-bg rounded-xl px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-apple-blue/30"
          />
          <button
            onClick={handleAdd}
            disabled={adding || !newAirport.code.trim() || !newAirport.name.trim()}
            className="px-5 py-2 bg-apple-blue text-white rounded-full text-sm font-medium hover:bg-apple-blue-hover disabled:opacity-40 transition-all duration-200 shrink-0"
          >
            {adding ? "추가 중…" : "추가"}
          </button>
        </div>
      </div>
    </section>
  );
}
