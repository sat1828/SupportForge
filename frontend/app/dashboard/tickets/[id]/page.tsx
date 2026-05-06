"use client";

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useParams, useRouter } from "next/navigation";
import {
  Send, Bot, User, Loader2, AlertTriangle, CheckCircle2,
  Info, Zap, Clock, Shield, ChevronLeft,
} from "lucide-react";
import axios from "axios";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "http://localhost:8000";

interface ResponseMeta {
  confidence: number;
  action: string;
  reason: string;
  step_count: number;
  fast_path_used: boolean;
  tool_calls_summary: string[];
  escalation_reason?: string;
  confidence_breakdown?: Record<string, number>;
}

interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: Date;
  response_meta?: ResponseMeta;
  streaming?: boolean;
}

// ── AI Transparency Banner ─────────────────────────────────
function TransparencyBanner({ meta, streaming }: { meta?: ResponseMeta; streaming: boolean }) {
  if (streaming) {
    return (
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
        className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm mb-2"
        style={{ background: "rgba(59,130,246,0.1)", border: "1px solid rgba(59,130,246,0.2)", color: "#60a5fa" }}>
        <Loader2 className="w-4 h-4 animate-spin" />
        <span>Analyzing your request…</span>
      </motion.div>
    );
  }
  if (!meta) return null;

  const getConfig = () => {
    if (meta.action === "fast_path" || meta.fast_path_used) return {
      icon: <Zap className="w-4 h-4" />, color: "rgba(245,158,11,0.1)",
      border: "rgba(245,158,11,0.25)", text: "#fbbf24",
      label: "Fast resolved (0 LLM calls)",
    };
    if (meta.action === "escalate") return {
      icon: <AlertTriangle className="w-4 h-4" />, color: "rgba(239,68,68,0.1)",
      border: "rgba(239,68,68,0.25)", text: "#f87171",
      label: "Escalated to human agent",
    };
    if (meta.action === "clarify") return {
      icon: <Info className="w-4 h-4" />, color: "rgba(139,92,246,0.1)",
      border: "rgba(139,92,246,0.25)", text: "#a78bfa",
      label: "Needs clarification",
    };
    if (meta.confidence >= 0.8) return {
      icon: <CheckCircle2 className="w-4 h-4" />, color: "rgba(16,185,129,0.1)",
      border: "rgba(16,185,129,0.25)", text: "#34d399",
      label: `Resolved with ${(meta.confidence * 100).toFixed(0)}% confidence`,
    };
    return {
      icon: <Info className="w-4 h-4" />, color: "rgba(59,130,246,0.1)",
      border: "rgba(59,130,246,0.25)", text: "#60a5fa",
      label: `Processing (${(meta.confidence * 100).toFixed(0)}% confidence)`,
    };
  };

  const cfg = getConfig();
  return (
    <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
      className="flex items-start gap-2 px-4 py-2.5 rounded-xl text-xs mb-1"
      style={{ background: cfg.color, border: `1px solid ${cfg.border}`, color: cfg.text }}>
      {cfg.icon}
      <div className="flex-1">
        <span className="font-medium">{cfg.label}</span>
        {meta.step_count > 0 && (
          <span className="ml-2 opacity-70">· {meta.step_count} steps</span>
        )}
        {meta.tool_calls_summary?.length > 0 && (
          <span className="ml-2 opacity-70">· Tools: {meta.tool_calls_summary.join(", ")}</span>
        )}
        {meta.escalation_reason && (
          <span className="block mt-0.5 opacity-80">Reason: {meta.escalation_reason}</span>
        )}
      </div>
      {meta.confidence_breakdown && (
        <div className="flex gap-1 flex-wrap">
          {Object.entries(meta.confidence_breakdown)
            .filter(([k]) => ["llm", "rag", "tool"].includes(k))
            .map(([k, v]) => (
              <span key={k} className="px-1.5 py-0.5 rounded text-xs opacity-70"
                style={{ background: "rgba(255,255,255,0.08)" }}>
                {k}:{((v as number) * 100).toFixed(0)}%
              </span>
            ))}
        </div>
      )}
    </motion.div>
  );
}

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  return (
    <motion.div
      initial={{ opacity: 0, y: 12, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      className={`flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"}`}
    >
      {/* Avatar */}
      <div className={`w-8 h-8 rounded-xl flex-shrink-0 flex items-center justify-center ${isUser
        ? "gradient-primary" : "bg-violet-500/20 border border-violet-500/30"}`}>
        {isUser
          ? <User className="w-4 h-4 text-white" />
          : <Bot className="w-4 h-4 text-violet-400" />}
      </div>

      <div className={`max-w-[75%] ${isUser ? "items-end" : "items-start"} flex flex-col gap-1`}>
        {/* Transparency meta (assistant only) */}
        {!isUser && <TransparencyBanner meta={msg.response_meta} streaming={!!msg.streaming} />}

        <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${isUser
          ? "gradient-primary text-white rounded-tr-sm"
          : "glass rounded-tl-sm"}`}
          style={!isUser ? { border: "1px solid var(--color-border)", color: "var(--color-text-primary)" } : {}}>
          {msg.streaming
            ? <span>{msg.content}<span className="inline-block w-1 h-4 ml-0.5 bg-blue-400 animate-pulse rounded-sm" /></span>
            : msg.content || <Loader2 className="w-4 h-4 animate-spin" style={{ color: "var(--color-text-muted)" }} />
          }
        </div>

        <span className="text-xs px-1" style={{ color: "var(--color-text-muted)" }}>
          {msg.timestamp.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
        </span>
      </div>
    </motion.div>
  );
}

export default function ChatPage() {
  const params = useParams();
  const router = useRouter();
  const ticketId = params.id as string;

  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "Hello! I'm the SupportForge AI agent. How can I help you today? I can assist with orders, refunds, invoices, and more.",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() || isProcessing) return;
    const text = input.trim();
    setInput("");

    // Add user message
    const userMsg: Message = {
      id: crypto.randomUUID(), role: "user", content: text, timestamp: new Date(),
    };
    setMessages((m) => [...m, userMsg]);
    setIsProcessing(true);

    // Add streaming assistant placeholder
    const assistantId = crypto.randomUUID();
    setMessages((m) => [...m, {
      id: assistantId, role: "assistant", content: "", timestamp: new Date(), streaming: true,
    }]);

    try {
      const { data } = await axios.post(
        `${API}/api/agent/chat/${ticketId}`,
        { message: text },
        { withCredentials: true }
      );

      // Fast-path or clarification: immediate response
      if (data.status === "fast_path_resolved" || data.message) {
        setMessages((m) => m.map((msg) =>
          msg.id === assistantId
            ? { ...msg, content: data.message || data.response_meta?.reason || "Done.", streaming: false, response_meta: data.response_meta }
            : msg
        ));
        setIsProcessing(false);
        return;
      }

      // Async job: fetch-based SSE stream (supports cookies)
        const streamUrl = `${API}/api/agent/chat/${ticketId}/stream`;
        eventSourceRef.current = { close: () => { controller?.abort(); } } as any;
        let accumulated = "";
        const controller = new AbortController();

        fetch(streamUrl, { credentials: "include", signal: controller.signal })
          .then(async (resp) => {
            if (!resp.ok || !resp.body) throw new Error("Stream failed");
            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";

            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              buffer += decoder.decode(value, { stream: true });
              const lines = buffer.split("\n");
              buffer = lines.pop() || "";

              let eventType = "message";
              let dataLine = "";
              for (const line of lines) {
                if (line.startsWith("event:")) eventType = line.slice(6).trim();
                if (line.startsWith("data:")) dataLine = line.slice(5).trim();
              }
              if (!dataLine) continue;

              try {
                const payload = JSON.parse(dataLine);
                if (eventType === "chunk") {
                  accumulated += payload.text || "";
                  setMessages((m) => m.map((msg) =>
                    msg.id === assistantId ? { ...msg, content: accumulated } : msg
                  ));
                } else if (eventType === "meta") {
                  setMessages((m) => m.map((msg) =>
                    msg.id === assistantId ? { ...msg, response_meta: payload } : msg
                  ));
                } else if (eventType === "done") {
                  setMessages((m) => m.map((msg) =>
                    msg.id === assistantId
                      ? { ...msg, content: accumulated || "Completed.", streaming: false, response_meta: payload.response_meta || msg.response_meta }
                      : msg
                  ));
                  setIsProcessing(false);
                }
              } catch {
                // ignore parse errors
              }
            }
          })
          .catch(() => {
            setMessages((m) => m.map((msg) =>
              msg.id === assistantId
                ? { ...msg, content: "An error occurred. A human agent will assist you shortly.", streaming: false,
                    response_meta: { confidence: 0, action: "escalate", reason: "Stream error", step_count: 0, fast_path_used: false, tool_calls_summary: [] } }
                : msg
            ));
            setIsProcessing(false);
          });

    } catch (err: any) {
      const errMsg = err.response?.data?.detail || "Failed to process your request.";
      setMessages((m) => m.map((msg) =>
        msg.id === assistantId
          ? { ...msg, content: errMsg, streaming: false }
          : msg
      ));
      setIsProcessing(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  return (
    <div className="min-h-screen flex flex-col" style={{ background: "var(--color-bg-deep)" }}>
      {/* Header */}
      <header className="glass border-b flex items-center gap-4 px-6 py-4 sticky top-0 z-10"
        style={{ borderColor: "var(--color-border)" }}>
        <button onClick={() => router.back()}
          className="p-2 rounded-lg hover:bg-white/[0.06] transition-colors"
          style={{ color: "var(--color-text-secondary)" }}>
          <ChevronLeft className="w-5 h-5" />
        </button>
        <div className="w-10 h-10 rounded-xl bg-violet-500/20 border border-violet-500/30 flex items-center justify-center">
          <Bot className="w-5 h-5 text-violet-400" />
        </div>
        <div>
          <h1 className="font-semibold text-sm">SupportForge AI Agent</h1>
          <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--color-text-muted)" }}>
            <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block pulse-dot relative" />
            <span>Online · Ticket #{ticketId?.slice(0, 8).toUpperCase()}</span>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <div className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full"
            style={{ background: "rgba(16,185,129,0.1)", color: "#34d399", border: "1px solid rgba(16,185,129,0.2)" }}>
            <Shield className="w-3 h-3" /> 21 invariants enforced
          </div>
        </div>
      </header>

      {/* Messages */}
      <main className="flex-1 overflow-y-auto px-4 py-6 max-w-3xl mx-auto w-full space-y-4">
        <AnimatePresence>
          {messages.map((msg) => (
            <MessageBubble key={msg.id} msg={msg} />
          ))}
        </AnimatePresence>
        <div ref={bottomRef} />
      </main>

      {/* Quick suggestions */}
      {messages.length === 1 && (
        <div className="max-w-3xl mx-auto w-full px-4 pb-2">
          <div className="flex flex-wrap gap-2">
            {[
              "Where is my order?", "Refund status kya hai?",
              "Download GST invoice", "COD available?",
            ].map((s) => (
              <button key={s} onClick={() => { setInput(s); }}
                className="px-3 py-1.5 rounded-full text-xs glass glass-hover transition-all"
                style={{ color: "var(--color-text-secondary)" }}>
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <footer className="glass border-t px-4 py-4 sticky bottom-0"
        style={{ borderColor: "var(--color-border)" }}>
        <div className="max-w-3xl mx-auto flex gap-3">
          <div className="flex-1 relative">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Describe your issue… (Hindi/English supported)"
              rows={1}
              disabled={isProcessing}
              className="w-full px-4 py-3 rounded-2xl text-sm resize-none outline-none disabled:opacity-50"
              style={{
                background: "rgba(255,255,255,0.05)",
                border: "1px solid var(--color-border)",
                color: "var(--color-text-primary)",
                maxHeight: "120px",
              }}
            />
            <div className="absolute right-3 bottom-3 flex items-center gap-1">
              <Clock className="w-3 h-3" style={{ color: "var(--color-text-muted)" }} />
              <span className="text-xs" style={{ color: "var(--color-text-muted)" }}>
                {input.length}/1000
              </span>
            </div>
          </div>
          <button
            onClick={sendMessage}
            disabled={!input.trim() || isProcessing}
            className="w-12 h-12 self-end rounded-2xl gradient-primary text-white flex items-center justify-center shadow-lg hover:opacity-90 disabled:opacity-50 transition-all"
            style={{ boxShadow: "0 0 20px rgba(59,130,246,0.3)" }}>
            {isProcessing
              ? <Loader2 className="w-5 h-5 animate-spin" />
              : <Send className="w-5 h-5" />}
          </button>
        </div>
        <p className="text-xs text-center mt-2" style={{ color: "var(--color-text-muted)" }}>
          Powered by LangGraph · Fast-path ≤200ms · Max 10 steps per request
        </p>
      </footer>
    </div>
  );
}
