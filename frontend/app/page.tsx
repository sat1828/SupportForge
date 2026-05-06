"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import {
  Zap, Shield, Activity, Brain, MessageSquare, ChevronRight,
  BarChart3, Lock, Clock, Layers,
} from "lucide-react";

const FEATURES = [
  {
    icon: <Brain className="w-6 h-6" />,
    title: "LangGraph Multi-Agent",
    desc: "Dynamic StateGraph with conditional routing, retry loops, and confidence-gated escalation.",
    color: "from-blue-500 to-violet-500",
  },
  {
    icon: <Zap className="w-6 h-6" />,
    title: "Deterministic Fast-Path",
    desc: "Regex rule engine resolves 40%+ of tickets in <200ms — zero LLM calls.",
    color: "from-amber-500 to-orange-500",
  },
  {
    icon: <Shield className="w-6 h-6" />,
    title: "9 Fraud Detection Rules",
    desc: "GST mismatch, COD abuse, and refund fraud detection with Indian SME domain intelligence.",
    color: "from-emerald-500 to-teal-500",
  },
  {
    icon: <Activity className="w-6 h-6" />,
    title: "21 Enforced Invariants",
    desc: "Max 10 steps, 10s latency, 5 LLM calls, 5000 tokens per ticket — programmatically enforced.",
    color: "from-rose-500 to-pink-500",
  },
  {
    icon: <Layers className="w-6 h-6" />,
    title: "Hybrid RAG Pipeline",
    desc: "Semantic + BM25 + RRF fusion + cross-encoder reranking. 1.5× boost for human corrections.",
    color: "from-cyan-500 to-blue-500",
  },
  {
    icon: <BarChart3 className="w-6 h-6" />,
    title: "Full Observability",
    desc: "Prometheus metrics, structured audit logs, LangSmith tracing, and 7-day replay system.",
    color: "from-violet-500 to-purple-500",
  },
];

const STATS = [
  { value: "70–80%", label: "Auto-resolution rate" },
  { value: "<200ms", label: "Fast-path latency" },
  { value: "21", label: "Enforced invariants" },
  { value: "100+", label: "Concurrent requests" },
];

export default function HomePage() {
  return (
    <main className="min-h-screen" style={{ background: "var(--color-bg-deep)" }}>
      {/* ── Animated background orbs ───────────────────────── */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div
          className="absolute -top-40 -left-40 w-96 h-96 rounded-full opacity-20 blur-3xl animate-glow-pulse"
          style={{ background: "radial-gradient(circle, #3b82f6, transparent 70%)" }}
        />
        <div
          className="absolute top-1/3 -right-40 w-80 h-80 rounded-full opacity-15 blur-3xl"
          style={{ background: "radial-gradient(circle, #8b5cf6, transparent 70%)", animation: "glow-pulse 4s ease-in-out infinite 2s" }}
        />
        <div
          className="absolute bottom-20 left-1/3 w-64 h-64 rounded-full opacity-10 blur-3xl animate-float"
          style={{ background: "radial-gradient(circle, #06b6d4, transparent 70%)" }}
        />
      </div>

      {/* ── Nav ─────────────────────────────────────────────── */}
      <nav className="relative z-10 flex items-center justify-between px-8 py-5 glass border-b"
        style={{ borderColor: "var(--color-border)" }}>
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl gradient-primary flex items-center justify-center shadow-lg">
            <MessageSquare className="w-5 h-5 text-white" />
          </div>
          <span className="text-xl font-bold tracking-tight">
            Support<span className="gradient-text">Forge</span>
          </span>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/login"
            className="px-4 py-2 text-sm rounded-lg transition-colors"
            style={{ color: "var(--color-text-secondary)" }}>
            Sign in
          </Link>
          <Link href="/dashboard"
            className="px-4 py-2 text-sm rounded-xl gradient-primary text-white font-medium shadow-lg transition-all hover:opacity-90">
            Dashboard →
          </Link>
        </div>
      </nav>

      {/* ── Hero ─────────────────────────────────────────────── */}
      <section className="relative z-10 pt-24 pb-16 px-8 text-center max-w-5xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7 }}
        >
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass mb-8 text-sm"
            style={{ color: "var(--color-text-secondary)", borderColor: "var(--color-border)" }}>
            <span className="w-2 h-2 rounded-full bg-emerald-400 pulse-dot inline-block relative" />
            Production-grade · Free-tier compatible · One-command deploy
          </div>

          <h1 className="text-6xl font-bold leading-tight mb-6 tracking-tight">
            <span className="gradient-text">AI-Powered</span>
            <br />
            Customer Support
          </h1>
          <p className="text-xl max-w-2xl mx-auto mb-10"
            style={{ color: "var(--color-text-secondary)" }}>
            A stateful multi-agent system that resolves{" "}
            <strong style={{ color: "var(--color-text-primary)" }}>70–80% of tickets automatically</strong>{" "}
            using LangGraph, hybrid RAG, and real-time SSE streaming.
          </p>

          <div className="flex items-center justify-center gap-4 flex-wrap">
            <Link href="/dashboard"
              className="group flex items-center gap-2 px-8 py-4 rounded-2xl gradient-primary text-white font-semibold text-lg shadow-lg hover:opacity-90 transition-all"
              style={{ boxShadow: "0 0 30px rgba(59,130,246,0.4)" }}>
              Launch Dashboard
              <ChevronRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
            </Link>
            <a href="https://github.com" target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-2 px-8 py-4 rounded-2xl glass glass-hover text-white font-semibold text-lg">
              View Source
            </a>
          </div>
        </motion.div>

        {/* Stats strip */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.3 }}
          className="mt-20 grid grid-cols-2 md:grid-cols-4 gap-4"
        >
          {STATS.map((s) => (
            <div key={s.label} className="glass rounded-2xl p-5 border-gradient">
              <div className="text-3xl font-bold gradient-text mb-1">{s.value}</div>
              <div className="text-sm" style={{ color: "var(--color-text-secondary)" }}>{s.label}</div>
            </div>
          ))}
        </motion.div>
      </section>

      {/* ── Features grid ───────────────────────────────────── */}
      <section className="relative z-10 px-8 py-16 max-w-6xl mx-auto">
        <motion.h2
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          className="text-4xl font-bold text-center mb-4"
        >
          Built for <span className="gradient-text">production</span>
        </motion.h2>
        <p className="text-center mb-12" style={{ color: "var(--color-text-secondary)" }}>
          Every component is hardened against real-world failure modes
        </p>

        <div className="grid md:grid-cols-3 gap-5">
          {FEATURES.map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.08 }}
              className="glass glass-hover rounded-2xl p-6 group cursor-default"
            >
              <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${f.color} flex items-center justify-center mb-4 text-white shadow-lg group-hover:scale-110 transition-transform`}>
                {f.icon}
              </div>
              <h3 className="font-semibold text-lg mb-2">{f.title}</h3>
              <p className="text-sm leading-relaxed" style={{ color: "var(--color-text-secondary)" }}>{f.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── Architecture callout ─────────────────────────────── */}
      <section className="relative z-10 px-8 py-16 max-w-4xl mx-auto">
        <motion.div
          initial={{ opacity: 0, scale: 0.97 }}
          whileInView={{ opacity: 1, scale: 1 }}
          className="glass rounded-3xl p-10 border-gradient"
          style={{ background: "linear-gradient(135deg, rgba(59,130,246,0.06), rgba(139,92,246,0.06))" }}
        >
          <div className="flex items-start gap-4 mb-6">
            <div className="p-3 rounded-xl" style={{ background: "rgba(59,130,246,0.15)" }}>
              <Lock className="w-6 h-6" style={{ color: "#60a5fa" }} />
            </div>
            <div>
              <h3 className="text-2xl font-bold mb-2">Security by default</h3>
              <p style={{ color: "var(--color-text-secondary)" }}>
                JWT HTTPOnly cookies, bcrypt passwords, prompt injection detection, rate limiting (5 req/min/user), and input sanitization across all 130 test cases.
              </p>
            </div>
          </div>
          <div className="flex gap-3 flex-wrap">
            {["JWT + HttpOnly", "Bcrypt", "Rate Limited", "Injection Guard", "Input Sanitized"].map((tag) => (
              <span key={tag} className="px-3 py-1 rounded-full text-xs font-medium"
                style={{ background: "rgba(59,130,246,0.15)", color: "#60a5fa", border: "1px solid rgba(59,130,246,0.3)" }}>
                {tag}
              </span>
            ))}
          </div>
        </motion.div>
      </section>

      {/* ── Footer ─────────────────────────────────────────── */}
      <footer className="relative z-10 text-center py-10 border-t" style={{ borderColor: "var(--color-border)", color: "var(--color-text-muted)" }}>
        <p className="text-sm">SupportForge · Production-grade AI Agent · Built with LangGraph + FastAPI + Next.js</p>
      </footer>
    </main>
  );
}
