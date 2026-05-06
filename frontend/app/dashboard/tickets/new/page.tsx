"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { ChevronLeft, Send, AlertCircle, MessageSquare } from "lucide-react";
import axios from "axios";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const PRIORITIES = [
  { value: "P1", label: "P1 — Critical", desc: "SLA: 1 hour", color: "text-red-400" },
  { value: "P2", label: "P2 — High", desc: "SLA: 4 hours", color: "text-amber-400" },
  { value: "P3", label: "P3 — Medium", desc: "SLA: 24 hours", color: "text-blue-400" },
  { value: "P4", label: "P4 — Low", desc: "SLA: 72 hours", color: "text-slate-400" },
];

const QUICK_TEMPLATES = [
  { label: "Order Tracking", desc: "My order has not arrived", fill: { title: "Order not delivered", description: "I placed an order and it has not arrived yet. The tracking shows no updates for the past 3 days. Please help with the status." } },
  { label: "Refund Request", desc: "I need my money back", fill: { title: "Refund not received", description: "I returned the product 10 days ago and the refund has not been credited to my account yet. Kindly initiate the refund immediately." } },
  { label: "GST Invoice", desc: "Download invoice", fill: { title: "GST invoice required", description: "I need the GST invoice for my recent order for accounting purposes. Please send it to my registered email." } },
  { label: "Damaged Product", desc: "Product arrived damaged", fill: { title: "Product damaged in transit", description: "The product I received is damaged. It looks like the packaging was crushed during delivery. I have photos as evidence." } },
];

export default function NewTicketPage() {
  const router = useRouter();
  const [form, setForm] = useState({ title: "", description: "", priority: "P3" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const { data } = await axios.post(`${API}/api/tickets/`, form, { withCredentials: true });
      router.push(`/dashboard/tickets/${data.id}`);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to create ticket. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen" style={{ background: "var(--color-bg-deep)" }}>
      {/* Header */}
      <header className="glass border-b flex items-center gap-4 px-6 py-4 sticky top-0 z-10"
        style={{ borderColor: "var(--color-border)" }}>
        <button onClick={() => router.back()}
          className="p-2 rounded-lg hover:bg-white/[0.06] transition-colors"
          style={{ color: "var(--color-text-secondary)" }}>
          <ChevronLeft className="w-5 h-5" />
        </button>
        <div>
          <h1 className="font-semibold">Create New Ticket</h1>
          <p className="text-xs" style={{ color: "var(--color-text-muted)" }}>
            AI agent will respond within seconds
          </p>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-8">
        {/* Quick templates */}
        <div className="mb-6">
          <p className="text-sm font-medium mb-3" style={{ color: "var(--color-text-secondary)" }}>
            Quick templates
          </p>
          <div className="grid grid-cols-2 gap-2">
            {QUICK_TEMPLATES.map((t) => (
              <button key={t.label}
                onClick={() => setForm({ ...form, ...t.fill })}
                className="glass glass-hover rounded-xl p-3 text-left transition-all group">
                <div className="text-sm font-medium group-hover:text-blue-400 transition-colors">{t.label}</div>
                <div className="text-xs mt-0.5" style={{ color: "var(--color-text-muted)" }}>{t.desc}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Form card */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass rounded-2xl p-6"
          style={{ border: "1px solid var(--color-border)" }}
        >
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Title */}
            <div>
              <label className="block text-sm font-medium mb-1.5"
                style={{ color: "var(--color-text-secondary)" }}>
                Issue Title <span className="text-red-400">*</span>
              </label>
              <input
                type="text" required value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                placeholder="e.g. Order not delivered after 7 days"
                minLength={5} maxLength={500}
                className="w-full px-4 py-3 rounded-xl text-sm outline-none"
                style={{
                  background: "rgba(255,255,255,0.05)",
                  border: "1px solid var(--color-border)",
                  color: "var(--color-text-primary)",
                }}
              />
            </div>

            {/* Description */}
            <div>
              <label className="block text-sm font-medium mb-1.5"
                style={{ color: "var(--color-text-secondary)" }}>
                Description <span className="text-red-400">*</span>
              </label>
              <textarea
                required value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="Describe your issue in detail. Include order IDs, dates, and any error messages you've seen. Hindi/English both accepted."
                rows={5} minLength={10} maxLength={5000}
                className="w-full px-4 py-3 rounded-xl text-sm outline-none resize-none"
                style={{
                  background: "rgba(255,255,255,0.05)",
                  border: "1px solid var(--color-border)",
                  color: "var(--color-text-primary)",
                }}
              />
              <div className="text-xs mt-1 text-right" style={{ color: "var(--color-text-muted)" }}>
                {form.description.length}/5000
              </div>
            </div>

            {/* Priority */}
            <div>
              <label className="block text-sm font-medium mb-2"
                style={{ color: "var(--color-text-secondary)" }}>
                Priority
              </label>
              <div className="grid grid-cols-2 gap-2">
                {PRIORITIES.map((p) => (
                  <button key={p.value} type="button"
                    onClick={() => setForm({ ...form, priority: p.value })}
                    className={`p-3 rounded-xl text-left text-sm transition-all ${
                      form.priority === p.value
                        ? "border-2 border-blue-500" : "border border-transparent"
                    } glass`}>
                    <span className={`font-semibold ${p.color}`}>{p.label}</span>
                    <span className="block text-xs mt-0.5" style={{ color: "var(--color-text-muted)" }}>
                      {p.desc}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {error && (
              <div className="flex items-start gap-2 px-3 py-2.5 rounded-xl text-sm"
                style={{ background: "rgba(239,68,68,0.1)", color: "#f87171", border: "1px solid rgba(239,68,68,0.2)" }}>
                <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                {error}
              </div>
            )}

            <button type="submit" disabled={loading || !form.title || !form.description}
              className="w-full py-3.5 rounded-xl gradient-primary text-white font-semibold flex items-center justify-center gap-2 hover:opacity-90 disabled:opacity-50 transition-all"
              style={{ boxShadow: "0 0 20px rgba(59,130,246,0.3)" }}>
              {loading
                ? <span className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                : <Send className="w-4 h-4" />}
              {loading ? "Submitting…" : "Submit Ticket"}
            </button>
          </form>
        </motion.div>

        {/* Info */}
        <div className="mt-4 flex items-start gap-2 text-xs px-2"
          style={{ color: "var(--color-text-muted)" }}>
          <MessageSquare className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
          <span>
            The AI agent will automatically respond. Simple queries (order tracking, refund status, GST invoice)
            are resolved instantly without any human intervention.
          </span>
        </div>
      </main>
    </div>
  );
}
