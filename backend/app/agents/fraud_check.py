"""
Indian SME Domain Intelligence — fraud detection rules.
All decisions are deterministic, auditable, and injected into AgentState.fraud_signals.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

GSTIN_PATTERN = re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"
)


@dataclass
class FraudSignal:
    rule_name: str
    severity: str          # "block" | "review" | "warn"
    evidence: str
    auto_action: str | None = None  # "deny_refund" | "suspend_cod" | "escalate"


@dataclass
class DomainCheckResult:
    fraud_signals: list[FraudSignal] = field(default_factory=list)
    auto_actions: list[str] = field(default_factory=list)
    requires_review: bool = False
    clean: bool = True

    def add_signal(self, signal: FraudSignal) -> None:
        self.fraud_signals.append(signal)
        self.clean = False
        self.requires_review = True
        if signal.auto_action:
            self.auto_actions.append(signal.auto_action)


class IndianSMEDomainRules:
    """
    9 deterministic business rules covering GST, COD, and refund fraud.
    All rules write to audit_log with rule_name + evidence.
    """

    def check_gst_mismatch(self, ticket_data: dict[str, Any]) -> FraudSignal | None:
        # Rule 1: GSTIN format validation
        gstin = ticket_data.get("gstin", "")
        if gstin and not GSTIN_PATTERN.match(gstin.upper()):
            return FraudSignal(
                rule_name="gst_invalid_gstin",
                severity="review",
                evidence=f"GSTIN '{gstin}' does not match regex pattern",
            )

        # Rule 2: Refund > invoice total
        refund_amt = float(ticket_data.get("refund_amount", 0) or 0)
        invoice_amt = float(ticket_data.get("invoice_amount", 0) or 0)
        if invoice_amt > 0 and refund_amt > invoice_amt:
            return FraudSignal(
                rule_name="gst_refund_exceeds_invoice",
                severity="block",
                evidence=f"Refund Rs.{refund_amt} > Invoice Rs.{invoice_amt}",
                auto_action="deny_refund",
            )

        # Rule 3: Invoice date > 2 years
        invoice_date_str = ticket_data.get("invoice_date")
        if invoice_date_str:
            try:
                invoice_date = datetime.fromisoformat(str(invoice_date_str)).replace(tzinfo=UTC)
                if (datetime.now(UTC) - invoice_date) > timedelta(days=730):
                    return FraudSignal(
                        rule_name="gst_invoice_too_old",
                        severity="block",
                        evidence=f"Invoice date {invoice_date.date()} > 2 years old",
                        auto_action="deny_refund",
                    )
            except (ValueError, TypeError):
                pass
        return None

    def check_cod_failure(
        self, ticket_data: dict[str, Any], customer_history: dict[str, Any]
    ) -> FraudSignal | None:
        # Rule 4: >3 COD failures in 30 days
        cod_failures_30d = int(customer_history.get("cod_failures_30d", 0))
        if cod_failures_30d > 3:
            return FraudSignal(
                rule_name="cod_excessive_failures",
                severity="block",
                evidence=f"{cod_failures_30d} COD failures in last 30 days",
                auto_action="suspend_cod",
            )

        # Rule 5: COD remittance pending > 7 days
        remittance_pending_days = int(customer_history.get("remittance_pending_days", 0))
        if remittance_pending_days > 7:
            return FraudSignal(
                rule_name="cod_remittance_overdue",
                severity="review",
                evidence=f"COD remittance pending {remittance_pending_days} days",
            )

        # Rule 6: NDR + customer claims delivered
        if ticket_data.get("ndr_raised") and ticket_data.get("customer_claims_delivered"):
            return FraudSignal(
                rule_name="cod_ndr_delivery_dispute",
                severity="review",
                evidence="NDR raised but customer claims delivery occurred",
                auto_action="escalate",
            )
        return None

    def check_refund_fraud(
        self, ticket_data: dict[str, Any], customer_history: dict[str, Any]
    ) -> FraudSignal | None:
        # Rule 7: >2 refunds in 30 days
        refunds_30d = int(customer_history.get("refunds_30d", 0))
        if refunds_30d > 2:
            return FraudSignal(
                rule_name="refund_excessive_requests",
                severity="review",
                evidence=f"{refunds_30d} refund requests in last 30 days",
            )

        # Rule 8: Digital goods refund after download
        if ticket_data.get("is_digital_good") and ticket_data.get("was_downloaded"):
            return FraudSignal(
                rule_name="refund_digital_post_download",
                severity="block",
                evidence="Digital product already downloaded — refund ineligible",
                auto_action="deny_refund",
            )

        # Rule 9: Shipping address changed after order
        if ticket_data.get("address_changed_post_order"):
            return FraudSignal(
                rule_name="refund_address_change_suspicious",
                severity="review",
                evidence="Shipping address was modified after order placement",
            )
        return None

    def apply_all_rules(
        self,
        ticket_data: dict[str, Any],
        customer_history: dict[str, Any],
    ) -> DomainCheckResult:
        result = DomainCheckResult()

        for check_fn, args in [
            (self.check_gst_mismatch, (ticket_data,)),
            (self.check_cod_failure, (ticket_data, customer_history)),
            (self.check_refund_fraud, (ticket_data, customer_history)),
        ]:
            try:
                signal = check_fn(*args)  # type: ignore[operator]
                if signal:
                    result.add_signal(signal)
                    logger.info(
                        "domain_rule_triggered",
                        extra={"rule": signal.rule_name, "severity": signal.severity},
                    )
            except Exception as e:
                logger.warning(f"domain_rule_check_failed: {e}")

        return result


domain_rules = IndianSMEDomainRules()
