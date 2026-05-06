"""
Context manager — enforces state compression invariants 4 and 5.
Invariant 4: messages <= MAX_CONTEXT_MESSAGES (6)
Invariant 5: token count <= MAX_CONTEXT_TOKENS (4000)
"""
from __future__ import annotations

import logging

import tiktoken
from langchain_core.messages import BaseMessage, SystemMessage

from app.agents.state import AgentState
from app.config import settings

logger = logging.getLogger(__name__)

# tiktoken encoder for accurate token counting
try:
    _encoder = tiktoken.get_encoding("cl100k_base")
except Exception:
    _encoder = None


def count_tokens(text: str) -> int:
    if _encoder:
        return len(_encoder.encode(text))
    return int(len(text) / 4)  # fallback estimate


def count_messages_tokens(messages: list[BaseMessage]) -> int:
    return sum(count_tokens(getattr(m, "content", "") or "") for m in messages)


class ContextManager:
    """
    Compresses AgentState after every node to prevent state explosion.
    Called as a dedicated node in the graph before checkpointing.
    """

    def compress(self, state: AgentState) -> AgentState:
        state = self._trim_messages(state)
        state = self._compress_kb_results(state)
        state = self._trim_tool_log(state)
        state = self._enforce_token_budget(state)
        return state

    def _trim_messages(self, state: AgentState) -> AgentState:
        msgs = state["messages"]
        max_msgs = settings.max_context_messages

        if len(msgs) <= max_msgs:
            return state

        overflow = msgs[:-max_msgs]
        summary_text = self._summarize_messages(overflow)

        # Replace overflow with compact summary SystemMessage
        state["conversation_summary"] = summary_text
        state["messages"] = [
            SystemMessage(content=f"[Earlier conversation summary]: {summary_text}"),
            *msgs[-max_msgs:],
        ]
        logger.debug(f"context_trimmed: {len(msgs)} → {len(state['messages'])} messages")
        return state

    def _compress_kb_results(self, state: AgentState) -> AgentState:
        results = state.get("kb_results", [])
        max_results = settings.max_kb_results_per_cycle

        if len(results) <= max_results:
            # Even if within limit, strip full text to save tokens
            state["kb_results"] = [
                {
                    "source": r.get("source", ""),
                    "summary": (r.get("text", "") or "")[:300],
                    "score": r.get("score", 0.0),
                    "doc_type": r.get("doc_type", ""),
                }
                for r in results
            ]
            return state

        # Sort by score descending, keep top N
        sorted_results = sorted(results, key=lambda r: r.get("score", 0.0), reverse=True)
        state["kb_results"] = [
            {
                "source": r.get("source", ""),
                "summary": (r.get("text", "") or "")[:300],
                "score": r.get("score", 0.0),
                "doc_type": r.get("doc_type", ""),
            }
            for r in sorted_results[:max_results]
        ]
        return state

    def _trim_tool_log(self, state: AgentState) -> AgentState:
        log = state.get("tool_calls_log", [])
        max_entries = 5
        if len(log) > max_entries:
            state["tool_calls_log"] = log[-max_entries:]
        return state

    def _enforce_token_budget(self, state: AgentState) -> AgentState:
        """Iteratively compress until token budget satisfied."""
        max_iterations = 3
        for _ in range(max_iterations):
            total = count_messages_tokens(state["messages"])
            if total <= settings.max_context_tokens:
                break
            # Force one more trim round
            msgs = state["messages"]
            if len(msgs) <= 2:
                # Can't trim further — truncate last message content
                last = msgs[-1]
                if hasattr(last, "content") and last.content:
                    truncated = last.content[: settings.max_context_tokens * 3]
                    state["messages"][-1] = type(last)(content=truncated)
                break
            state = self._trim_messages(state)

        return state

    @staticmethod
    def _summarize_messages(messages: list[BaseMessage]) -> str:
        """
        Lightweight rule-based summarizer (no LLM call — preserves cost budget).
        Extracts intent + key info from overflow messages.
        """
        parts = []
        for m in messages:
            content = getattr(m, "content", "") or ""
            role = type(m).__name__.replace("Message", "")
            if content:
                parts.append(f"{role}: {content[:150]}")
        return " | ".join(parts) if parts else "Previous conversation context."


# Global singleton
context_manager = ContextManager()
