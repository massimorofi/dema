"""Data models for the MCP Control Plane."""
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum
import uuid


class PlanStatus(str, Enum):
    """Status of a Plan."""
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    AWAITING_HITL = "AWAITING_HITL"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Stage:
    """Represents a stage in the Plan."""
    def __init__(self, name: str, description: str, required_skills: List[str] = None):
        self.name = name
        self.description = description
        self.required_skills = required_skills or []
        self.completed = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "required_skills": self.required_skills,
            "completed": self.completed
        }


class Plan:
    """Represents an orchestration Plan."""
    def __init__(self, goal: str, constraints: List[str] = None, metadata: Dict[str, Any] = None):
        self.plan_id = str(uuid.uuid4())
        self.goal = goal
        self.constraints = constraints or []
        self.metadata = metadata or {}
        self.status = PlanStatus.CREATED
        self.stages: List[Stage] = []
        self.current_stage_idx = 0
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.tenant_id = metadata.get("tenant_id", "default") if metadata else "default"
        self.run_id = str(uuid.uuid4())

    @property
    def current_stage(self) -> Optional[Stage]:
        """Get the current stage."""
        if 0 <= self.current_stage_idx < len(self.stages):
            return self.stages[self.current_stage_idx]
        return None

    def update_status(self, new_status: PlanStatus) -> bool:
        """Update plan status according to state machine rules."""
        valid_transitions = {
            PlanStatus.CREATED: [PlanStatus.PLANNING],
            PlanStatus.PLANNING: [PlanStatus.EXECUTING, PlanStatus.FAILED],
            PlanStatus.EXECUTING: [PlanStatus.AWAITING_HITL, PlanStatus.PAUSED, PlanStatus.COMPLETED, PlanStatus.FAILED],
            PlanStatus.AWAITING_HITL: [PlanStatus.EXECUTING, PlanStatus.PAUSED, PlanStatus.FAILED],
            PlanStatus.PAUSED: [PlanStatus.EXECUTING],
            PlanStatus.COMPLETED: [PlanStatus.CREATED],
            PlanStatus.FAILED: [PlanStatus.CREATED],
        }

        if new_status in valid_transitions.get(self.status, []):
            self.status = new_status
            self.updated_at = datetime.utcnow()
            return True
        return False

    def add_stage(self, stage: Stage) -> None:
        """Add a stage to the plan."""
        self.stages.append(stage)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "constraints": self.constraints,
            "metadata": self.metadata,
            "status": self.status.value,
            "stages": [s.to_dict() for s in self.stages],
            "current_stage_idx": self.current_stage_idx,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "tenant_id": self.tenant_id,
            "run_id": self.run_id,
        }


class LLMDecision:
    """Represents a decision from the LLM."""
    def __init__(self):
        self.tool_intents: List[Dict[str, Any]] = []
        self.next_action: Optional[str] = None
        self.update_stage_to: Optional[str] = None
        self.rationale: str = ""
        self.requires_approval: bool = False
        self.confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_intents": self.tool_intents,
            "next_action": self.next_action,
            "update_stage_to": self.update_stage_to,
            "rationale": self.rationale,
            "requires_approval": self.requires_approval,
            "confidence": self.confidence,
        }


class ToolResult:
    """Represents the result of a tool call."""
    def __init__(self, tool_name: str, status: str, result: Any, error: Optional[str] = None):
        self.tool_name = tool_name
        self.status = status
        self.result = result
        self.error = error
        self.timestamp = datetime.utcnow()
        self.token_count = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
            "token_count": self.token_count,
        }


class ApprovalRequest:
    """Represents a request for human approval."""
    def __init__(self, plan_id: str, reason: str, decision: LLMDecision):
        self.approval_id = str(uuid.uuid4())
        self.plan_id = plan_id
        self.reason = reason
        self.decision = decision
        self.created_at = datetime.utcnow()
        self.approved = None
        self.approved_at: Optional[datetime] = None
        self.approval_token: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "plan_id": self.plan_id,
            "reason": self.reason,
            "decision": self.decision.to_dict(),
            "created_at": self.created_at.isoformat(),
            "approved": self.approved,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
        }


class ContextSnapshot:
    """Represents a snapshot of the 4-tier context (P0-P3)."""
    def __init__(self):
        self.p0_plan_intent: Dict[str, Any] = {}  # Plan/Goal
        self.p1_task_context: Dict[str, Any] = {}  # Current Stage/Task
        self.p2_observations: List[ToolResult] = []  # Tool Results
        self.p3_signals: List[Dict[str, Any]] = []  # Ephemeral events
        self.created_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "p0_plan_intent": self.p0_plan_intent,
            "p1_task_context": self.p1_task_context,
            "p2_observations": [o.to_dict() for o in self.p2_observations],
            "p3_signals": self.p3_signals,
            "created_at": self.created_at.isoformat(),
        }


class AuditLog:
    """Represents an audit log entry."""
    def __init__(self, plan_id: str, event_type: str, details: Dict[str, Any]):
        self.log_id = str(uuid.uuid4())
        self.plan_id = plan_id
        self.event_type = event_type
        self.details = details
        self.timestamp = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "log_id": self.log_id,
            "plan_id": self.plan_id,
            "event_type": self.event_type,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }
