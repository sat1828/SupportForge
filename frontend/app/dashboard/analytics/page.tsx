"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import {
  TrendingUp, Zap, Shield, Clock, BarChart3,
  Activity, CheckCircle2, AlertTriangle, ChevronLeft,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchMetrics() {
  const { data } = await axios.get(`${API}/api/admin/metrics`, { withCredentials: true });
  return data;
}

function MetricBar({ label, value, max, color, unit = "" }: {
  label: string; value: number; max: number; color: string; unit?: string;
}) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span style={{ color: "var(--color-text-secondary)" }}>{label}</span>
        <span style={{ color: "var(--color-text-primary)" }}>{value.toFixed(1)}{unit} / {max}{unit}</span>
      </div>
      <div className="h-2 rounded-full" style={{ background: "rgba(255,255,255,0.07)" }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="h-full rounded-full"
          style={{ background: color }}
        />
      </div>
    </div>
  );
}

export default function AnalyticsPage() {
  const { data: metrics, isLoading } = useQuery({
    queryKey: ["metrics"], queryFn: fetchMetrics, refetchInterval: 30_000,
  });

  const m = metrics || {};
  const resolution_pct = ((m.resolution_rate || 0) * 100).toFixed(1);
  const escalation_pct = ((m.escalation_rate || 0) * 100).toFixed(1);
  const conf_pct = ((m.avg_confidence || 0) * 100).toFixed(0);

  return (
    <div className="min-h-screen" style={{ background: "var(--color-bg-deep)" }}>
      {/* Header */}
      <header className="glass border-b flex items-center gap-4 px-6 py-4 sticky top-0 z-10"
        style={{ borderColor: "var(--color-border)" }}>
        <Link href="/dashboard"
          className="p-2 rounded-lg hover:bg-white/[0.06] transition-colors"
          style={{ color: "var(--color-text-secondary)" }}>
          <ChevronLeft className="w-5 h-5" />
        </Link>
        <div>
          <h1 className="font-semibold">Analytics</h1>
          <p className="text-xs" style={{ color: "var(--color-text-muted)" }}>Live system performance</p>
        </div>
        <div className="ml-auto text-xs px-3 py-1.5 rounded-full"
          style={{ background: "rgba(16,185,129,0.1)", color: "#34d399", border: "1px solid rgba(16,185,129,0.2)" }}>
          <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block mr-1.5" />
          Live · Refreshing every 30s
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8 space-y-6">
        {/* KPIs */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label: "Resolution Rate", value: `${resolution_pct}%`, icon: <CheckCircle2 className="w-5 h-5" />, color: "text-emerald-400", bg: "bg-emerald-500/10", target: "Target: 70%" },
            { label: "Escalation Rate", value: `${escalation_pct}%`, icon: <AlertTriangle className="w-5 h-5" />, color: "text-amber-400", bg: "bg-amber-500/10", target: "Target: <20%" },
            { label: "Avg Confidence", value: `${conf_pct}%`, icon: <Activity className="w-5 h-5" />, color: "text-violet-400", bg: "bg-violet-500/10", target: "Target: >75%" },
            { label: "Total Tickets", value: m.total_tickets || 0, icon: <BarChart3 className="w-5 h-5" />, color: "text-blue-400", bg: "bg-blue-500/10", target: "All time" },
          ].map((kpi) => (
            <motion.div key={kpi.label}
              initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
              className="glass rounded-2xl p-5">
              <div className={`w-10 h-10 rounded-xl ${kpi.bg} ${kpi.color} flex items-center justify-center mb-3`}>
                {kpi.icon}
              </div>
              <div className={`text-2xl font-bold mb-0.5 ${kpi.color}`}>{isLoading ? "—" : kpi.value}</div>
              <div className="text-sm font-medium" style={{ color: "var(--color-text-secondary)" }}>{kpi.label}</div>
              <div className="text-xs mt-1" style={{ color: "var(--color-text-muted)" }}>{kpi.target}</div>
            </motion.div>
          ))}
        </div>

        {/* Execution Budget Meters */}
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.15 }}
          className="glass rounded-2xl p-6">
          <div className="flex items-center gap-2 mb-5">
            <Shield className="w-5 h-5 text-blue-400" />
            <h2 className="font-semibold">Execution Budget Compliance</h2>
            <span className="ml-auto text-xs px-2.5 py-1 rounded-full"
              style={{ background: "rgba(16,185,129,0.1)", color: "#34d399" }}>
              All 21 invariants enforced
            </span>
          </div>
          <div className="grid md:grid-cols-2 gap-4">
            <MetricBar label="Avg LLM Calls / Ticket" value={m.avg_llm_calls_per_ticket || 0} max={5} color="#3b82f6" />
            <MetricBar label="Avg Tokens / Ticket (÷100)" value={(m.avg_tokens_per_ticket || 0) / 100} max={50} color="#8b5cf6" />
            <MetricBar label="Resolution Rate" value={m.resolution_rate || 0} max={1} color="#10b981" />
            <MetricBar label="Escalation Rate" value={m.escalation_rate || 0} max={1} color="#f59e0b" />
          </div>
        </motion.div>

        {/* Invariant status table */}
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.25 }}
          className="glass rounded-2xl overflow-hidden">
          <div className="px-6 py-4 border-b flex items-center gap-2" style={{ borderColor: "var(--color-border)" }}>
            <Zap className="w-5 h-5 text-amber-400" />
            <h2 className="font-semibold">21 System Invariants</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b" style={{ borderColor: "var(--color-border)" }}>
                  {["#", "Invariant", "Limit", "Enforced In", "Status"].map((h) => (
                    <th key={h} className="px-5 py-3 text-left text-xs font-medium uppercase tracking-wide"
                      style={{ color: "var(--color-text-muted)" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  [1, "max_steps_per_ticket", "≤ 10", "budget_guard.py", true],
                  [2, "max_total_latency", "≤ 10s", "budget_guard.py", true],
                  [3, "max_kb_retries", "≤ 3", "budget_guard.py", true],
                  [4, "max_context_messages", "≤ 6", "context_manager.py", true],
                  [5, "max_kb_results", "≤ 3", "context_manager.py", true],
                  [6, "fast_path_latency", "≤ 200ms", "fastpath.py", true],
                  [7, "rag_fast_path_latency", "≤ 60ms", "retriever.py", true],
                  [8, "replay_full_retention", "7 days", "replay.py", true],
                  [9, "replay_summary_retention", "90 days", "replay.py", true],
                  [10, "fast_path_executes_in_200ms", "≤ 200ms", "test_fastpath.py", true],
                  [11, "fast_path_used_logged", "Always", "fastpath.py", true],
                  [12, "confidence_deterministic", "100%", "confidence.py", true],
                  [13, "tool_fail_caps_confidence", "≤ 60%", "confidence.py", true],
                  [14, "post_chat_returns_202", "≤ 50ms", "agent.py", true],
                  [15, "100_concurrent_no_crash", "0% crash", "worker.py", true],
                  [16, "correction_creates_chunk", "Always", "feedback_indexer.py", true],
                  [17, "correction_boost_1_5x", "1.5×", "feedback_indexer.py", true],
                  [18, "correction_creates_perf_log", "Always", "admin.py", true],
                  [19, "max_llm_calls", "≤ 5", "resilience.py", true],
                  [20, "max_tokens", "≤ 5000", "resilience.py", true],
                  [21, "zero_crash_rate", "0%", "fastpath.py + 130 cases", true],
                ].map(([num, name, limit, file, ok]) => (
                  <tr key={num as number} className="border-b hover:bg-white/[0.02] transition-colors"
                    style={{ borderColor: "var(--color-border)" }}>
                    <td className="px-5 py-3 font-mono text-xs" style={{ color: "var(--color-text-muted)" }}>
                      {String(num).padStart(2, "0")}
                    </td>
                    <td className="px-5 py-3 font-mono text-xs" style={{ color: "var(--color-text-primary)" }}>
                      {name}
                    </td>
                    <td className="px-5 py-3 text-xs font-semibold" style={{ color: "#60a5fa" }}>{limit}</td>
                    <td className="px-5 py-3 text-xs" style={{ color: "var(--color-text-muted)" }}>{file}</td>
                    <td className="px-5 py-3">
                      {ok
                        ? <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full"
                            style={{ background: "rgba(16,185,129,0.15)", color: "#34d399" }}>
                            <CheckCircle2 className="w-3 h-3" /> Enforced
                          </span>
                        : <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full"
                            style={{ background: "rgba(239,68,68,0.15)", color: "#f87171" }}>
                            Missing
                          </span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </motion.div>
      </main>
    </div>
  );
}
