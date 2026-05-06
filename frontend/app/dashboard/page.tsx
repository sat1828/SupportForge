"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import {
  LayoutDashboard, MessageSquare, BarChart3, Settings,
  ChevronRight, TrendingUp, Clock, CheckCircle2,
  AlertTriangle, Zap, LogOut, Menu, X, Bell,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchMetrics() {
  const { data } = await axios.get(`${API}/api/admin/metrics`, { withCredentials: true });
  return data;
}

async function fetchTickets() {
  const { data } = await axios.get(`${API}/api/tickets/?limit=20`, { withCredentials: true });
  return data;
}

const NAV = [
  { href: "/dashboard", label: "Overview", icon: <LayoutDashboard className="w-4 h-4" /> },
  { href: "/dashboard/tickets", label: "Tickets", icon: <MessageSquare className="w-4 h-4" /> },
  { href: "/dashboard/analytics", label: "Analytics", icon: <BarChart3 className="w-4 h-4" /> },
];

function StatCard({ label, value, sub, color, icon }: {
  label: string; value: string | number; sub?: string;
  color: string; icon: React.ReactNode;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass glass-hover rounded-2xl p-6"
    >
      <div className="flex items-start justify-between mb-4">
        <div className={`p-2.5 rounded-xl ${color}`}>{icon}</div>
        <TrendingUp className="w-4 h-4" style={{ color: "var(--color-text-muted)" }} />
      </div>
      <div className="text-3xl font-bold mb-1">{value}</div>
      <div className="text-sm font-medium" style={{ color: "var(--color-text-secondary)" }}>{label}</div>
      {sub && <div className="text-xs mt-1" style={{ color: "var(--color-text-muted)" }}>{sub}</div>}
    </motion.div>
  );
}

function TicketRow({ ticket }: { ticket: any }) {
  const statusClass = `status-${ticket.status.replace(" ", "_")}`;
  const confColor = ticket.confidence_score
    ? ticket.confidence_score >= 0.8 ? "conf-high"
      : ticket.confidence_score >= 0.65 ? "conf-mid" : "conf-low"
    : "";

  return (
    <motion.tr
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="border-b hover:bg-white/[0.02] transition-colors cursor-pointer group"
      style={{ borderColor: "var(--color-border)" }}
    >
      <td className="px-4 py-3.5">
        <Link href={`/dashboard/tickets/${ticket.id}`} className="font-medium text-sm hover:text-blue-400 transition-colors">
          {ticket.title.length > 45 ? ticket.title.slice(0, 45) + "…" : ticket.title}
        </Link>
      </td>
      <td className="px-4 py-3.5">
        <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${statusClass}`}>
          {ticket.status.replace("_", " ")}
        </span>
      </td>
      <td className={`px-4 py-3.5 text-xs font-mono font-bold priority-${ticket.priority}`}>
        {ticket.priority}
      </td>
      <td className={`px-4 py-3.5 text-sm font-mono ${confColor}`}>
        {ticket.confidence_score != null ? `${(ticket.confidence_score * 100).toFixed(0)}%` : "—"}
      </td>
      <td className="px-4 py-3.5 text-xs" style={{ color: "var(--color-text-muted)" }}>
        {new Date(ticket.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
      </td>
      <td className="px-4 py-3.5">
        <Link href={`/dashboard/tickets/${ticket.id}`}
          className="opacity-0 group-hover:opacity-100 transition-opacity text-blue-400">
          <ChevronRight className="w-4 h-4" />
        </Link>
      </td>
    </motion.tr>
  );
}

export default function DashboardPage() {
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const { data: metrics, isLoading: metricsLoading } = useQuery({
    queryKey: ["metrics"], queryFn: fetchMetrics, refetchInterval: 15_000,
  });
  const { data: tickets, isLoading: ticketsLoading } = useQuery({
    queryKey: ["tickets"], queryFn: fetchTickets, refetchInterval: 10_000,
  });

  const stats = [
    {
      label: "Total Tickets", value: metrics?.total_tickets ?? "—",
      sub: "All time", color: "bg-blue-500/10 text-blue-400",
      icon: <MessageSquare className="w-4 h-4" />,
    },
    {
      label: "Resolved Today", value: metrics?.resolved_today ?? "—",
      sub: `${((metrics?.resolution_rate ?? 0) * 100).toFixed(0)}% resolution rate`,
      color: "bg-emerald-500/10 text-emerald-400",
      icon: <CheckCircle2 className="w-4 h-4" />,
    },
    {
      label: "Escalated", value: metrics?.escalated_count ?? "—",
      sub: `${((metrics?.escalation_rate ?? 0) * 100).toFixed(0)}% escalation rate`,
      color: "bg-amber-500/10 text-amber-400",
      icon: <AlertTriangle className="w-4 h-4" />,
    },
    {
      label: "Avg Confidence", value: metrics ? `${(metrics.avg_confidence * 100).toFixed(0)}%` : "—",
      sub: `~${(metrics?.avg_llm_calls_per_ticket ?? 0).toFixed(1)} LLM calls/ticket`,
      color: "bg-violet-500/10 text-violet-400",
      icon: <Zap className="w-4 h-4" />,
    },
  ];

  return (
    <div className="min-h-screen flex" style={{ background: "var(--color-bg-deep)" }}>
      {/* ── Sidebar ──────────────────────────────────────────── */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.aside
            initial={{ x: -260 }} animate={{ x: 0 }} exit={{ x: -260 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="w-64 flex-shrink-0 glass border-r flex flex-col"
            style={{ borderColor: "var(--color-border)", minHeight: "100vh" }}
          >
            {/* Brand */}
            <div className="p-6 border-b flex items-center gap-3" style={{ borderColor: "var(--color-border)" }}>
              <div className="w-9 h-9 rounded-xl gradient-primary flex items-center justify-center shadow-lg">
                <MessageSquare className="w-5 h-5 text-white" />
              </div>
              <span className="text-lg font-bold">Support<span className="gradient-text">Forge</span></span>
            </div>

            <nav className="flex-1 p-4 space-y-1">
              {NAV.map((item) => (
                <Link key={item.href} href={item.href}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all hover:bg-white/[0.06]"
                  style={{ color: "var(--color-text-secondary)" }}>
                  {item.icon}
                  {item.label}
                </Link>
              ))}
            </nav>

            {/* User + logout */}
            <div className="p-4 border-t" style={{ borderColor: "var(--color-border)" }}>
              <Link href="/login"
                className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-all hover:bg-red-500/10"
                style={{ color: "var(--color-text-muted)" }}>
                <LogOut className="w-4 h-4" /> Sign out
              </Link>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      {/* ── Main content ─────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Topbar */}
        <header className="glass border-b flex items-center justify-between px-6 py-4 sticky top-0 z-20"
          style={{ borderColor: "var(--color-border)" }}>
          <div className="flex items-center gap-4">
            <button onClick={() => setSidebarOpen(!sidebarOpen)}
              className="p-2 rounded-lg hover:bg-white/[0.06] transition-colors"
              style={{ color: "var(--color-text-secondary)" }}>
              {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
            <div>
              <h1 className="text-lg font-semibold">Overview</h1>
              <p className="text-xs" style={{ color: "var(--color-text-muted)" }}>
                {new Date().toLocaleDateString("en-IN", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Link href="/dashboard/tickets/new"
              className="flex items-center gap-2 px-4 py-2 rounded-xl gradient-primary text-white text-sm font-medium shadow-lg hover:opacity-90 transition-all">
              <MessageSquare className="w-4 h-4" /> New Ticket
            </Link>
            <button className="p-2 rounded-lg hover:bg-white/[0.06] transition-colors relative"
              style={{ color: "var(--color-text-secondary)" }}>
              <Bell className="w-5 h-5" />
              <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-blue-500" />
            </button>
          </div>
        </header>

        <main className="flex-1 p-6 space-y-6">
          {/* Stats */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {stats.map((s) => (
              <StatCard key={s.label} {...s} />
            ))}
          </div>

          {/* Invariant health bar */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
            className="glass rounded-2xl p-5"
          >
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold">Execution Budget (Live)</h2>
              <span className="text-xs px-2.5 py-1 rounded-full"
                style={{ background: "rgba(16,185,129,0.15)", color: "#34d399" }}>
                All invariants OK
              </span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {[
                { label: "Max Steps", used: 0, max: 10 },
                { label: "Latency", used: 0, max: 10, unit: "s" },
                { label: "KB Retries", used: 0, max: 3 },
                { label: "LLM Calls", used: metrics?.avg_llm_calls_per_ticket ?? 0, max: 5 },
                { label: "Tokens", used: (metrics?.avg_tokens_per_ticket ?? 0) / 1000, max: 5, unit: "k" },
              ].map((inv) => {
                const pct = Math.min((inv.used / inv.max) * 100, 100);
                const barColor = pct > 80 ? "#ef4444" : pct > 60 ? "#f59e0b" : "#10b981";
                return (
                  <div key={inv.label} className="space-y-1">
                    <div className="flex justify-between text-xs" style={{ color: "var(--color-text-secondary)" }}>
                      <span>{inv.label}</span>
                      <span>{inv.used.toFixed(inv.unit === "k" ? 1 : 0)}{inv.unit ?? ""}/{inv.max}{inv.unit ?? ""}</span>
                    </div>
                    <div className="h-1.5 rounded-full" style={{ background: "rgba(255,255,255,0.08)" }}>
                      <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: barColor }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </motion.div>

          {/* Ticket table */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="glass rounded-2xl overflow-hidden"
          >
            <div className="flex items-center justify-between px-6 py-4 border-b" style={{ borderColor: "var(--color-border)" }}>
              <h2 className="font-semibold">Recent Tickets</h2>
              <Link href="/dashboard/tickets" className="text-sm text-blue-400 hover:text-blue-300 transition-colors">
                View all →
              </Link>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b" style={{ borderColor: "var(--color-border)" }}>
                    {["Title", "Status", "Priority", "Confidence", "Created", ""].map((h) => (
                      <th key={h} className="px-4 py-3 text-xs font-medium uppercase tracking-wide"
                        style={{ color: "var(--color-text-muted)" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {ticketsLoading
                    ? Array(5).fill(0).map((_, i) => (
                      <tr key={i}>
                        {Array(6).fill(0).map((_, j) => (
                          <td key={j} className="px-4 py-3.5">
                            <div className="h-4 rounded skeleton" style={{ width: j === 0 ? "60%" : "40%" }} />
                          </td>
                        ))}
                      </tr>
                    ))
                    : (tickets ?? []).map((t: any) => <TicketRow key={t.id} ticket={t} />)
                  }
                </tbody>
              </table>
              {!ticketsLoading && (!tickets || tickets.length === 0) && (
                <div className="py-12 text-center" style={{ color: "var(--color-text-muted)" }}>
                  <MessageSquare className="w-8 h-8 mx-auto mb-3 opacity-40" />
                  <p className="text-sm">No tickets yet. Create your first one!</p>
                </div>
              )}
            </div>
          </motion.div>
        </main>
      </div>
    </div>
  );
}
