import React, { useState, useEffect } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, AreaChart, Area, BarChart, Bar
} from "recharts";
import { TrendingUp, TrendingDown, ChevronDown, Search, ArrowUpRight, ArrowLeft } from "lucide-react";

// Point this at your running backend. In production, set via build-time env var.
const API_BASE = "http://localhost:8000";

const fonts = `
  @import url('https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,500&family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
  .mono { font-family: 'IBM Plex Mono', monospace; font-variant-numeric: tabular-nums; }
  .serif { font-family: 'Newsreader', serif; }
  .ledger-line { border-bottom: 1px solid rgba(237,234,226,0.08); }
`;

function momentumColor(v) {
  if (v >= 70) return "#3FA796";
  if (v >= 50) return "#C9A227";
  return "#C6524B";
}

// ---------- Landing page ----------
function Landing({ onSelectFund }) {
  const [data, setData] = useState(null);
  const [activeSector, setActiveSector] = useState("All");
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/funds?sort=return_1y&limit=100`)
      .then(r => {
        if (!r.ok) throw new Error(`API returned ${r.status}`);
        return r.json();
      })
      .then(setData)
      .catch(e => setError(e.message));
  }, []);

  if (error) {
    return (
      <div style={{ padding: 40, color: "#C6524B" }} className="mono">
        Couldn't load funds: {error}. Is the backend running at {API_BASE}?
      </div>
    );
  }
  if (!data) {
    return <div style={{ padding: 40, color: "#8B96A6" }} className="mono">Loading funds…</div>;
  }

  const visibleFunds = activeSector === "All"
    ? data.funds
    : data.funds.filter(f => f.sector_focus === activeSector);

  return (
    <div style={{ padding: "28px 28px 60px", maxWidth: 1360, margin: "0 auto" }}>
      <div style={{ marginBottom: 24 }}>
        <div className="mono" style={{ fontSize: 11, color: "#8B96A6", letterSpacing: "0.08em", marginBottom: 6 }}>
          {data.funds.length} SCHEMES TRACKED{data.nav_as_of ? ` · NAV AS OF ${data.nav_as_of}` : ""}
        </div>
        <div className="serif" style={{ fontSize: 32, fontWeight: 500 }}>Sector-wise Fund Performance</div>
      </div>

      {/* Sector filter tabs */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 24 }}>
        {["All", ...data.sectors].map(s => (
          <button key={s} onClick={() => setActiveSector(s)}
            style={{
              background: activeSector === s ? "#C9A227" : "#0F1B2B",
              color: activeSector === s ? "#0A131F" : "#8B96A6",
              border: "1px solid rgba(237,234,226,0.1)",
              borderRadius: 20, padding: "6px 14px", fontSize: 12.5,
              fontWeight: 600, cursor: "pointer", fontFamily: "'Inter',sans-serif"
            }}>
            {s}
          </button>
        ))}
      </div>

      {/* Fund grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 14 }}>
        {visibleFunds.map(f => {
          const beatBench = f.return_1y != null && f.benchmark_1y != null && f.return_1y > f.benchmark_1y;
          return (
            <button key={f.id} onClick={() => onSelectFund(f.id)}
              style={{
                textAlign: "left", background: "#0F1B2B", border: "1px solid rgba(237,234,226,0.08)",
                borderRadius: 8, padding: 18, cursor: "pointer", color: "inherit", fontFamily: "inherit"
              }}>
              <div className="mono" style={{ fontSize: 10.5, color: "#8B96A6", letterSpacing: "0.06em", marginBottom: 6 }}>
                {f.sector_focus.toUpperCase()} · {f.amc}
              </div>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 14, lineHeight: 1.3 }}>{f.name}</div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
                <div>
                  <div className="mono" style={{ fontSize: 10, color: "#8B96A6" }}>NAV</div>
                  <div className="mono" style={{ fontSize: 15, fontWeight: 600 }}>₹{f.nav}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div className="mono" style={{ fontSize: 10, color: "#8B96A6" }}>1Y RETURN</div>
                  <div className="mono" style={{
                    fontSize: 18, fontWeight: 700,
                    color: beatBench ? "#3FA796" : "#C6524B",
                    display: "flex", alignItems: "center", gap: 3, justifyContent: "flex-end"
                  }}>
                    {beatBench ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                    {f.return_1y != null ? `${f.return_1y}%` : "—"}
                  </div>
                </div>
              </div>
              {f.benchmark_1y != null && (
                <div className="mono" style={{ fontSize: 10.5, color: "#8B96A6", marginTop: 6 }}>
                  vs {f.benchmark_1y}% benchmark · {f.expense_ratio}% TER
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ---------- Detail view ----------
function FundDetail({ fundId, onBack }) {
  const [fund, setFund] = useState(null);
  const [sectors, setSectors] = useState([]);
  const [flows, setFlows] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/api/funds/${fundId}`).then(r => { if (!r.ok) throw new Error("fund not found"); return r.json(); }),
      fetch(`${API_BASE}/api/sectors`).then(r => r.json()),
      fetch(`${API_BASE}/api/flows`).then(r => r.json()),
    ]).then(([f, s, fl]) => { setFund(f); setSectors(s); setFlows(fl); })
      .catch(e => setError(e.message));
  }, [fundId]);

  if (error) return <div style={{ padding: 40, color: "#C6524B" }} className="mono">{error}</div>;
  if (!fund) return <div style={{ padding: 40, color: "#8B96A6" }} className="mono">Loading…</div>;

  return (
    <div style={{ padding: "28px 28px 60px", maxWidth: 1360, margin: "0 auto" }}>
      <button onClick={onBack} style={{
        background: "none", border: "none", color: "#8B96A6", cursor: "pointer",
        display: "flex", alignItems: "center", gap: 6, marginBottom: 20, fontSize: 13, fontFamily: "'Inter',sans-serif"
      }}>
        <ArrowLeft size={15} /> Back to all funds
      </button>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 24 }}>
        <div>
          <div className="mono" style={{ fontSize: 11, color: "#8B96A6", letterSpacing: "0.08em", marginBottom: 6 }}>
            {fund.category.toUpperCase()} · {fund.amc}
          </div>
          <div className="serif" style={{ fontSize: 32, fontWeight: 500 }}>{fund.name}</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="mono" style={{ fontSize: 12, color: "#8B96A6" }}>NAV</div>
          <div className="mono" style={{ fontSize: 26, fontWeight: 600 }}>₹{fund.nav}</div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 20 }}>
        <div style={{ background: "#0F1B2B", border: "1px solid rgba(237,234,226,0.08)", borderRadius: 8, padding: 20 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: "#8B96A6", letterSpacing: "0.04em" }}>RETURNS vs BENCHMARK vs CATEGORY</span>
          <div style={{ marginTop: 16 }}>
            {fund.returns.map((r, i) => (
              <div key={i} className="ledger-line mono" style={{ display: "grid", gridTemplateColumns: "80px 1fr 1fr 1fr", padding: "9px 0", fontSize: 13 }}>
                <span style={{ color: "#8B96A6" }}>{r.period}</span>
                <span style={{ color: "#EDEAE2", fontWeight: 600 }}>{r.fund_return}%</span>
                <span style={{ color: "#8B96A6" }}>{r.benchmark_return}% <span style={{ fontSize: 10 }}>bench</span></span>
                <span style={{ color: "#8B96A6" }}>{r.category_avg_return}% <span style={{ fontSize: 10 }}>category</span></span>
              </div>
            ))}
          </div>

          <div style={{ marginTop: 24, borderTop: "1px solid rgba(237,234,226,0.08)", paddingTop: 16 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: "#8B96A6", letterSpacing: "0.04em" }}>COSTS</span>
            <div className="ledger-line mono" style={{ display: "flex", justifyContent: "space-between", padding: "10px 0", fontSize: 13 }}>
              <span style={{ color: "#8B96A6" }}>Expense Ratio (TER)</span>
              <span style={{ color: "#C9A227", fontWeight: 600 }}>{fund.expense_ratio}%</span>
            </div>
            <div className="mono" style={{ display: "flex", justifyContent: "space-between", padding: "10px 0", fontSize: 13 }}>
              <span style={{ color: "#8B96A6" }}>Exit Load</span>
              <span style={{ color: "#EDEAE2" }}>{fund.exit_load}</span>
            </div>
          </div>
        </div>

        <div style={{ background: "#0F1B2B", border: "1px solid rgba(237,234,226,0.08)", borderRadius: 8, padding: 20 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: "#8B96A6", letterSpacing: "0.04em" }}>FII / DII NET FLOW (₹ CR)</span>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={flows}>
              <XAxis dataKey="date" stroke="#8B96A6" fontSize={9} tickLine={false} axisLine={false} />
              <YAxis stroke="#8B96A6" fontSize={9} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ background: "#0A131F", border: "1px solid rgba(237,234,226,0.15)", borderRadius: 6, fontSize: 11 }} />
              <Bar dataKey="fii_cr" fill="#C6524B" radius={[2, 2, 0, 0]} />
              <Bar dataKey="dii_cr" fill="#3FA796" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>

          <div style={{ marginTop: 16 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: "#8B96A6", letterSpacing: "0.04em" }}>SECTOR MOMENTUM</span>
            {sectors.slice(0, 6).map((s, i) => (
              <div key={i} className="mono" style={{ display: "flex", justifyContent: "space-between", padding: "7px 0", fontSize: 12 }}>
                <span style={{ color: "#EDEAE2" }}>{s.sector}</span>
                <span style={{ color: momentumColor(s.momentum_score), fontWeight: 600 }}>{s.momentum_score}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------- Root app: simple two-view router ----------
export default function App() {
  const [view, setView] = useState({ page: "landing" });

  return (
    <div style={{ background: "#0A131F", color: "#EDEAE2", minHeight: "100vh", fontFamily: "'Inter', sans-serif" }}>
      <style>{fonts}</style>

      <div style={{
        borderBottom: "1px solid rgba(237,234,226,0.1)", background: "#0F1B2B",
        padding: "14px 28px", display: "flex", alignItems: "center", justifyContent: "space-between"
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}
          onClick={() => setView({ page: "landing" })}>
          <div style={{
            width: 28, height: 28, borderRadius: 4, background: "linear-gradient(135deg,#C9A227,#8a6f1a)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontFamily: "'Newsreader', serif", fontWeight: 600, fontSize: 15, color: "#0A131F"
          }}>₹</div>
          <span className="serif" style={{ fontSize: 19, fontWeight: 500 }}>
            Money<span style={{ color: "#C9A227" }}>Mint</span>
          </span>
        </div>
        <div className="mono" style={{ fontSize: 12, color: "#8B96A6" }}>Personal MF Analytics</div>
      </div>

      {view.page === "landing"
        ? <Landing onSelectFund={id => setView({ page: "detail", fundId: id })} />
        : <FundDetail fundId={view.fundId} onBack={() => setView({ page: "landing" })} />
      }
    </div>
  );
}
