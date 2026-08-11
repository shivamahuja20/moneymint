import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  LineChart, Line, AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import {
  Search, ArrowLeft, ArrowUp, ArrowDown, X, GitCompare, Calculator, AlertTriangle,
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
function pctColor(v) { return v == null ? MUTE : v >= 67 ? GREEN : v >= 33 ? GOLD : RED; }
function fmtINR(v) {
  if (v == null) return "—";
  return "₹" + Math.round(v).toLocaleString("en-IN");
}
function fmtAUM(v) { return v == null ? "—" : fmtINR(v) + " Cr"; }

// A small labelled stat (used for the real TER / AUM facts on the detail page).
function Fact({ label, value, sub }) {
  return (
    <div style={{ minWidth: 130 }}>
      <div className="mono" style={{ fontSize: 10, color: MUTE, letterSpacing: "0.08em", marginBottom: 4 }}>{label}</div>
      <div className="mono" style={{ fontSize: 19, fontWeight: 600, color: INK }}>{value}</div>
      {sub ? <div className="mono" style={{ fontSize: 10, color: MUTE, marginTop: 2 }}>{sub}</div> : null}
    </div>
  );
}

// Honest label for schemes the data-quality guard flagged. These are hidden from
// the explorer but still reachable by direct link, so the detail page must say why.
function dataQualityNote(dq, navDate) {
  if (dq === "stale")
    return {
      label: "Stale — likely dormant or wound-up",
      text: `The most recent NAV is from ${navDate || "an old date"}. This scheme has stopped `
        + "reporting fresh NAVs, so it's excluded from the explorer and rankings. The figures "
        + "below are historical and may not reflect anything current.",
    };
  if (dq === "discontinuity")
    return {
      label: "NAV discontinuity — some metrics withheld",
      text: "This scheme's NAV history has a large single-day jump with no economic meaning "
        + "(typically a segregated-portfolio / side-pocket event or a data restatement). "
        + "Returns and risk over any period spanning that jump are omitted rather than shown "
        + "as misleading numbers, and the scheme is excluded from the explorer.",
    };
  return null;
}

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
                    <Th col="aum" label="AUM (Cr)" />
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
                        <td className="mono" style={{ padding: "11px 12px", textAlign: "right", fontSize: 13, fontWeight: 600, color: retColor(s.ret_3y) }}>
                          <div>{fmtPct(s.ret_3y)}</div>
                          {s.percentile_3y != null && (
                            <div style={{ fontSize: 9.5, fontWeight: 600, color: pctColor(s.percentile_3y), marginTop: 2 }}>
                              top {Math.max(1, 100 - Math.round(s.percentile_3y))}%
                            </div>
                          )}
                        </td>
                        <td className="mono" style={{ padding: "11px 12px", textAlign: "right", fontSize: 13, fontWeight: 600, color: retColor(s.ret_5y) }}>{fmtPct(s.ret_5y)}</td>
                        <td className="mono" style={{ padding: "11px 12px", textAlign: "right", fontSize: 13, color: INK }}>{fmtNum(s.sharpe_3y)}</td>
                        <td className="mono" style={{ padding: "11px 12px", textAlign: "right", fontSize: 13, color: s.aaum_cr != null ? INK : MUTE }}>
                          {s.aaum_cr != null ? Math.round(s.aaum_cr).toLocaleString("en-IN") : "—"}
                        </td>
                      </tr>
                    );
                  })}
                  {data.schemes.length === 0 && (
                    <tr><td colSpan={9} className="mono" style={{ padding: 30, textAlign: "center", color: MUTE }}>
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
  const [holdings, setHoldings] = useState(null);

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

  useEffect(() => {
    setHoldings(null);
    fetch(`${API_BASE}/api/schemes/${code}/holdings?limit=10`)
      .then(r => r.json()).then(setHoldings).catch(() => {});
  }, [code]);

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

      {/* data-quality banner — only shown for flagged (stale / discontinuity) schemes */}
      {(() => {
        const note = dataQualityNote(d.data_quality, d.nav_date);
        if (!note) return null;
        return (
          <div style={{
            background: "rgba(198,82,75,0.08)", border: "1px solid rgba(198,82,75,0.4)",
            borderRadius: 8, padding: "13px 16px", marginBottom: 20,
            display: "flex", gap: 12, alignItems: "flex-start",
          }}>
            <AlertTriangle size={17} color={RED} style={{ marginTop: 1, flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: 12.5, fontWeight: 700, color: RED, marginBottom: 3 }}>{note.label}</div>
              <div className="mono" style={{ fontSize: 11.5, color: INK, lineHeight: 1.55 }}>{note.text}</div>
            </div>
          </div>
        );
      })()}

      {/* fund facts: real expense ratio + fund size from AMFI (null => "not disclosed") */}
      <div style={{ display: "flex", gap: 44, flexWrap: "wrap", background: PANEL, border: BORDER, borderRadius: 8, padding: "16px 20px", marginBottom: 20 }}>
        <Fact label="EXPENSE RATIO (TER)"
          value={d.ter != null ? `${d.ter}%` : "—"}
          sub={d.ter != null ? `AMFI · as of ${d.ter_as_of}` : "not disclosed"} />
        <Fact label="FUND SIZE (AVG AUM)"
          value={fmtAUM(d.aaum_cr)}
          sub={d.aaum_cr != null ? `AMFI · as of ${d.aaum_as_of}` : "not disclosed"} />
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

          {/* category rank */}
          <div style={{ marginTop: 22, borderTop: "1px solid rgba(237,234,226,0.08)", paddingTop: 16 }}>
            <span style={sectionLabel}>CATEGORY RANK</span>
            <div className="mono" style={{ fontSize: 10.5, color: MUTE, marginTop: 4 }}>
              Standing among usable {(d.category || "").replace(/^Equity Schemes? - /, "").replace(/^Debt Scheme - /, "")} peers.
            </div>
            <div style={{ marginTop: 12 }}>
              {PERIODS.map(p => {
                const rk = d.rankings.find(x => x.period === p);
                const top = rk && rk.percentile != null ? Math.max(1, 100 - Math.round(rk.percentile)) : null;
                return (
                  <div key={p} className="ledger-line mono" style={{ display: "grid", gridTemplateColumns: "60px 1fr 1fr", padding: "9px 0", fontSize: 13 }}>
                    <span style={{ color: MUTE }}>{p}</span>
                    <span style={{ textAlign: "right", color: INK }}>
                      {rk ? `#${rk.rank_in_category} of ${rk.category_size}` : "—"}
                    </span>
                    <span style={{ textAlign: "right", fontWeight: 600, color: pctColor(rk ? rk.percentile : null) }}>
                      {top != null ? `top ${top}%` : "—"}
                    </span>
                  </div>
                );
              })}
            </div>
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

      <RollingReturns code={code} />

      <HoldingsPanels holdings={holdings} />

      <Calculators code={code} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Rolling returns — the return from EVERY start date, not just two dates.
// ---------------------------------------------------------------------------
const ROLLING_WINDOWS = ["1Y", "3Y", "5Y", "7Y"];

function RollingReturns({ code }) {
  const [window_, setWindow] = useState("3Y");
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    setD(null); setErr(null);
    fetch(`${API_BASE}/api/schemes/rolling?codes=${code}&window=${window_}`)
      .then(r => { if (!r.ok) throw new Error(`API ${r.status}`); return r.json(); })
      .then(setD).catch(e => setErr(e.message));
  }, [code, window_]);

  const fund = d && d.funds && d.funds[0];
  const s = fund && fund.stats;

  return (
    <div style={{ background: PANEL, border: BORDER, borderRadius: 8, padding: 20, marginTop: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
        <div>
          <span style={sectionLabel}>ROLLING RETURNS</span>
          <div className="mono" style={{ fontSize: 10.5, color: MUTE, marginTop: 4, maxWidth: 620, lineHeight: 1.5 }}>
            The {window_} return starting from <em>every</em> day in this fund's history — not just
            the one window ending today. Shows the range of outcomes a real investor could have had.
          </div>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {ROLLING_WINDOWS.map(w => (
            <button key={w} onClick={() => setWindow(w)} style={{
              background: window_ === w ? GOLD : "transparent", color: window_ === w ? BG : MUTE,
              border: BORDER, borderRadius: 6, padding: "4px 10px", fontSize: 11.5, fontWeight: 600,
              cursor: "pointer", fontFamily: "'Inter',sans-serif",
            }}>{w}</button>
          ))}
        </div>
      </div>

      {err && <div className="mono" style={{ fontSize: 12, color: RED, marginTop: 12 }}>Couldn't load: {err}</div>}
      {!d && !err && <div className="mono" style={{ fontSize: 12, color: MUTE, marginTop: 12 }}>Loading…</div>}

      {d && !s && (
        <div className="mono" style={{ fontSize: 12.5, color: MUTE, marginTop: 12 }}>
          Not enough history for a {window_} rolling analysis of this fund.
        </div>
      )}

      {s && (
        <>
          <div style={{ display: "flex", gap: 34, flexWrap: "wrap", marginTop: 16, marginBottom: 4 }}>
            <Fact label="WORST" value={fmtPct(s.min)} sub={`of ${s.windows.toLocaleString()} windows`} />
            <Fact label="MEDIAN" value={fmtPct(s.median)} sub="typical outcome" />
            <Fact label="BEST" value={fmtPct(s.max)} />
            <Fact label="LOST MONEY" value={`${s.pct_negative}%`} sub="of windows" />
            <Fact label="ABOVE 12%" value={`${s.pct_above_12}%`} sub="of windows" />
            {fund.beat_benchmark_pct != null && (
              <Fact label="BEAT BENCHMARK" value={`${fund.beat_benchmark_pct}%`}
                sub={d.benchmark ? "of overlapping windows" : null} />
            )}
          </div>

          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={fund.points}>
              <defs>
                <linearGradient id="rollFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={GOLD} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={GOLD} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(237,234,226,0.06)" vertical={false} />
              <XAxis dataKey="date" stroke={MUTE} fontSize={10} tickLine={false} axisLine={false}
                minTickGap={60} tickFormatter={v => v.slice(0, 7)} />
              <YAxis stroke={MUTE} fontSize={10} tickLine={false} axisLine={false} width={44}
                tickFormatter={v => `${v}%`} />
              <Tooltip contentStyle={{ background: BG, border: "1px solid rgba(237,234,226,0.15)", borderRadius: 6, fontSize: 11 }}
                labelStyle={{ color: MUTE }}
                labelFormatter={v => `${window_} starting ${v}`}
                formatter={v => [`${v}%`, d.annualised ? "annualised" : "absolute"]} />
              <Area type="monotone" dataKey="ret" stroke={GOLD} strokeWidth={1.4} fill="url(#rollFill)" />
            </AreaChart>
          </ResponsiveContainer>

          <div className="mono" style={{ fontSize: 10, color: MUTE, marginTop: 8, lineHeight: 1.5 }}>
            {d.annualised ? "Annualised (CAGR) per window." : "Absolute return per window."}
            {d.benchmark ? ` Benchmark: ${d.benchmark.proxy_name}.` : " No benchmark proxy for this category."}
            {" "}Windows spanning a NAV discontinuity are excluded.
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Holdings + sector allocation (Phase 8)
// ---------------------------------------------------------------------------
function HoldingsPanels({ holdings }) {
  if (holdings == null) return null;  // still loading
  const has = holdings.holdings && holdings.holdings.length > 0;
  if (!has) {
    return (
      <div style={{ background: PANEL, border: BORDER, borderRadius: 8, padding: 20, marginTop: 20 }}>
        <span style={sectionLabel}>PORTFOLIO HOLDINGS</span>
        <div className="mono" style={{ fontSize: 12.5, color: MUTE, marginTop: 10 }}>
          Portfolio holdings not yet available for this scheme.
        </div>
      </div>
    );
  }
  const maxPct = Math.max(...holdings.sector_allocation.map(s => s.pct_of_aum), 1);
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 20, marginTop: 20 }}>
      {/* top holdings */}
      <div style={{ background: PANEL, border: BORDER, borderRadius: 8, padding: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <span style={sectionLabel}>TOP HOLDINGS</span>
          <span className="mono" style={{ fontSize: 10.5, color: MUTE }}>as of {holdings.as_of_date}</span>
        </div>
        <div style={{ marginTop: 12 }}>
          {holdings.holdings.map((h, i) => (
            <div key={i} className="ledger-line mono" style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 10, padding: "8px 0", fontSize: 13 }}>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {h.instrument_name}
                <span style={{ color: MUTE, fontSize: 10.5 }}> · {h.sector}</span>
              </span>
              <span style={{ fontWeight: 600, color: GOLD }}>{h.pct_of_aum}%</span>
            </div>
          ))}
        </div>
      </div>

      {/* sector allocation */}
      <div style={{ background: PANEL, border: BORDER, borderRadius: 8, padding: 20 }}>
        <span style={sectionLabel}>SECTOR ALLOCATION</span>
        <div style={{ marginTop: 12 }}>
          {holdings.sector_allocation.slice(0, 10).map((s, i) => (
            <div key={i} className="mono" style={{ padding: "5px 0", fontSize: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 200 }}>{s.sector}</span>
                <span style={{ color: MUTE }}>{s.pct_of_aum.toFixed(1)}%</span>
              </div>
              <div style={{ height: 4, background: "rgba(237,234,226,0.08)", borderRadius: 2 }}>
                <div style={{ height: 4, width: `${(s.pct_of_aum / maxPct) * 100}%`, background: GREEN, borderRadius: 2 }} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Calculators (backtest over real NAVs + forward projection), on the detail page
// ---------------------------------------------------------------------------
const calcInput = {
  background: BG, color: INK, border: BORDER, borderRadius: 6,
  padding: "8px 10px", fontSize: 13, fontFamily: "'IBM Plex Mono', monospace",
  width: "100%", boxSizing: "border-box",
};
const tab = (active) => ({
  background: active ? GOLD : PANEL, color: active ? BG : MUTE, border: "none",
  padding: "7px 14px", fontSize: 12.5, fontWeight: 600, cursor: "pointer",
  fontFamily: "'Inter',sans-serif",
});

function Field({ label, children }) {
  return (
    <label style={{ display: "block" }}>
      <div className="mono" style={{ fontSize: 10, color: MUTE, marginBottom: 4 }}>{label}</div>
      {children}
    </label>
  );
}

function Tile({ label, value, color = INK }) {
  return (
    <div style={{ background: BG, border: BORDER, borderRadius: 6, padding: "12px 14px" }}>
      <div className="mono" style={{ fontSize: 10, color: MUTE }}>{label}</div>
      <div className="mono" style={{ fontSize: 18, fontWeight: 700, color, marginTop: 3 }}>{value}</div>
    </div>
  );
}

function Calculators({ code }) {
  const [tab_, setTab] = useState("backtest");
  return (
    <div style={{ background: PANEL, border: BORDER, borderRadius: 8, padding: 20, marginTop: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <span style={{ ...sectionLabel, display: "flex", alignItems: "center", gap: 7 }}>
          <Calculator size={14} /> CALCULATORS
        </span>
        <div style={{ display: "flex", border: BORDER, borderRadius: 6, overflow: "hidden" }}>
          <button onClick={() => setTab("backtest")} style={tab(tab_ === "backtest")}>Backtest (real)</button>
          <button onClick={() => setTab("project")} style={tab(tab_ === "project")}>Project (assumed)</button>
        </div>
      </div>
      {tab_ === "backtest" ? <Backtest code={code} /> : <Project code={code} />}
    </div>
  );
}

function Backtest({ code }) {
  const [mode, setMode] = useState("sip");
  const [amount, setAmount] = useState(5000);
  const [start, setStart] = useState(() => {
    const d = new Date(); d.setFullYear(d.getFullYear() - 5);
    return d.toISOString().slice(0, 10);
  });
  const [taxClass, setTaxClass] = useState("");   // "" = use server's classification
  const [rate, setRate] = useState(30);
  const [res, setRes] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const run = () => {
    setLoading(true); setError(null);
    const p = new URLSearchParams({ mode, amount, start, marginal_rate: rate });
    if (taxClass) p.set("tax_class", taxClass);
    fetch(`${API_BASE}/api/schemes/${code}/backtest?${p}`)
      .then(async r => { const j = await r.json(); if (!r.ok) throw new Error(j.detail || `API ${r.status}`); return j; })
      .then(d => { setRes(d); setError(null); })
      .catch(e => { setError(e.message); setRes(null); })
      .finally(() => setLoading(false));
  };

  return (
    <div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 16 }}>
        <div style={{ display: "flex", border: BORDER, borderRadius: 6, overflow: "hidden", height: 36 }}>
          {["sip", "lumpsum"].map(m => (
            <button key={m} onClick={() => setMode(m)} style={tab(mode === m)}>{m === "sip" ? "SIP" : "Lumpsum"}</button>
          ))}
        </div>
        <div style={{ width: 150 }}><Field label={mode === "sip" ? "MONTHLY AMOUNT (₹)" : "AMOUNT (₹)"}>
          <input type="number" value={amount} onChange={e => setAmount(+e.target.value)} style={calcInput} />
        </Field></div>
        <div style={{ width: 160 }}><Field label="START DATE">
          <input type="date" value={start} onChange={e => setStart(e.target.value)} style={calcInput} />
        </Field></div>
        <button onClick={run} disabled={loading} style={{
          background: GOLD, color: BG, border: "none", borderRadius: 6, padding: "9px 20px",
          fontSize: 13, fontWeight: 700, cursor: "pointer", fontFamily: "'Inter',sans-serif", height: 36,
        }}>{loading ? "…" : "Run"}</button>
      </div>

      {error && <div className="mono" style={{ color: RED, fontSize: 12.5, padding: "8px 0" }}>{error}</div>}

      {res && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 10, marginBottom: 16 }}>
            <Tile label="INVESTED" value={fmtINR(res.invested)} />
            <Tile label="VALUE TODAY" value={fmtINR(res.current_value)} color={GOLD} />
            <Tile label="GAIN" value={fmtINR(res.gain)} color={retColor(res.gain)} />
            <Tile label={mode === "sip" ? "XIRR" : "CAGR"} value={`${mode === "sip" ? res.xirr_pct : res.cagr_pct}%`} color={GREEN} />
          </div>

          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={res.series}>
              <defs>
                <linearGradient id="gv" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={GOLD} stopOpacity={0.4} />
                  <stop offset="100%" stopColor={GOLD} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(237,234,226,0.06)" vertical={false} />
              <XAxis dataKey="date" stroke={MUTE} fontSize={10} tickLine={false} axisLine={false}
                minTickGap={60} tickFormatter={v => v.slice(0, 7)} />
              <YAxis stroke={MUTE} fontSize={10} tickLine={false} axisLine={false} width={54}
                tickFormatter={v => `${Math.round(v / 1000)}k`} />
              <Tooltip contentStyle={{ background: BG, border: "1px solid rgba(237,234,226,0.15)", borderRadius: 6, fontSize: 11 }}
                labelStyle={{ color: MUTE }} formatter={(v, n) => [fmtINR(v), n === "value" ? "Value" : "Invested"]} />
              <Area type="monotone" dataKey="invested" stroke={MUTE} strokeWidth={1} fill="none" strokeDasharray="3 3" />
              <Area type="monotone" dataKey="value" stroke={GOLD} strokeWidth={1.6} fill="url(#gv)" />
            </AreaChart>
          </ResponsiveContainer>

          {/* taxation */}
          <div style={{ borderTop: "1px solid rgba(237,234,226,0.08)", marginTop: 14, paddingTop: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
              <span style={sectionLabel}>ESTIMATED TAX IF REDEEMED TODAY</span>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <div style={{ display: "flex", border: BORDER, borderRadius: 6, overflow: "hidden" }}>
                  {[["", "Auto"], ["equity", "Equity"], ["non_equity", "Non-equity"]].map(([v, l]) => (
                    <button key={v || "auto"} onClick={() => setTaxClass(v)} style={{ ...tab(taxClass === v), padding: "5px 10px", fontSize: 11 }}>{l}</button>
                  ))}
                </div>
                {(taxClass === "non_equity" || res.tax.tax_class === "non_equity") && (
                  <input type="number" value={rate} onChange={e => setRate(+e.target.value)}
                    title="Slab rate %" style={{ ...calcInput, width: 70 }} />
                )}
                <button onClick={run} style={{ ...tab(false), border: BORDER, borderRadius: 6, fontSize: 11, padding: "5px 10px" }}>Apply</button>
              </div>
            </div>
            <div className="mono" style={{ display: "flex", gap: 24, marginTop: 10, fontSize: 13 }}>
              <span>Tax: <b style={{ color: RED }}>{fmtINR(res.tax.tax)}</b></span>
              <span style={{ color: MUTE }}>{res.tax.gain_type} · {res.tax.tax_class} · {res.tax.effective_rate_pct}% of gain</span>
            </div>
            <div className="mono" style={{ fontSize: 10, color: MUTE, marginTop: 8, lineHeight: 1.5 }}>
              {res.tax.assumptions.join(" ")}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Project({ code }) {
  const [mode, setMode] = useState("sip");
  const [amount, setAmount] = useState(10000);
  const [years, setYears] = useState(10);
  const [rate, setRate] = useState(12);
  const [target, setTarget] = useState(10000000);
  const [corpus, setCorpus] = useState(2000000);
  const [withdrawal, setWithdrawal] = useState(15000);
  const [res, setRes] = useState(null);
  const [error, setError] = useState(null);

  const run = () => {
    const p = new URLSearchParams({ mode, annual_rate: rate });
    if (mode === "sip" || mode === "lumpsum") { p.set("amount", amount); p.set("years", years); }
    if (mode === "goal") { p.set("target", target); p.set("years", years); }
    if (mode === "swp") { p.set("corpus", corpus); p.set("monthly_withdrawal", withdrawal); }
    fetch(`${API_BASE}/api/calc/project?${p}`)
      .then(async r => { const j = await r.json(); if (!r.ok) throw new Error(j.detail || `API ${r.status}`); return j; })
      .then(d => { setRes(d); setError(null); })
      .catch(e => { setError(e.message); setRes(null); });
  };

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
        {[["sip", "SIP"], ["lumpsum", "Lumpsum"], ["swp", "SWP"], ["goal", "Goal"]].map(([m, l]) => (
          <button key={m} onClick={() => { setMode(m); setRes(null); }} style={{ ...tab(mode === m), border: BORDER, borderRadius: 6 }}>{l}</button>
        ))}
      </div>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 14 }}>
        {(mode === "sip" || mode === "lumpsum") && (
          <div style={{ width: 150 }}><Field label={mode === "sip" ? "MONTHLY (₹)" : "AMOUNT (₹)"}>
            <input type="number" value={amount} onChange={e => setAmount(+e.target.value)} style={calcInput} /></Field></div>
        )}
        {mode === "goal" && (
          <div style={{ width: 170 }}><Field label="TARGET CORPUS (₹)">
            <input type="number" value={target} onChange={e => setTarget(+e.target.value)} style={calcInput} /></Field></div>
        )}
        {mode === "swp" && (<>
          <div style={{ width: 160 }}><Field label="STARTING CORPUS (₹)">
            <input type="number" value={corpus} onChange={e => setCorpus(+e.target.value)} style={calcInput} /></Field></div>
          <div style={{ width: 150 }}><Field label="MONTHLY WITHDRAWAL (₹)">
            <input type="number" value={withdrawal} onChange={e => setWithdrawal(+e.target.value)} style={calcInput} /></Field></div>
        </>)}
        {mode !== "swp" && (
          <div style={{ width: 90 }}><Field label="YEARS">
            <input type="number" value={years} onChange={e => setYears(+e.target.value)} style={calcInput} /></Field></div>
        )}
        <div style={{ width: 110 }}><Field label="ANNUAL RETURN %">
          <input type="number" value={rate} onChange={e => setRate(+e.target.value)} style={calcInput} /></Field></div>
        <button onClick={run} style={{
          background: GOLD, color: BG, border: "none", borderRadius: 6, padding: "9px 20px",
          fontSize: 13, fontWeight: 700, cursor: "pointer", fontFamily: "'Inter',sans-serif", height: 36,
        }}>Calculate</button>
      </div>

      {error && <div className="mono" style={{ color: RED, fontSize: 12.5, padding: "8px 0" }}>{error}</div>}

      {res && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 10 }}>
          {res.mode === "goal" && <>
            <Tile label="MONTHLY SIP NEEDED" value={fmtINR(res.monthly_sip)} color={GOLD} />
            <Tile label="TOTAL INVESTED" value={fmtINR(res.total_invested)} />
            <Tile label="TARGET" value={fmtINR(res.target)} color={GREEN} />
          </>}
          {(res.mode === "sip" || res.mode === "lumpsum") && <>
            <Tile label="INVESTED" value={fmtINR(res.invested)} />
            <Tile label="PROJECTED VALUE" value={fmtINR(res.future_value)} color={GOLD} />
            <Tile label="GAIN" value={fmtINR(res.gain)} color={GREEN} />
          </>}
          {res.mode === "swp" && <>
            <Tile label="LASTS" value={res.sustained ? "Indefinitely" : `${(res.lasts_months / 12).toFixed(1)} yrs`}
              color={res.sustained ? GREEN : GOLD} />
            <Tile label="MONTHLY WITHDRAWAL" value={fmtINR(res.monthly_withdrawal)} />
            <Tile label="STARTING CORPUS" value={fmtINR(res.corpus)} />
          </>}
        </div>
      )}
      <div className="mono" style={{ fontSize: 10, color: MUTE, marginTop: 12, lineHeight: 1.5 }}>
        Projections assume a constant {rate}% annual return — an assumption for planning, not a prediction.
        Real returns vary year to year.
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

      <OverlapPanel codes={codes} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Portfolio overlap — how much of these funds is actually the same stocks.
// ---------------------------------------------------------------------------
function overlapColor(v) {
  if (v == null) return MUTE;
  return v >= 50 ? RED : v >= 30 ? GOLD : GREEN;
}

function OverlapPanel({ codes }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!codes || codes.length < 2) return;
    setD(null); setErr(null);
    fetch(`${API_BASE}/api/schemes/overlap?codes=${codes.join(",")}`)
      .then(r => { if (!r.ok) throw new Error(`API ${r.status}`); return r.json(); })
      .then(setD).catch(e => setErr(e.message));
  }, [codes]);

  if (!codes || codes.length < 2) return null;

  const pairs = d ? d.pairs.filter(p => p.overlap_pct != null) : [];
  const missing = d ? d.funds.filter(f => f.holdings_count === 0) : [];

  return (
    <div style={{ background: PANEL, border: BORDER, borderRadius: 8, padding: 20, marginTop: 20 }}>
      <span style={sectionLabel}>PORTFOLIO OVERLAP</span>
      <div className="mono" style={{ fontSize: 10.5, color: MUTE, marginTop: 4, maxWidth: 700, lineHeight: 1.5 }}>
        How much of these funds is the same stocks. Overlap is the share of a rupee that's
        duplicated — matched on ISIN, so different spellings of one company still count.
      </div>

      {err && <div className="mono" style={{ fontSize: 12, color: RED, marginTop: 12 }}>Couldn't load: {err}</div>}
      {!d && !err && <div className="mono" style={{ fontSize: 12, color: MUTE, marginTop: 12 }}>Loading…</div>}

      {d && (
        <>
          {d.as_of_mismatch && (
            <div className="mono" style={{
              fontSize: 11, color: GOLD, marginTop: 12, display: "flex", gap: 7, alignItems: "flex-start",
            }}>
              <AlertTriangle size={13} style={{ marginTop: 1, flexShrink: 0 }} />
              <span>
                These portfolios are from different months
                ({d.funds.filter(f => f.as_of_date).map(f => f.as_of_date).join(" vs ")}) —
                AMCs disclose on their own schedule, so this is an approximate comparison.
              </span>
            </div>
          )}

          {missing.length > 0 && (
            <div className="mono" style={{ fontSize: 11, color: MUTE, marginTop: 12 }}>
              No disclosed holdings yet for {missing.map(f => f.name).join(", ")} — shown as "—"
              rather than 0%.
            </div>
          )}

          {pairs.length > 0 && (
            <div style={{ marginTop: 16 }}>
              {pairs.map((p, i) => (
                <div key={i} className="ledger-line" style={{ padding: "10px 0" }}>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 12, alignItems: "baseline" }}>
                    <span className="mono" style={{ fontSize: 12, color: INK }}>
                      {p.a_name} <span style={{ color: MUTE }}>vs</span> {p.b_name}
                    </span>
                    <span className="mono" style={{ fontSize: 16, fontWeight: 700, color: overlapColor(p.overlap_pct) }}>
                      {p.overlap_pct}%
                    </span>
                  </div>
                  <div className="mono" style={{ fontSize: 10.5, color: MUTE, marginTop: 3 }}>
                    {p.common_count} common holdings
                    {p.top_common.length > 0 && " · biggest: "}
                    {p.top_common.slice(0, 3).map(t => `${t.name} ${t.min_pct}%`).join(", ")}
                  </div>
                </div>
              ))}
            </div>
          )}

          {d.combined.length > 0 && (
            <div style={{ marginTop: 22, borderTop: "1px solid rgba(237,234,226,0.08)", paddingTop: 16 }}>
              <span style={sectionLabel}>WHAT YOU'D ACTUALLY OWN</span>
              <div className="mono" style={{ fontSize: 10.5, color: MUTE, marginTop: 4 }}>
                Splitting your money equally across these {d.funds.length} funds.
              </div>
              <div style={{ display: "flex", gap: 34, flexWrap: "wrap", margin: "14px 0 6px" }}>
                <Fact label="TOP 5 STOCKS" value={d.concentration_top5 != null ? `${d.concentration_top5}%` : "—"} sub="of your money" />
                <Fact label="TOP 10 STOCKS" value={d.concentration_top10 != null ? `${d.concentration_top10}%` : "—"} sub="of your money" />
              </div>
              {d.combined.slice(0, 8).map((h, i) => (
                <div key={i} className="ledger-line mono" style={{
                  display: "grid", gridTemplateColumns: "1fr auto auto", gap: 12,
                  padding: "7px 0", fontSize: 12.5, alignItems: "center",
                }}>
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{h.name}</span>
                  <span style={{ fontSize: 10, color: h.held_by === d.funds.length ? GOLD : MUTE }}>
                    in {h.held_by}/{d.funds.length}
                  </span>
                  <span style={{ fontWeight: 600, color: INK, minWidth: 52, textAlign: "right" }}>{h.pct}%</span>
                </div>
              ))}
            </div>
          )}

          <div className="mono" style={{ fontSize: 10, color: MUTE, marginTop: 14, lineHeight: 1.5 }}>
            Weights are as disclosed ({d.funds.filter(f => f.covered_pct > 0).map(f => `${f.covered_pct}%`).join(" / ")} of AUM
            carries an ISIN — cash and derivatives are excluded, and we don't rescale to 100%).
          </div>
        </>
      )}
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
// minimal deep-linking: ?code=<scheme> opens that scheme's detail directly, so
// funds (including guard-flagged ones hidden from the explorer) are shareable /
// bookmarkable. Kept intentionally tiny — no router dependency.
function viewFromUrl() {
  const code = new URLSearchParams(window.location.search).get("code");
  return code ? { page: "detail", code } : { page: "explorer" };
}

// ---------------------------------------------------------------------------
// Stale-data banner
//
// The scheduled jobs fail SILENTLY — cron's errors go to a system mail file
// nobody reads, and a job that never starts writes nothing to its own log. That
// is exactly how a broken nightly sync went unnoticed for three weeks while the
// app kept serving confidently-stale numbers. Surfacing freshness here, in the
// one place the data actually gets looked at, is the failure's only reliable
// tripwire.
// ---------------------------------------------------------------------------
const SOURCE_LABEL = { nav: "NAV prices", holdings: "portfolio holdings", costs: "fees & AUM" };

function StaleDataBanner() {
  const [health, setHealth] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/health/data`)
      .then(r => r.json()).then(setHealth).catch(() => {});
  }, []);

  if (!health || !health.stale) return null;
  const stale = Object.entries(health.sources).filter(([, v]) => v.stale);
  if (!stale.length) return null;

  return (
    <div style={{
      background: "rgba(198,82,75,0.12)", borderBottom: `1px solid ${RED}`,
      padding: "10px 28px", display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap",
    }}>
      <span className="mono" style={{ fontSize: 12, fontWeight: 700, color: RED }}>
        DATA MAY BE OUT OF DATE
      </span>
      <span className="mono" style={{ fontSize: 11.5, color: MUTE }}>
        {stale.map(([k, v]) => `${SOURCE_LABEL[k] || k} last updated ${v.latest || "never"}` +
          (v.age_days != null ? ` (${v.age_days} days ago)` : "")).join(" · ")}
        {" — the scheduled update may have failed."}
      </span>
    </div>
  );
}

export default function App() {
  const [view, setView] = useState(viewFromUrl);
  const [compareCodes, setCompareCodes] = useState([]);

  const go = (next) => {
    const qs = next.page === "detail" ? `?code=${encodeURIComponent(next.code)}` : "";
    window.history.pushState(next, "", qs || window.location.pathname);
    setView(next);
  };

  // keep the browser back/forward buttons in sync with the view
  useEffect(() => {
    const onPop = () => setView(viewFromUrl());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

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
          onClick={() => go({ page: "explorer" })}>
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

      <StaleDataBanner />

      {view.page === "explorer" && (
        <Explorer
          onSelectScheme={code => go({ page: "detail", code })}
          compareCodes={compareCodes}
          toggleCompare={toggleCompare}
          onOpenCompare={() => go({ page: "compare" })}
        />
      )}
      {view.page === "detail" && (
        <SchemeDetail code={view.code} onBack={() => go({ page: "explorer" })} />
      )}
      {view.page === "compare" && (
        <Compare codes={compareCodes} onBack={() => go({ page: "explorer" })} />
      )}
    </div>
  );
}
