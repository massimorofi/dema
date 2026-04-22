"""State Machine implementation for the MCP Control Plane."""
import logging
from typing import Optional, Callable, Dict, List, Any
from models import Plan, PlanStatus, Stage


logger = logging.getLogger(__name__)


class StateTransition:
    """Represents a state transition rule."""
    def __init__(self, trigger: str, from_status: PlanStatus, to_status: PlanStatus, 
                 action: Optional[Callable] = None, validation: Optional[Callable] = None):
        self.trigger = trigger
        self.from_status = from_status
        self.to_status = to_status
        self.action = action
        self.validation = validation


class StateMachine:
    """Deterministic state machine for Plan lifecycle."""
    
    def __init__(self):
        self.transitions: Dict[str, List[StateTransition]] = {}
        self._setup_transitions()

    def _setup_transitions(self) -> None:
        """Configure all valid state transitions."""
        transitions = [
            StateTransition(
                "PLAN_GOAL_SET",
                PlanStatus.CREATED,
                PlanStatus.PLANNING,
            ),
            StateTransition(
                "LLM_DECOMPOSE_COMPLETE",
                PlanStatus.PLANNING,
                PlanStatus.EXECUTING,
            ),
            StateTransition(
                "PLAN_FAILED",
                PlanStatus.PLANNING,
                PlanStatus.FAILED,
            ),
            StateTransition(
                "LLM_STAGE_CHANGE",
                PlanStatus.EXECUTING,
                PlanStatus.EXECUTING,
                action=self._action_clear_p1_context,
                validation=self._validate_stage_exists,
            ),
            StateTransition(
                "POLICY_RISK_DETECTED",
                PlanStatus.EXECUTING,
                PlanStatus.AWAITING_HITL,
                action=self._action_create_approval,
            ),
            StateTransition(
                "API_PAUSE",
                PlanStatus.EXECUTING,
                PlanStatus.PAUSED,
            ),
            StateTransition(
                "PLAN_COMPLETE",
                PlanStatus.EXECUTING,
                PlanStatus.COMPLETED,
            ),
            StateTransition(
                "PLAN_FAILED",
                PlanStatus.EXECUTING,
                PlanStatus.FAILED,
            ),
            StateTransition(
                "API_RESUME",
                PlanStatus.AWAITING_HITL,
                PlanStatus.EXECUTING,
                action=self._action_inject_approval_token,
            ),
            StateTransition(
                "API_PAUSE",
                PlanStatus.AWAITING_HITL,
                PlanStatus.PAUSED,
            ),
            StateTransition(
                "APPROVAL_DENIED",
                PlanStatus.AWAITING_HITL,
                PlanStatus.FAILED,
            ),
            StateTransition(
                "API_RESUME",
                PlanStatus.PAUSED,
                PlanStatus.EXECUTING,
            ),
            StateTransition(
                "RETRY",
                PlanStatus.COMPLETED,
                PlanStatus.CREATED,
            ),
            StateTransition(
                "RETRY",
                PlanStatus.FAILED,
                PlanStatus.CREATED,
            ),
        ]
        
        for transition in transitions:
            key = f"{transition.trigger}_{transition.from_status.value}"
            if key not in self.transitions:
                self.transitions[key] = []
            self.transitions[key].append(transition)

    def _action_clear_p1_context(self, plan: Plan, **kwargs) -> None:
        """Clear P1 (Task Context) when transitioning stages."""
        logger.info(f"[Plan {plan.plan_id}] Clearing P1 Task Context")
        # This will be tied to the memory manager

    def _action_create_approval(self, plan: Plan, **kwargs) -> None:
        """Create an approval request when risk is detected."""
        logger.info(f"[Plan {plan.plan_id}] Creating approval request")
        # This will be handled by the orchestrator

    def _action_inject_approval_token(self, plan: Plan, **kwargs) -> None:
        """Inject approval token into P2 when resuming from AWAITING_HITL."""
        logger.info(f"[Plan {plan.plan_id}] Injecting approval token into P2")

    def _validate_stage_exists(self, plan: Plan, stage_name: str, **kwargs) -> bool:
        """Validate that the target stage exists in the plan."""
        stage_names = [s.name for s in plan.stages]
        return stage_name in stage_names

    def can_transition(self, plan: Plan, trigger: str, **kwargs) -> bool:
        """Check if a transition is valid."""
        key = f"{trigger}_{plan.status.value}"
        transitions = self.transitions.get(key, [])
        
        if not transitions:
            return False
        
        for transition in transitions:
            if transition.validation:
                if not transition.validation(plan, **kwargs):
                    return False
        
        return True

    def transition(self, plan: Plan, trigger: str, **kwargs) -> bool:
        """Perform a state transition."""
        key = f"{trigger}_{plan.status.value}"
        transitions = self.transitions.get(key, [])
        
        if not transitions:
            logger.warning(f"[Plan {plan.plan_id}] Invalid transition: {trigger} from {plan.status.value}")
            return False
        
        transition = transitions[0]  # Get first matching transition
        
        # Execute validation
        if transition.validation:
            if not transition.validation(plan, **kwargs):
                logger.error(f"[Plan {plan.plan_id}] Validation failed for transition: {trigger}")
                return False
        
        # Perform the transition
        old_status = plan.status
        if plan.update_status(transition.to_status):
            logger.info(f"[Plan {plan.plan_id}] Transitioned: {old_status.value} -> {transition.to_status.value} (trigger: {trigger})")
            
            # Execute action
            if transition.action:
                transition.action(plan, **kwargs)
            
            return True
        
        return False

    def get_allowed_transitions(self, current_status: PlanStatus) -> List[PlanStatus]:
        """Get all allowed next statuses from current status."""
        allowed = set()
        for t_list in self.transitions.values():
            for t in t_list:
                if t.from_status == current_status:
                    allowed.add(t.to_status)
        return list(allowed)
