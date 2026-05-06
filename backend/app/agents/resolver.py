"""
Resolver Agent — tool-calling node with retry loop and confidence recalculation.
Uses CostAwareLLM to enforce Invariants 19 and 20.
Builds response_meta on every resolution (Execution Rule 3).
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage

from app.agents.state import AgentState

logger = logging.getLogger(__name__)

RESOLVER_SYSTEM_PROMPT = """You are a resolution agent for an Indian SME support system.
Your job is to resolve customer support tickets using the available tools.

Available tools: get_ticket_details, update_ticket_status, search_kb, send_email, escalate_to_human, translate_text

Rules:
1. Always check ticket details first before taking action
2. Use KB results provided in context — do NOT make up policies
3. For refunds > ₹5000, use escalate_to_human
4. For status updates, use update_ticket_status
5. Always respond in the same language as the customer

Return structured JSON: {"response": "...", "action": "resolve|clarify|escalate", "confidence": 0.0-1.0, "tools_used": [...]}
"""


async def resolver_node(state: AgentState) -> AgentState:
    """
    Resolver with tool-calling loop. Recalculates confidence after tools.
    """
    from app.core.resilience import cost_aware_llm, CostLimitExceededError, AllProvidersExhaustedError
    from app.tools import get_all_tools

    tools = get_all_tools()
    kb_context = _format_kb_context(state.get("kb_results", []))
    fraud_context = _format_fraud_context(state.get("fraud_signals", []))

    system_content = RESOLVER_SYSTEM_PROMPT
    if kb_context:
        system_content += f"\n\nKnowledge Base Context:\n{kb_context}"
    if fraud_context:
        system_content += f"\n\nDomain Alerts:\n{fraud_context}"

    messages = [SystemMessage(content=system_content)] + list(state["messages"])

    tool_success = True
    try:
        response = await cost_aware_llm.ainvoke(
            messages, budget=state["budget"]
        )

        tool_calls_made: list[dict[str, Any]] = []

        # Execute tool calls if any
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                tool_result = await _execute_tool(tc, tools, state)
                tool_calls_made.append(tool_result)
                if not tool_result.get("success"):
                    tool_success = False

            # Update tool log (rolling window of 5)
            state["tool_calls_log"] = (state.get("tool_calls_log", []) + tool_calls_made)[-5:]

        # Extract resolution from response
        resolution_text = getattr(response, "content", "") or ""
        llm_confidence = 0.75  # default

        try:
            if "{" in resolution_text:
                parsed = json.loads(resolution_text[resolution_text.find("{"):resolution_text.rfind("}") + 1])
                resolution_text = parsed.get("response", resolution_text)
                llm_confidence = float(parsed.get("confidence", 0.75))
                action = parsed.get("action", "resolve")
            else:
                action = "resolve"
        except (json.JSONDecodeError, ValueError):
            action = "resolve"

        # Recalculate multi-factor confidence
        from app.core.confidence import confidence_scorer, ConfidenceInputs
        rag_score = max((r.get("score", 0.0) for r in state.get("kb_results", [])), default=0.0)
        inputs = ConfidenceInputs(
            llm_confidence=llm_confidence,
            rag_relevance_score=rag_score,
            tool_execution_success=1.0 if tool_success else 0.0,
            historical_accuracy=(state.get("calibrated_confidence") or {}).get("historical_accuracy", 0.5),
        )
        calibrated = confidence_scorer.compute(inputs)

        state["calibrated_confidence"] = {
            "llm_confidence": llm_confidence,
            "rag_relevance_score": rag_score,
            "tool_execution_success": 1.0 if tool_success else 0.0,
            "historical_accuracy": inputs.historical_accuracy,
            "final_score": calibrated.score,
            "routing_decision": calibrated.routing_decision,
        }

        # Append AI response to messages
        state["messages"] = list(state["messages"]) + [AIMessage(content=resolution_text)]

        # Build response_meta (Execution Rule 3 — MANDATORY)
        state["response_meta"] = _build_response_meta(state, calibrated, action, tool_calls_made)
        state["next_node"] = calibrated.routing_decision

        logger.info(
            "resolver_complete",
            extra={
                "action": action,
                "confidence": calibrated.score,
                "routing": calibrated.routing_decision,
                "tools_called": len(tool_calls_made),
            },
        )

    except CostLimitExceededError as e:
        logger.warning(f"resolver_cost_exceeded: {e}")
        state["budget"]["force_escalated"] = True
        state["budget"]["cost_exceeded"] = True
        state["escalation_reason"] = f"cost_limit: {e.limit_type}"
        state["next_node"] = "escalation"
        # Execution Rule 2: response_meta must reflect this
        state["response_meta"] = {
            "confidence": 0.0,
            "action": "escalate",
            "reason": "System cost limit reached. A human agent will assist you.",
            "step_count": state["budget"]["steps_taken"],
            "fast_path_used": False,
            "tool_calls_summary": [],
            "escalation_reason": str(e),
        }

    except AllProvidersExhaustedError as e:
        logger.error(f"resolver_all_providers_failed: {e}")
        state["escalation_reason"] = "LLM service unavailable — human agent assigned"
        state["next_node"] = "escalation"
        state["response_meta"] = {
            "confidence": 0.0,
            "action": "escalate",
            "reason": "Our AI service is temporarily unavailable. A human agent will help you.",
            "step_count": state["budget"]["steps_taken"],
            "fast_path_used": False,
            "tool_calls_summary": [],
            "escalation_reason": "all_providers_exhausted",
        }

    return state


async def _execute_tool(
    tool_call: Any, tools: dict[str, Any], state: AgentState
) -> dict[str, Any]:
    tool_name = tool_call.get("name", "") if isinstance(tool_call, dict) else getattr(tool_call, "name", "")
    tool_args = tool_call.get("args", {}) if isinstance(tool_call, dict) else getattr(tool_call, "args", {})

    t0 = time.monotonic()
    try:
        tool_fn = tools.get(tool_name)
        if not tool_fn:
            return {"name": tool_name, "success": False, "error": "tool_not_found", "latency_ms": 0}

        result = await tool_fn(ticket_id=state["ticket_id"], **tool_args)
        latency_ms = int((time.monotonic() - t0) * 1000)

        from app.observability.prometheus import tool_call_counter
        tool_call_counter.labels(tool_name=tool_name, status="success").inc()

        return {"name": tool_name, "success": True, "output": str(result)[:500], "latency_ms": latency_ms}
    except Exception as e:
        latency_ms = int((time.monotonic() - t0) * 1000)
        from app.observability.prometheus import tool_call_counter
        tool_call_counter.labels(tool_name=tool_name, status="fail").inc()
        logger.warning(f"tool_execution_failed tool={tool_name}: {e}")
        return {"name": tool_name, "success": False, "error": str(e), "latency_ms": latency_ms}


def _format_kb_context(kb_results: list[dict]) -> str:
    if not kb_results:
        return ""
    parts = []
    for i, r in enumerate(kb_results, 1):
        parts.append(f"[{i}] Source: {r.get('source', 'N/A')}\n{r.get('summary', r.get('text', ''))[:300]}")
    return "\n\n".join(parts)


def _format_fraud_context(fraud_signals: list[dict]) -> str:
    if not fraud_signals:
        return ""
    parts = [f"⚠️ {s.get('rule_name', '')}: {s.get('evidence', '')}" for s in fraud_signals]
    return "\n".join(parts)


def _build_response_meta(
    state: AgentState, calibrated: Any, action: str, tool_calls: list[dict]
) -> dict:
    """Execution Rule 3: ALWAYS build response_meta."""
    action_map = {
        "resolve": "resolve",
        "clarify": "clarify",
        "escalate": "escalate",
        "kb_retry": "clarify",
    }
    final_action = action_map.get(action, "resolve")

    reason_map = {
        "resolve": f"Resolved with {calibrated.score:.0%} confidence.",
        "clarify": "I need more details to resolve this accurately.",
        "escalate": state.get("escalation_reason") or "Complex case requires human review.",
    }

    return {
        "confidence": calibrated.score,
        "action": final_action,
        "reason": reason_map.get(final_action, reason_map["resolve"]),
        "step_count": state["budget"]["steps_taken"],
        "fast_path_used": state.get("fast_path_used", False),
        "tool_calls_summary": [t["name"] for t in tool_calls],
        "escalation_reason": state.get("escalation_reason"),
        "confidence_breakdown": calibrated.breakdown,
    }
