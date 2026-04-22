"""Orchestrator for managing the Plan execution loop."""
import logging
import json
from typing import Optional, Callable
from models import Plan, PlanStatus, Stage, ToolResult, ApprovalRequest
from state_machine import StateMachine
from memory_manager import MemoryManager
from gateway_client import GatewayClient
from llm_connector import LLMConnector
from stage_gate import StageGate
from skills_registry import SkillsRegistry
from audit_store import AuditStore


logger = logging.getLogger(__name__)


class Orchestrator:
    """Main orchestration engine for plan execution."""
    
    def __init__(self, 
                 llm_connector: LLMConnector,
                 gateway_client: GatewayClient,
                 memory_manager: MemoryManager,
                 skills_registry: SkillsRegistry,
                 audit_store: AuditStore):
        self.llm_connector = llm_connector
        self.gateway_client = gateway_client
        self.memory_manager = memory_manager
        self.skills_registry = skills_registry
        self.audit_store = audit_store
        self.state_machine = StateMachine()
        self.stage_gate = StageGate(memory_manager, skills_registry, audit_store)
        
        self.plans: dict = {}
        self.approval_requests: dict = {}
        self.approval_callbacks: dict = {}  # Callbacks for test/external approval
        self.max_iterations = 50
        self.iteration_count: dict = {}

    def create_plan(self, goal: str, constraints: list = None, metadata: dict = None) -> Plan:
        """Create a new orchestration plan."""
        plan = Plan(goal, constraints, metadata)
        self.plans[plan.plan_id] = plan
        
        self.audit_store.log_event(
            plan.plan_id,
            "PLAN_CREATED",
            {"goal": goal, "constraints": constraints}
        )
        
        logger.info(f"[Orchestrator] Created plan: {plan.plan_id}")
        return plan

    def add_stage_to_plan(self, plan_id: str, stage_name: str, description: str, 
                          required_skills: list = None) -> Optional[Stage]:
        """Add a stage to a plan."""
        plan = self.plans.get(plan_id)
        if not plan:
            logger.error(f"[Orchestrator] Plan not found: {plan_id}")
            return None
        
        stage = Stage(stage_name, description, required_skills)
        plan.add_stage(stage)
        
        self.audit_store.log_event(
            plan_id,
            "STAGE_ADDED",
            {"stage_name": stage_name, "description": description}
        )
        
        logger.debug(f"[Orchestrator] Added stage '{stage_name}' to plan {plan_id}")
        return stage

    def decompose_plan(self, plan_id: str) -> bool:
        """Use LLM to decompose the goal into stages."""
        plan = self.plans.get(plan_id)
        if not plan:
            logger.error(f"[Orchestrator] Plan not found: {plan_id}")
            return False
        
        if plan.status != PlanStatus.PLANNING:
            logger.warning(f"[Orchestrator] Plan not in PLANNING state: {plan.status}")
            return False
        
        logger.info(f"[Orchestrator] Decomposing plan: {plan_id}")
        
        # Prepare context for decomposition
        context = {
            "goal": plan.goal,
            "constraints": plan.constraints,
            "task": "Decompose this goal into logical stages. Each stage should be a distinct subsystem of the overall goal.",
        }
        
        # Call LLM for decomposition
        # For now, add some default stages
        # In production, this would use LLM to generate stages
        stages = [
            ("Planning", "Analyze the goal and create a detailed plan", []),
            ("Discovery", "Gather information and resources needed", []),
            ("Execution", "Execute the main tasks", []),
            ("Validation", "Verify the results", []),
            ("Completion", "Finalize and report", []),
        ]
        
        for stage_name, description, skills in stages:
            self.add_stage_to_plan(plan_id, stage_name, description, skills)
        
        self.audit_store.log_event(
            plan_id,
            "PLAN_DECOMPOSED",
            {"stage_count": len(plan.stages)}
        )
        
        logger.info(f"[Orchestrator] Plan decomposed into {len(plan.stages)} stages")
        return True

    def start_execution(self, plan_id: str, mode: str = "auto") -> bool:
        """Start or resume execution of a plan."""
        plan = self.plans.get(plan_id)
        if not plan:
            logger.error(f"[Orchestrator] Plan not found: {plan_id}")
            return False
        
        if plan.status == PlanStatus.CREATED:
            # Need to plan first
            if not self.state_machine.transition(plan, "PLAN_GOAL_SET"):
                logger.error(f"[Orchestrator] Failed to transition plan to PLANNING")
                return False
            
            if not self.decompose_plan(plan_id):
                logger.error(f"[Orchestrator] Failed to decompose plan")
                return False
        
        if plan.status == PlanStatus.PLANNING:
            if not self.state_machine.transition(plan, "LLM_DECOMPOSE_COMPLETE"):
                logger.error(f"[Orchestrator] Failed to transition plan to EXECUTING")
                return False
        
        if plan.status != PlanStatus.EXECUTING:
            logger.warning(f"[Orchestrator] Plan not in EXECUTING state: {plan.status}")
            return False
        
        # Initialize memory snapshot
        current_stage = plan.current_stage
        stage_name = current_stage.name if current_stage else "Unknown"
        self.memory_manager.create_snapshot(plan, stage_name)
        
        # Initialize iteration counter
        self.iteration_count[plan_id] = 0
        
        logger.info(f"[Orchestrator] Starting execution of plan: {plan_id}")
        
        if mode == "auto":
            return self.run_execution_loop(plan_id)
        
        return True

    def run_execution_loop(self, plan_id: str) -> bool:
        """Main execution loop - processes until completion or pause."""
        plan = self.plans.get(plan_id)
        if not plan:
            logger.error(f"[Orchestrator] Plan not found: {plan_id}")
            return False
        
        logger.info(f"[Orchestrator] Execution loop started for plan: {plan_id}")
        
        while plan.status == PlanStatus.EXECUTING:
            self.iteration_count[plan_id] += 1
            iteration = self.iteration_count[plan_id]
            
            if iteration > self.max_iterations:
                logger.error(f"[Orchestrator] Max iterations ({self.max_iterations}) reached")
                self.state_machine.transition(plan, "PLAN_FAILED")
                break
            
            logger.debug(f"[Orchestrator] Iteration {iteration} for plan {plan_id}")
            
            # 1. Gather context
            context = self.memory_manager.get_full_context(plan_id)
            if not context:
                logger.error(f"[Orchestrator] Failed to get context for plan {plan_id}")
                self.state_machine.transition(plan, "PLAN_FAILED")
                break
            
            # Add stage instructions to context
            context["stage_instructions"] = self.stage_gate.get_stage_instructions(plan)
            
            # 2. Get LLM decision
            logger.debug(f"[Orchestrator] Requesting LLM decision")
            decision = self.llm_connector.get_decision(context)
            
            self.audit_store.log_event(
                plan_id,
                "LLM_DECISION",
                {
                    "iteration": iteration,
                    "next_action": decision.next_action,
                    "tool_count": len(decision.tool_intents),
                    "requires_approval": decision.requires_approval,
                    "confidence": decision.confidence,
                }
            )
            
            # 3. Check for memory compaction
            if self.memory_manager.should_compact_p2(plan_id):
                logger.info(f"[Orchestrator] Compacting P2 observations")
                summary = self.llm_connector.summarize_observations(
                    self.memory_manager.get_snapshot(plan_id).p2_observations
                )
                self.memory_manager.compact_p2(plan_id, summary)
            
            # 4. Policy & Risk Check
            if decision.requires_approval:
                logger.warning(f"[Orchestrator] Decision requires approval")
                approval_req = ApprovalRequest(plan_id, "High-risk decision", decision)
                self.approval_requests[approval_req.approval_id] = approval_req
                
                if not self.state_machine.transition(plan, "POLICY_RISK_DETECTED"):
                    logger.error(f"[Orchestrator] Failed to transition to AWAITING_HITL")
                    break
                
                self.memory_manager.add_signal(
                    plan_id,
                    {
                        "type": "approval_required",
                        "approval_id": approval_req.approval_id,
                        "reason": "High-risk decision detected",
                    }
                )
                
                break  # Pause for HITL
            
            # 5. Gateway Execution
            if decision.tool_intents:
                logger.debug(f"[Orchestrator] Executing {len(decision.tool_intents)} tools")
                results = self.gateway_client.execute_batch(decision.tool_intents)
                
                # Process results
                for result_dict in results:
                    # Convert gateway response to ToolResult
                    if "error" in result_dict:
                        tool_result = ToolResult(
                            tool_name="unknown",
                            status="error",
                            result=None,
                            error=result_dict.get("error", {}).get("message", "Unknown error"),
                        )
                    else:
                        result_data = result_dict.get("result", {})
                        tool_result = ToolResult(
                            tool_name=result_dict.get("params", {}).get("tool", "unknown"),
                            status="success",
                            result=result_data,
                        )
                    
                    self.memory_manager.add_observation(plan_id, tool_result)
                    
                    self.audit_store.log_event(
                        plan_id,
                        "TOOL_EXECUTED",
                        {
                            "iteration": iteration,
                            "tool": tool_result.tool_name,
                            "status": tool_result.status,
                        }
                    )
            
            # 6. Handle stage transitions
            if decision.update_stage_to:
                if self.stage_gate.can_transition(plan, decision.update_stage_to):
                    if self.stage_gate.transition_stage(plan, decision.update_stage_to, decision):
                        # Update LLM-triggered stage with state machine
                        if not self.state_machine.transition(plan, "LLM_STAGE_CHANGE", 
                                                             stage_name=decision.update_stage_to):
                            logger.error(f"[Orchestrator] Failed to transition stage")
                            self.state_machine.transition(plan, "PLAN_FAILED")
                            break
                    else:
                        logger.error(f"[Orchestrator] Stage transition failed")
                        self.state_machine.transition(plan, "PLAN_FAILED")
                        break
            
            # Check for completion
            if decision.next_action and decision.next_action.lower() == "complete":
                logger.info(f"[Orchestrator] Plan marked as complete by LLM")
                if self.state_machine.transition(plan, "PLAN_COMPLETE"):
                    logger.info(f"[Orchestrator] Plan execution completed: {plan_id}")
                break
        
        return plan.status in [PlanStatus.COMPLETED, PlanStatus.AWAITING_HITL, PlanStatus.PAUSED]

    def handle_approval(self, approval_id: str, approved: bool, approval_token: str = None) -> bool:
        """Handle human approval response."""
        approval_req = self.approval_requests.get(approval_id)
        if not approval_req:
            logger.error(f"[Orchestrator] Approval request not found: {approval_id}")
            return False
        
        plan = self.plans.get(approval_req.plan_id)
        if not plan:
            logger.error(f"[Orchestrator] Plan not found: {approval_req.plan_id}")
            return False
        
        plan_id = approval_req.plan_id
        
        if approved:
            logger.info(f"[Orchestrator] Approval granted for {plan_id}")
            approval_req.approved = True
            approval_req.approval_token = approval_token or "approved"
            
            # Inject approval token into context
            self.memory_manager.inject_approval_token(plan_id, approval_req.approval_token)
            
            # Resume execution
            if not self.state_machine.transition(plan, "API_RESUME"):
                logger.error(f"[Orchestrator] Failed to resume plan")
                return False

            self.iteration_count[plan_id] = 0
            self.audit_store.log_event(plan_id, "APPROVAL_GRANTED", {"approval_id": approval_id})

            # Continue execution
            return self.run_execution_loop(plan_id)
        else:
            logger.warning(f"[Orchestrator] Approval denied for {plan_id}")
            approval_req.approved = False
            
            if not self.state_machine.transition(plan, "APPROVAL_DENIED"):
                logger.error(f"[Orchestrator] Failed to transition plan to FAILED")
                return False
            
            self.audit_store.log_event(plan_id, "APPROVAL_DENIED", {"approval_id": approval_id})
            return True

    def pause_plan(self, plan_id: str) -> bool:
        """Pause plan execution via API."""
        plan = self.plans.get(plan_id)
        if not plan:
            logger.error(f"[Orchestrator] Plan not found: {plan_id}")
            return False
        
        if self.state_machine.transition(plan, "API_PAUSE"):
            self.audit_store.log_event(plan_id, "PLAN_PAUSED", {})
            logger.info(f"[Orchestrator] Plan paused: {plan_id}")
            return True
        
        return False

    def resume_plan(self, plan_id: str) -> bool:
        """Resume plan execution via API."""
        plan = self.plans.get(plan_id)
        if not plan:
            logger.error(f"[Orchestrator] Plan not found: {plan_id}")
            return False

        if plan.status == PlanStatus.PAUSED:
            if self.state_machine.transition(plan, "API_RESUME"):
                self.iteration_count[plan_id] = 0
                self.audit_store.log_event(plan_id, "PLAN_RESUMED", {})
                logger.info(f"[Orchestrator] Plan resumed: {plan_id}")
                return self.run_execution_loop(plan_id)

        return False

    def get_plan_state(self, plan_id: str) -> Optional[dict]:
        """Get current plan state."""
        plan = self.plans.get(plan_id)
        if not plan:
            return None
        
        context = self.memory_manager.get_full_context(plan_id)
        
        return {
            "plan": plan.to_dict(),
            "context": context,
            "audit_logs": self.audit_store.to_dict(plan_id),
            "iteration": self.iteration_count.get(plan_id, 0),
        }
