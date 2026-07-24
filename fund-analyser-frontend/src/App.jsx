import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import {
  Search, ArrowLeft, ArrowUp, ArrowDown, X, GitCompare,
} from "lucide-react";

const API_BASE = "http://localhost:8000";

const fonts = `
  @import url('https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,500&family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
  .mono { font-family: 'IBM Plex Mono', monospace; font-variant-numeric: tabular-nums; }
  .serif { font-family: 'Newsreader', serif; }
  .ledger-line { border-bottom: 1px solid rgba(237,234,226,0.08); }
`;

// palette
const BG = "#0A131F", PANEL = "#0F1B2B", INK = "#EDEAE2", MUTE = "#8B96A6";
const GOLD = "#C9A227", GREEN = "#3FA796", RED = "#C6524B";
const BORDER = "1px solid rgba(237,234,226,0.08)";

const PERIODS = ["1M", "3M", "6M", "1Y", "3Y", "5Y", "10Y"];

function retColor(v) { return v == null ? MUTE : v >= 0 ? GREEN : RED; }
function fmtPct(v) { return v == null ? "—" : `${v}%`; }
function fmtNum(v) { return v == null ? "—" : v; }

// ---------------------------------------------------------------------------
// Explorer (home)
// ---------------------------------------------------------------------------
function Explorer({ onSelectScheme, compareCodes, toggleCompare, onOpenCompare }) {
  const [facets, setFacets] = useState({ categories: [], amcs: [] });
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [amc, setAmc] = useState("");
  const [optionType, setOptionType] = useState("Growth");
  const [sort, setSort] = useState("3Y");
  const [order, setOrder] = useState("desc");
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const debounceRef = useRef();

  useEffect(() => {
    fetch(`${API_BASE}/api/schemes/facets`).then(r => r.json()).then(setFacets).catch(() => {});
  }, []);

  const load = useCallback(() => {
    const params = new URLSearchParams({ sort, order, page, page_size: 50 });
    if (q) params.set("q", q);
    if (category) params.set("category", category);
    if (amc) params.set("amc", amc);
    if (optionType) params.set("option_type", optionType);
    fetch(`${API_BASE}/api/schemes?${params}`)
      .then(r => { if (!r.ok) throw new Error(`API ${r.status}`); return r.json(); })
      .then(d => { setData(d); setError(null); })
      .catch(e => setError(e.message));
  }, [q, category, amc, optionType, sort, order, page]);

  // debounce search text; other filters apply immediately
  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(load, 250);
    return () => clearTimeout(debounceRef.current);
  }, [load]);

  // reset to page 1 when filters/search change
  useEffect(() => { setPage(1); }, [q, category, amc, optionType, sort, order]);

  const clickSort = (col) => {
    if (sort === col) setOrder(order === "desc" ? "asc" : "desc");
    else { setSort(col); setOrder(col === "name" ? "asc" : "desc"); }
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  const selectStyle = {
    background: PANEL, color: INK, border: BORDER, borderRadius: 6,
    padding: "8px 10px", fontSize: 13, fontFamily: "'Inter',sans-serif", maxWidth: 260,
  };

  const Th = ({ col, label, align = "right" }) => (
    <th onClick={() => clickSort(col)} style={{
      textAlign: align, padding: "10px 12px", cursor: "pointer",
      fontSize: 11, fontWeight: 600, letterSpacing: "0.04em", whiteSpace: "nowrap",
      userSelect: "none",
    }}>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4,
        color: sort === col ? GOLD : MUTE }}>
        {label}
        {sort === col && (order === "desc" ? <ArrowDown size={12} /> : <ArrowUp size={12} />)}
      </span>
    </th>
  );

  return (
    <div style={{ padding: "28px 28px 90px", maxWidth: 1360, margin: "0 auto" }}>
      <div style={{ marginBottom: 20 }}>
        <div className="mono" style={{ fontSize: 11, color: MUTE, letterSpacing: "0.08em", marginBottom: 6 }}>
          {data ? `${data.total.toLocaleString()} SCHEMES` : "…"} · ALL INDIAN MUTUAL FUNDS
        </div>
        <div className="serif" style={{ fontSize: 32, fontWeight: 500 }}>Scheme Explorer</div>
      </div>

      {/* controls */}
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 18, alignItems: "center" }}>
        <div style={{ position: "relative", flex: "1 1 280px", maxWidth: 420 }}>
          <Search size={15} color={MUTE} style={{ position: "absolute", left: 12, top: 11 }} />
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search fund or AMC…"
            style={{ ...selectStyle, width: "100%", maxWidth: "none", paddingLeft: 34, boxSizing: "border-box" }} />
        </div>
        <select value={category} onChange={e => setCategory(e.target.value)} style={selectStyle}>
          <option value="">All categories</option>
          {facets.categories.map(c => <option key={c.value} value={c.value}>{c.value} ({c.count})</option>)}
        </select>
        <select value={amc} onChange={e => setAmc(e.target.value)} style={selectStyle}>
          <option value="">All AMCs</option>
          {facets.amcs.map(a => <option key={a.value} value={a.value}>{a.value} ({a.count})</option>)}
        </select>
        <div style={{ display: "flex", border: BORDER, borderRadius: 6, overflow: "hidden" }}>
          {["Growth", "IDCW", ""].map(o => (
            <button key={o || "all"} onClick={() => setOptionType(o)} style={{
              background: optionType === o ? GOLD : PANEL,
              color: optionType === o ? BG : MUTE, border: "none",
              padding: "8px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer",
              fontFamily: "'Inter',sans-serif",
            }}>{o || "All"}</button>
          ))}
        </div>
      </div>

      {error && <div className="mono" style={{ color: RED, padding: "20px 0" }}>
        Couldn't load schemes: {error}. Is the backend running at {API_BASE}?
      </div>}

      {!data && !error && <div className="mono" style={{ color: MUTE, padding: "20px 0" }}>Loading…</div>}

      {data && (
        <>
          <div style={{ background: PANEL, border: BORDER, borderRadius: 8, overflow: "hidden" }}>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 860 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid rgba(237,234,226,0.12)" }}>
                    <th style={{ width: 40 }}></th>
                    <Th col="name" label="SCHEME" align="left" />
                    <th style={{ textAlign: "left", padding: "10px 12px", color: MUTE, fontSize: 11, fontWeight: 600, letterSpacing: "0.04em" }}>CATEGORY</th>
                    <Th col="nav" label="NAV" />
                    <Th col="1Y" label="1Y" />
                    <Th col="3Y" label="3Y" />
                    <Th col="5Y" label="5Y" />
                    <Th col="sharpe" label="SHARPE 3Y" />
                  </tr>
                </thead>
                <tbody>
                  {data.schemes.map(s => {
                    const checked = compareCodes.includes(s.scheme_code);
                    return (
                      <tr key={s.scheme_code} className="ledger-line"
                        style={{ cursor: "pointer" }}
                        onClick={() => onSelectScheme(s.scheme_code)}>
                        <td style={{ padding: "0 0 0 12px" }} onClick={e => e.stopPropagation()}>
                          <input type="checkbox" checked={checked}
                            onChange={() => toggleCompare(s.scheme_code)}
                            disabled={!checked && compareCodes.length >= 4}
                            style={{ accentColor: GOLD, cursor: "pointer" }} />
                        </td>
                        <td style={{ padding: "11px 12px", maxWidth: 340 }}>
                          <div style={{ fontSize: 13.5, fontWeight: 600, lineHeight: 1.3 }}>{s.name}</div>
                          <div className="mono" style={{ fontSize: 10.5, color: MUTE, marginTop: 2 }}>
                            {s.amc}{s.plan_type ? ` · ${s.plan_type}` : ""}
                          </div>
                        </td>
                        <td className="mono" style={{ padding: "11px 12px", fontSize: 11, color: MUTE }}>
                          {(s.category || "").replace(/^Equity Schemes? - /, "").replace(/^Debt Scheme - /, "")}
                        </td>
                        <td className="mono" style={{ padding: "11px 12px", textAlign: "right", fontSize: 13 }}>
                          {s.nav != null ? `₹${s.nav}` : "—"}
                        </td>
                        <td className="mono" style={{ padding: "11px 12px", textAlign: "right", fontSize: 13, fontWeight: 600, color: retColor(s.ret_1y) }}>{fmtPct(s.ret_1y)}</td>
                        <td className="mono" style={{ padding: "11px 12px", textAlign: "right", fontSize: 13, fontWeight: 600, color: retColor(s.ret_3y) }}>{fmtPct(s.ret_3y)}</td>
                        <td className="mono" style={{ padding: "11px 12px", textAlign: "right", fontSize: 13, fontWeight: 600, color: retColor(s.ret_5y) }}>{fmtPct(s.ret_5y)}</td>
                        <td className="mono" style={{ padding: "11px 12px", textAlign: "right", fontSize: 13, color: INK }}>{fmtNum(s.sharpe_3y)}</td>
                      </tr>
                    );
                  })}
                  {data.schemes.length === 0 && (
                    <tr><td colSpan={8} className="mono" style={{ padding: 30, textAlign: "center", color: MUTE }}>
                      No schemes match these filters.
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* pagination */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 16 }}>
            <span className="mono" style={{ fontSize: 12, color: MUTE }}>
              Page {data.page} of {totalPages.toLocaleString()}
            </span>
            <div style={{ display: "flex", gap: 8 }}>
              <button disabled={page <= 1} onClick={() => setPage(page - 1)} style={pagerBtn(page <= 1)}>Prev</button>
              <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} style={pagerBtn(page >= totalPages)}>Next</button>
            </div>
          </div>
        </>
      )}

      {/* compare action bar */}
      {compareCodes.length > 0 && (
        <div style={{
          position: "fixed", bottom: 20, left: "50%", transform: "translateX(-50%)",
          background: GOLD, color: BG, borderRadius: 30, padding: "10px 18px",
          display: "flex", alignItems: "center", gap: 14, boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
          fontFamily: "'Inter',sans-serif", zIndex: 10,
        }}>
          <span style={{ fontSize: 13, fontWeight: 700 }}>{compareCodes.length} selected</span>
          <button onClick={onOpenCompare} disabled={compareCodes.length < 2} style={{
            background: BG, color: GOLD, border: "none", borderRadius: 20, padding: "6px 14px",
            fontSize: 12.5, fontWeight: 700, cursor: compareCodes.length < 2 ? "not-allowed" : "pointer",
            opacity: compareCodes.length < 2 ? 0.5 : 1, display: "flex", alignItems: "center", gap: 6,
          }}>
            <GitCompare size={14} /> Compare
          </button>
          <button onClick={() => compareCodes.slice().forEach(toggleCompare)} style={{
            background: "none", border: "none", cursor: "pointer", display: "flex", color: BG,
          }}><X size={16} /></button>
        </div>
      )}
    </div>
  );
}

function pagerBtn(disabled) {
  return {
    background: PANEL, color: disabled ? MUTE : INK, border: BORDER, borderRadius: 6,
    padding: "7px 16px", fontSize: 12.5, fontWeight: 600,
    cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.5 : 1,
    fontFamily: "'Inter',sans-serif",
  };
}

// ---------------------------------------------------------------------------
// Detail
// ---------------------------------------------------------------------------
function SchemeDetail({ code, onBack }) {
  const [d, setD] = useState(null);
  const [error, setError] = useState(null);
  const [range, setRange] = useState("3Y");
  const [nav, setNav] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/schemes/${code}`)
      .then(r => { if (!r.ok) throw new Error("scheme not found"); return r.json(); })
      .then(setD).catch(e => setError(e.message));
  }, [code]);

  useEffect(() => {
    setNav(null);
    fetch(`${API_BASE}/api/schemes/${code}/nav?range=${range}`)
      .then(r => r.json()).then(setNav).catch(() => {});
  }, [code, range]);

  if (error) return <div style={{ padding: 40, color: RED }} className="mono">{error}</div>;
  if (!d) return <div style={{ padding: 40, color: MUTE }} className="mono">Loading…</div>;

  const risk1y = d.risk.find(r => r.period === "1Y") || {};
  const risk3y = d.risk.find(r => r.period === "3Y") || {};

  return (
    <div style={{ padding: "28px 28px 60px", maxWidth: 1360, margin: "0 auto" }}>
      <button onClick={onBack} style={backBtn}><ArrowLeft size={15} /> Back to explorer</button>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 24, flexWrap: "wrap", gap: 16 }}>
        <div>
          <div className="mono" style={{ fontSize: 11, color: MUTE, letterSpacing: "0.08em", marginBottom: 6 }}>
            {(d.category || "").toUpperCase()} · {d.amc}
            {d.plan_type ? ` · ${d.plan_type}` : ""}{d.option_type ? ` · ${d.option_type}` : ""}
          </div>
          <div className="serif" style={{ fontSize: 30, fontWeight: 500, maxWidth: 720 }}>{d.name}</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="mono" style={{ fontSize: 12, color: MUTE }}>NAV{d.nav_date ? ` · ${d.nav_date}` : ""}</div>
          <div className="mono" style={{ fontSize: 26, fontWeight: 600 }}>{d.nav != null ? `₹${d.nav}` : "—"}</div>
        </div>
      </div>

      {/* NAV chart */}
      <div style={{ background: PANEL, border: BORDER, borderRadius: 8, padding: 20, marginBottom: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <span style={sectionLabel}>NAV HISTORY</span>
          <div style={{ display: "flex", gap: 6 }}>
            {["1Y", "3Y", "5Y", "max"].map(r => (
              <button key={r} onClick={() => setRange(r)} style={{
                background: range === r ? GOLD : "transparent", color: range === r ? BG : MUTE,
                border: BORDER, borderRadius: 6, padding: "4px 10px", fontSize: 11.5, fontWeight: 600,
                cursor: "pointer", fontFamily: "'Inter',sans-serif",
              }}>{r === "max" ? "Max" : r}</button>
            ))}
          </div>
        </div>
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={nav ? nav.points : []}>
            <CartesianGrid stroke="rgba(237,234,226,0.06)" vertical={false} />
            <XAxis dataKey="date" stroke={MUTE} fontSize={10} tickLine={false} axisLine={false}
              minTickGap={60} tickFormatter={v => v.slice(0, 7)} />
            <YAxis stroke={MUTE} fontSize={10} tickLine={false} axisLine={false} width={48}
              domain={["auto", "auto"]} />
            <Tooltip contentStyle={{ background: BG, border: "1px solid rgba(237,234,226,0.15)", borderRadius: 6, fontSize: 11 }}
              labelStyle={{ color: MUTE }} formatter={v => [`₹${v}`, "NAV"]} />
            <Line type="monotone" dataKey="nav" stroke={GOLD} strokeWidth={1.6} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 20 }}>
        {/* returns */}
        <div style={{ background: PANEL, border: BORDER, borderRadius: 8, padding: 20 }}>
          <span style={sectionLabel}>RETURNS vs BENCHMARK vs CATEGORY</span>
          {d.benchmark ? (
            <div className="mono" style={{ fontSize: 10.5, color: MUTE, marginTop: 4 }}>
              Benchmark proxy: {d.benchmark.proxy_name}
              {d.benchmark.note ? ` — ${d.benchmark.note}` : ""}
            </div>
          ) : (
            <div className="mono" style={{ fontSize: 10.5, color: MUTE, marginTop: 4 }}>
              No benchmark proxy for this category (shown as —).
            </div>
          )}
          <div style={{ marginTop: 14 }}>
            <div className="mono" style={{ display: "grid", gridTemplateColumns: "60px 1fr 1fr 1fr", fontSize: 10.5, color: MUTE, paddingBottom: 6 }}>
              <span></span><span style={{ textAlign: "right" }}>FUND</span>
              <span style={{ textAlign: "right" }}>BENCH</span><span style={{ textAlign: "right" }}>CATEGORY</span>
            </div>
            {PERIODS.map(p => {
              const r = d.returns.find(x => x.period === p);
              return (
                <div key={p} className="ledger-line mono" style={{ display: "grid", gridTemplateColumns: "60px 1fr 1fr 1fr", padding: "9px 0", fontSize: 13 }}>
                  <span style={{ color: MUTE }}>{p}</span>
                  <span style={{ textAlign: "right", fontWeight: 600, color: retColor(r ? r.fund_return : null) }}>{fmtPct(r ? r.fund_return : null)}</span>
                  <span style={{ textAlign: "right", color: MUTE }}>{fmtPct(r ? r.benchmark_return : null)}</span>
                  <span style={{ textAlign: "right", color: MUTE }}>{fmtPct(r ? r.category_avg_return : null)}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* risk */}
        <div style={{ background: PANEL, border: BORDER, borderRadius: 8, padding: 20 }}>
          <span style={sectionLabel}>RISK METRICS</span>
          <div style={{ marginTop: 14 }}>
            <div className="mono" style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr 1fr", fontSize: 10.5, color: MUTE, paddingBottom: 6 }}>
              <span></span><span style={{ textAlign: "right" }}>1Y</span><span style={{ textAlign: "right" }}>3Y</span>
            </div>
            {[
              ["Volatility", "stdev", "%"], ["Sharpe", "sharpe", ""],
              ["Beta", "beta", ""], ["Alpha", "alpha", "%"], ["Max drawdown", "max_drawdown", "%"],
            ].map(([label, key, unit]) => (
              <div key={key} className="ledger-line mono" style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr 1fr", padding: "9px 0", fontSize: 13 }}>
                <span style={{ color: MUTE }}>{label}</span>
                <span style={{ textAlign: "right", color: INK }}>{risk1y[key] != null ? `${risk1y[key]}${unit}` : "—"}</span>
                <span style={{ textAlign: "right", color: INK }}>{risk3y[key] != null ? `${risk3y[key]}${unit}` : "—"}</span>
              </div>
            ))}
          </div>
          <div className="mono" style={{ fontSize: 10, color: MUTE, marginTop: 12, lineHeight: 1.5 }}>
            Sharpe uses a 6.5% risk-free rate. Beta/alpha vs the category benchmark proxy;
            "—" where history is too short or no proxy exists.
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Compare
// ---------------------------------------------------------------------------
function Compare({ codes, onBack }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/schemes/compare?codes=${codes.join(",")}`)
      .then(r => { if (!r.ok) throw new Error(`API ${r.status}`); return r.json(); })
      .then(setData).catch(e => setError(e.message));
  }, [codes]);

  if (error) return <div style={{ padding: 40, color: RED }} className="mono">{error}</div>;
  if (!data) return <div style={{ padding: 40, color: MUTE }} className="mono">Loading…</div>;

  const schemes = data.schemes;
  const getRet = (s, p) => { const x = s.returns.find(y => y.period === p); return x ? x.fund_return : null; };
  const getRisk = (s, p, k) => { const x = s.risk.find(y => y.period === p); return x ? x[k] : null; };

  // index of the best value in a row (higherBetter picks max, else min)
  const bestIdx = (vals, higherBetter) => {
    let bi = -1, bv = null;
    vals.forEach((v, i) => {
      if (v == null) return;
      if (bv == null || (higherBetter ? v > bv : v < bv)) { bv = v; bi = i; }
    });
    return bi;
  };

  const rows = [
    ...PERIODS.map(p => ({ label: `${p} return`, vals: schemes.map(s => getRet(s, p)), unit: "%", higher: true, color: true })),
    { label: "Sharpe (3Y)", vals: schemes.map(s => getRisk(s, "3Y", "sharpe")), unit: "", higher: true },
    { label: "Volatility (3Y)", vals: schemes.map(s => getRisk(s, "3Y", "stdev")), unit: "%", higher: false },
    { label: "Max drawdown (3Y)", vals: schemes.map(s => getRisk(s, "3Y", "max_drawdown")), unit: "%", higher: true },
  ];

  return (
    <div style={{ padding: "28px 28px 60px", maxWidth: 1360, margin: "0 auto" }}>
      <button onClick={onBack} style={backBtn}><ArrowLeft size={15} /> Back to explorer</button>
      <div className="serif" style={{ fontSize: 30, fontWeight: 500, marginBottom: 20 }}>Compare {schemes.length} schemes</div>

      <div style={{ background: PANEL, border: BORDER, borderRadius: 8, overflow: "hidden" }}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 640 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid rgba(237,234,226,0.12)" }}>
                <th style={{ textAlign: "left", padding: "12px", color: MUTE, fontSize: 11, fontWeight: 600 }}>METRIC</th>
                {schemes.map(s => (
                  <th key={s.scheme_code} style={{ textAlign: "right", padding: "12px", fontSize: 12.5, fontWeight: 600, color: INK, maxWidth: 200 }}>
                    {s.name}
                    <div className="mono" style={{ fontSize: 10, color: MUTE, fontWeight: 400, marginTop: 2 }}>
                      {(s.category || "").replace(/^Equity Schemes? - /, "")}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => {
                const winner = bestIdx(row.vals, row.higher);
                return (
                  <tr key={ri} className="ledger-line">
                    <td className="mono" style={{ padding: "10px 12px", fontSize: 12.5, color: MUTE }}>{row.label}</td>
                    {row.vals.map((v, i) => (
                      <td key={i} className="mono" style={{
                        padding: "10px 12px", textAlign: "right", fontSize: 13,
                        fontWeight: i === winner ? 700 : 500,
                        color: row.color ? retColor(v) : (i === winner ? GOLD : INK),
                        background: i === winner ? "rgba(201,162,39,0.08)" : "transparent",
                      }}>
                        {v == null ? "—" : `${v}${row.unit}`}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
      <div className="mono" style={{ fontSize: 10.5, color: MUTE, marginTop: 12 }}>
        Highlighted = best in row (for drawdown, closest to zero). "—" where data is unavailable.
      </div>
    </div>
  );
}

const sectionLabel = { fontSize: 13, fontWeight: 600, color: MUTE, letterSpacing: "0.04em" };
const backBtn = {
  background: "none", border: "none", color: MUTE, cursor: "pointer",
  display: "flex", alignItems: "center", gap: 6, marginBottom: 20, fontSize: 13,
  fontFamily: "'Inter',sans-serif",
};

// ---------------------------------------------------------------------------
// Root
// ---------------------------------------------------------------------------
export default function App() {
  const [view, setView] = useState({ page: "explorer" });
  const [compareCodes, setCompareCodes] = useState([]);

  const toggleCompare = (code) => setCompareCodes(prev =>
    prev.includes(code) ? prev.filter(c => c !== code) : prev.length >= 4 ? prev : [...prev, code]);

  return (
    <div style={{ background: BG, color: INK, minHeight: "100vh", fontFamily: "'Inter', sans-serif" }}>
      <style>{fonts}</style>

      <div style={{
        borderBottom: "1px solid rgba(237,234,226,0.1)", background: PANEL,
        padding: "14px 28px", display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}
          onClick={() => setView({ page: "explorer" })}>
          <div style={{
            width: 28, height: 28, borderRadius: 4, background: "linear-gradient(135deg,#C9A227,#8a6f1a)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontFamily: "'Newsreader', serif", fontWeight: 600, fontSize: 15, color: BG,
          }}>₹</div>
          <span className="serif" style={{ fontSize: 19, fontWeight: 500 }}>
            Money<span style={{ color: GOLD }}>Mint</span>
          </span>
        </div>
        <div className="mono" style={{ fontSize: 12, color: MUTE }}>Personal MF Analytics</div>
      </div>

      {view.page === "explorer" && (
        <Explorer
          onSelectScheme={code => setView({ page: "detail", code })}
          compareCodes={compareCodes}
          toggleCompare={toggleCompare}
          onOpenCompare={() => setView({ page: "compare" })}
        />
      )}
      {view.page === "detail" && (
        <SchemeDetail code={view.code} onBack={() => setView({ page: "explorer" })} />
      )}
      {view.page === "compare" && (
        <Compare codes={compareCodes} onBack={() => setView({ page: "explorer" })} />
      )}
    </div>
  );
}
