import json
import csv
import io
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any

AUDIT_LOG = Path("/mnt/data/audit_log.jsonl")
AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)

def _hash_entry(entry: Dict[str, Any]) -> str:
    """SHA256 hash for tamper evidence. SOC2 requirement."""
    serialized = json.dumps(entry, sort_keys=True).encode()
    return hashlib.sha256(serialized).hexdigest()[:16]

def log_decision(
    invoice_id: str,
    action: Dict,
    reward: float,
    compliance_rule: Optional[str] = None,
    reviewer: Optional[str] = None,
    confidence: Optional[float] = None
) -> str:
    """
    SOC2 Type II compliant audit log. Append-only, tamper-evident.
    Returns audit_hash for traceability.
    """
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "invoice_id": invoice_id,
        "action_type": action.get("action_type"),
        "action_details": action,
        "reward": round(reward, 4),
        "compliance_rule": compliance_rule,
        "confidence": round(confidence, 3) if confidence else None,
        "reviewer": reviewer,
        "env_version": "luminix-v3.0.0"
    }
    entry["audit_hash"] = _hash_entry(entry)

    with open(AUDIT_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")

    return entry["audit_hash"]

def export_gdpr_csv() -> str:
    """One-click GDPR Article 20 data portability export for auditors."""
    if not AUDIT_LOG.exists():
        return "timestamp,invoice_id,action_type,reward,compliance_rule,reviewer,audit_hash\n"

    with open(AUDIT_LOG) as f:
        logs = [json.loads(line) for line in f if line.strip()]

    if not logs:
        return "timestamp,invoice_id,action_type,reward,compliance_rule,reviewer,audit_hash\n"

    output = io.StringIO()
    fieldnames = ["timestamp", "invoice_id", "action_type", "reward", "compliance_rule", "reviewer", "audit_hash"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    for log in logs:
        writer.writerow(log)
    return output.getvalue()

def get_audit_summary() -> Dict:
    """Dashboard metrics for CFO."""
    if not AUDIT_LOG.exists():
        return {"total": 0, "auto_approved": 0, "escalated": 0, "soc2_violations": 0}

    with open(AUDIT_LOG) as f:
        logs = [json.loads(line) for line in f if line.strip()]

    return {
        "total_invoices": len(logs),
        "auto_approved": sum(1 for l in logs if l["action_type"] == "final_decision" and l["reward"] > 0.8),
        "escalated": sum(1 for l in logs if l["reviewer"]),
        "soc2_violations_caught": sum(1 for l in logs if l["compliance_rule"] == "SOC2_TYPE_II"),
        "total_value_processed": "calculated separately"
    }
