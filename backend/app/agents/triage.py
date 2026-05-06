"""
Triage Agent — classifies intent, priority, language, and initial confidence.
Uses structured output to produce a TriageResult.
Triggers clarification loop if confidence < 0.75.
"""
from __future__ import annotations

import logging
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agents.state import AgentState
from app.config import settings

logger = logging.getLogger(__name__)

TRIAGE_SYSTEM_PROMPT = """You are a triage agent for an Indian e-commerce/SaaS support system.

Analyze the customer's message and classify it.

Intent categories:
- order_status: tracking, where is my order, delivery status
- refund_status: refund timeline, when will I get money back
- invoice_download: GST invoice, bill copy request
- cod_query: cash on delivery questions
- return_request: product return initiation
- payment_issue: failed payment, gateway error
- warranty_claim: product defect, warranty
- account_issue: login, account deactivation
- shipping_delay: delayed delivery, courier issue
- general_query: anything else

Priority (based on urgency and financial impact):
- P1: Critical — financial loss > ₹10,000, legal threat, data breach
- P2: High — financial impact, SLA breach imminent
- P3: Medium — standard support query
- P4: Low — general information request

Language detection: en, hi, hinglish

IMPORTANT: If the user writes in Hinglish (mixed Hindi-English), treat it as valid input.
Focus on intent, not grammar. Common Hinglish markers: kahan, kab, milega, mera, bhai.

Return a JSON object with: intent, priority, language, confidence (0.0-1.0), reasoning."""


class TriageResult(BaseModel):
    intent: str = Field(description="Classified intent category")
    priority: Literal["P1", "P2", "P3", "P4"] = Field(default="P3")
    language: Literal["en", "hi", "hinglish"] = Field(default="en")
    confidence: float = Field(ge=0.0, le=1.0, description="Classification confidence")
    reasoning: str = Field(description="Brief reasoning for classification")


async def triage_node(state: AgentState) -> AgentState:
    """
    Triage agent node. Updates state with intent, priority, language, confidence.
    """
    from langchain_groq import ChatGroq

    from app.core.resilience import CostLimitExceededError

    messages = state["messages"]
    last_user_msg = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)), ""
    )

    prompt_messages = [
        SystemMessage(content=TRIAGE_SYSTEM_PROMPT),
        HumanMessage(content=f"Customer message: {last_user_msg}"),
    ]

    try:
        # Use structured output for reliable classification
        if settings.groq_api_key:
            llm = ChatGroq(
                model=settings.groq_model,
                api_key=settings.groq_api_key,
                temperature=0.0,
            ).with_structured_output(TriageResult)
        else:
            llm = None

        if llm:
            result = await llm.ainvoke(prompt_messages)
        else:
            result = TriageResult(
                intent="general_query", priority="P3",
                language="en", confidence=0.5,
                reasoning="LLM unavailable — default classification"
            )

        # Track LLM call in budget
        state["budget"]["llm_calls_made"] += 1
        state["budget"]["tokens_consumed"] += 200  # estimate for structured call

        state["intent"] = result.intent
        state["priority"] = result.priority
        state["language"] = result.language

        # Use hinglish_detected from InputNormalizer if available
        if state.get("hinglish_detected"):
            state["language"] = "hinglish"

        # Store initial LLM confidence for multi-factor scorer
        state["calibrated_confidence"] = {
            "llm_confidence": result.confidence,
            "rag_relevance_score": 0.0,
            "tool_execution_success": 1.0,
            "historical_accuracy": 0.5,
            "final_score": result.confidence * 0.4 + 0.0 * 0.3 + 1.0 * 0.2 + 0.5 * 0.1,
            "routing_decision": "resolve" if result.confidence >= 0.80 else
                                "kb_retry" if result.confidence >= 0.65 else "escalate",
        }

        logger.info(
            "triage_complete",
            extra={
                "intent": result.intent,
                "priority": result.priority,
                "confidence": result.confidence,
                "language": result.language,
            },
        )

        # Route decision
        if result.confidence >= 0.75:
            state["next_node"] = "supervisor"
        else:
            state["next_node"] = "clarify"

    except CostLimitExceededError as e:
        logger.warning(f"triage_cost_limit: {e}")
        state["budget"]["force_escalated"] = True
        state["escalation_reason"] = f"cost_limit: {e}"
        state["next_node"] = "escalation"
    except Exception as e:
        logger.error(f"triage_failed: {e}")
        # Safe default — don't crash
        state["intent"] = "general_query"
        state["priority"] = "P3"
        state["next_node"] = "supervisor"

    return state
