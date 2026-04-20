"""Tests for the MCP Control Plane."""
import pytest
from models import Plan, PlanStatus, Stage, LLMDecision, ToolResult, ApprovalRequest
from state_machine import StateMachine
from memory_manager import MemoryManager
from audit_store import AuditStore


class TestPlanModel:
    """Test the Plan model."""
    
    def test_plan_creation(self):
        plan = Plan("Test goal", ["Constraint 1"], {"tenant_id": "test"})
        assert plan.goal == "Test goal"
        assert plan.status == PlanStatus.CREATED
        assert plan.tenant_id == "test"
    
    def test_plan_add_stage(self):
        plan = Plan("Test goal")
        stage = Stage("Stage 1", "Test stage")
        plan.add_stage(stage)
        assert len(plan.stages) == 1
        assert plan.current_stage == stage
    
    def test_plan_status_transition(self):
        plan = Plan("Test goal")
        assert plan.update_status(PlanStatus.PLANNING)
        assert plan.status == PlanStatus.PLANNING
        assert plan.update_status(PlanStatus.EXECUTING)
        assert plan.status == PlanStatus.EXECUTING
    
    def test_plan_invalid_transition(self):
        plan = Plan("Test goal")
        # Can't jump directly from CREATED to EXECUTING
        assert not plan.update_status(PlanStatus.EXECUTING)
        assert plan.status == PlanStatus.CREATED


class TestStateMachine:
    """Test the State Machine."""
    
    def test_state_machine_transitions(self):
        sm = StateMachine()
        plan = Plan("Test goal")
        
        # Valid transition
        assert sm.transition(plan, "PLAN_GOAL_SET")
        assert plan.status == PlanStatus.PLANNING
    
    def test_invalid_state_machine_transition(self):
        sm = StateMachine()
        plan = Plan("Test goal")
        
        # Invalid trigger
        assert not sm.transition(plan, "INVALID_TRIGGER")


class TestMemoryManager:
    """Test the Memory Manager."""
    
    def test_memory_snapshot_creation(self):
        mm = MemoryManager()
        plan = Plan("Test goal", metadata={"tenant_id": "test"})
        
        snapshot = mm.create_snapshot(plan, "Discovery")
        assert snapshot is not None
        assert snapshot.p0_plan_intent["goal"] == "Test goal"
        assert snapshot.p1_task_context["current_stage"] == "Discovery"
    
    def test_memory_observation_addition(self):
        mm = MemoryManager()
        plan = Plan("Test goal")
        mm.create_snapshot(plan, "Discovery")
        
        result = ToolResult("test_tool", "success", {"data": "test"})
        mm.add_observation(plan.plan_id, result)
        
        snapshot = mm.get_snapshot(plan.plan_id)
        assert len(snapshot.p2_observations) == 1
    
    def test_memory_signal_addition(self):
        mm = MemoryManager()
        plan = Plan("Test goal")
        mm.create_snapshot(plan, "Discovery")
        
        mm.add_signal(plan.plan_id, {"type": "test_event"})
        
        snapshot = mm.get_snapshot(plan.plan_id)
        assert len(snapshot.p3_signals) == 1
    
    def test_memory_p1_context_clear(self):
        mm = MemoryManager()
        plan = Plan("Test goal")
        mm.create_snapshot(plan, "Discovery")
        
        snapshot = mm.get_snapshot(plan.plan_id)
        assert len(snapshot.p1_task_context) > 0
        
        mm.clear_p1_context(plan.plan_id)
        snapshot = mm.get_snapshot(plan.plan_id)
        assert len(snapshot.p1_task_context) == 0


class TestAuditStore:
    """Test the Audit Store."""
    
    def test_audit_log_event(self):
        store = AuditStore()
        plan_id = "test-plan-123"
        
        store.log_event(plan_id, "TEST_EVENT", {"detail": "value"})
        logs = store.get_logs(plan_id)
        
        assert len(logs) == 1
        assert logs[0].event_type == "TEST_EVENT"
    
    def test_audit_filter_by_type(self):
        store = AuditStore()
        plan_id = "test-plan-123"
        
        store.log_event(plan_id, "EVENT_A", {})
        store.log_event(plan_id, "EVENT_B", {})
        store.log_event(plan_id, "EVENT_A", {})
        
        type_a_logs = store.get_logs_by_type(plan_id, "EVENT_A")
        assert len(type_a_logs) == 2


class TestLLMDecision:
    """Test the LLM Decision model."""
    
    def test_decision_creation(self):
        decision = LLMDecision()
        assert decision.confidence == 0.0
        assert decision.requires_approval == False
    
    def test_decision_with_tools(self):
        decision = LLMDecision()
        decision.tool_intents = [
            {"tool": "tool1", "arguments": {"arg": "value"}},
            {"tool": "tool2", "arguments": {}},
        ]
        
        assert len(decision.tool_intents) == 2


class TestStageModel:
    """Test the Stage model."""
    
    def test_stage_creation(self):
        stage = Stage("Discovery", "Discover data", ["skill1", "skill2"])
        assert stage.name == "Discovery"
        assert len(stage.required_skills) == 2
        assert not stage.completed
    
    def test_stage_completion(self):
        stage = Stage("Discovery", "Discover data")
        stage.completed = True
        assert stage.completed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
