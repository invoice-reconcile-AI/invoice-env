import requests
import os
import json
from server.models import Invoice
from typing import Optional

def escalate_to_slack(
    invoice: Invoice,
    reasoning: str,
    confidence: float,
    audit_hash: str,
    approval_url: str
):
    """
    Human-in-loop: If confidence < 0.8 or amount > $10K, ping Slack for approval.
    Returns True if escalated, False if auto-approved.
    """
    webhook = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook:
        return False # No webhook = auto-approve

    if confidence >= 0.8 and invoice.total_amount < 10000:
        return False # Auto-approve

    color = "#ff0000" if "VIOLATION" in reasoning or "REJECT" in reasoning else "#ffa500"

    msg = {
        "text": f"Invoice Review: {invoice.invoice_id}",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🚨 Invoice Needs Review"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Invoice:*\n{invoice.invoice_id}"},
                    {"type": "mrkdwn", "text": f"*Vendor:*\n{invoice.vendor_name}"},
                    {"type": "mrkdwn", "text": f"*Amount:*\n${invoice.total_amount:,.2f}"},
                    {"type": "mrkdwn", "text": f"*AI Confidence:*\n{confidence:.0%}"}
                ]
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*AI Reasoning:*\n```{reasoning}```"}
            },
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"Audit Hash: `{audit_hash}` | <{approval_url}|View Details>"}]
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✅ Approve"},
                        "style": "primary",
                        "value": json.dumps({"action": "approve", "audit_hash": audit_hash})
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "❌ Reject"},
                        "style": "danger",
                        "value": json.dumps({"action": "reject", "audit_hash": audit_hash})
                    }
                ]
            }
        ]
    }

    try:
        requests.post(webhook, json=msg, timeout=5)
        return True
    except:
        return False

def check_email_approval(audit_hash: str) -> Optional[str]:
    """Poll for human response. Returns 'approve', 'reject', or None if pending."""
    # In prod: check Redis/DB for Slack button callback
    # For demo: return None
    return None
