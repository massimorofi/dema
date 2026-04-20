"""Audit store for logging all events and operations."""
import logging
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from models import AuditLog


logger = logging.getLogger(__name__)


class AuditStore:
    """Store and retrieve audit logs for plans."""
    
    def __init__(self):
        self.logs: Dict[str, List[AuditLog]] = {}

    def log_event(self, plan_id: str, event_type: str, details: Dict[str, Any]) -> AuditLog:
        """Log an event to the audit store."""
        audit_log = AuditLog(plan_id, event_type, details)
        
        if plan_id not in self.logs:
            self.logs[plan_id] = []
        
        self.logs[plan_id].append(audit_log)
        logger.debug(f"[Audit] Plan {plan_id}: {event_type} - {json.dumps(details, default=str)}")
        
        return audit_log

    def get_logs(self, plan_id: str) -> List[AuditLog]:
        """Get all audit logs for a plan."""
        return self.logs.get(plan_id, [])

    def get_logs_by_type(self, plan_id: str, event_type: str) -> List[AuditLog]:
        """Get audit logs filtered by event type."""
        return [log for log in self.logs.get(plan_id, []) if log.event_type == event_type]

    def get_logs_since(self, plan_id: str, since: datetime) -> List[AuditLog]:
        """Get audit logs since a specific time."""
        return [log for log in self.logs.get(plan_id, []) if log.timestamp >= since]

    def clear_logs(self, plan_id: str) -> None:
        """Clear all logs for a plan."""
        if plan_id in self.logs:
            del self.logs[plan_id]
            logger.info(f"[Audit] Cleared logs for plan {plan_id}")

    def to_dict(self, plan_id: str) -> List[Dict[str, Any]]:
        """Convert audit logs to dict format."""
        return [log.to_dict() for log in self.get_logs(plan_id)]
