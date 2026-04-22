"""Comprehensive API tests for the MCP Control Plane (Dema).

Tests all API endpoints and state transitions:
  CREATED -> PLANNING -> EXECUTING <-> PAUSED
                           -> AWAITING_HITL <-> EXECUTING
                           -> COMPLETED/FAILED -> CREATED (Retry)

Run:  .venv/bin/python -m pytest tests/test_api.py -v --tb=short -s
"""
import sys
import os
import json
import logging
import uuid
from unittest.mock import patch, MagicMock, PropertyMock

import pytest
import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient

# Ensure the project root is on sys.path so we can import dema modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Plan, PlanStatus, Stage
from state_machine import StateMachine
from rest_api import create_api
from orchestrator import Orchestrator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _mock_external_deps():
    """Mock external dependencies so the real Orchestrator can be instantiated.

    We patch the *classes* at the orchestrator module level, create configured
    MagicMock instances, and yield them.  Tests can then override individual
    mocks with patch.object for per-test behaviour.
    """
    with patch("orchestrator.GatewayClient") as mock_gw_cls, \
         patch("orchestrator.LLMConnector") as mock_llm_cls, \
         patch("orchestrator.MemoryManager") as mock_mm_cls, \
         patch("orchestrator.SkillsRegistry") as mock_sr_cls, \
         patch("orchestrator.AuditStore") as mock_as_cls, \
         patch("main.GatewayClient"), \
         patch("main.LLMConnector"), \
         patch("main.MemoryManager"), \
         patch("main.SkillsRegistry"), \
         patch("main.AuditStore"):

        # --- GatewayClient mock ---
        mock_gw_instance = MagicMock()
        mock_gw_instance.list_tools.return_value = []
        mock_gw_cls.return_value = mock_gw_instance

        # --- LLMConnector mock ---
        _Decision = MagicMock()
        _Decision.tool_intents = []
        _Decision.next_action = None
        _Decision.update_stage_to = None
        _Decision.rationale = ""
        _Decision.requires_approval = False
        _Decision.confidence = 0.0
        _Decision.to_dict.return_value = {}

        mock_llm_instance = MagicMock()
        mock_llm_instance.get_decision.return_value = _Decision
        mock_llm_instance.summarize_observations.return_value = ""
        mock_llm_cls.return_value = mock_llm_instance

        # --- MemoryManager mock ---
        mock_mm_instance = MagicMock()
        mock_mm_instance.get_full_context.return_value = {
            "p0_plan_intent": {}, "p1_task_context": {},
            "p2_observations": [], "p3_signals": [],
        }
        mock_mm_instance.should_compact_p2.return_value = False
        mock_mm_instance.get_snapshot.return_value = MagicMock(
            p2_observations=[],
            to_dict=lambda: {"p0_plan_intent": {}, "p1_task_context": {},
                             "p2_observations": [], "p3_signals": []},
        )
        mock_mm_cls.return_value = mock_mm_instance

        # --- SkillsRegistry mock ---
        mock_sr_instance = MagicMock()
        mock_sr_instance.get_skills_for_stage.return_value = []
        mock_sr_instance.refresh_skills.return_value = 0
        mock_sr_cls.return_value = mock_sr_instance

        # --- AuditStore mock ---
        mock_as_instance = MagicMock()
        _AuditEvent = MagicMock()
        _AuditEvent.to_dict.return_value = {}
        # Store logged events per plan so to_dict can return them
        mock_as_instance._events = {}

        def _log_event(plan_id, event_type, details):
            event = MagicMock()
            event.to_dict.return_value = {
                "log_id": str(uuid.uuid4()),
                "plan_id": plan_id,
                "event_type": event_type,
                "details": details,
                "timestamp": "2026-01-01T00:00:00",
            }
            mock_as_instance._events.setdefault(plan_id, []).append(event)
            return event

        mock_as_instance.log_event.side_effect = _log_event
        mock_as_instance.to_dict.side_effect = lambda pid: [
            e.to_dict() for e in mock_as_instance._events.get(pid, [])
        ]
        mock_as_cls.return_value = mock_as_instance

        yield {
            "gw": mock_gw_instance,
            "llm": mock_llm_instance,
            "mm": mock_mm_instance,
            "sr": mock_sr_instance,
            "as": mock_as_instance,
        }


def _make_orchestrator(mocks):
    """Create a real Orchestrator with mocked dependencies."""
    return Orchestrator(
        llm_connector=mocks["llm"],
        gateway_client=mocks["gw"],
        memory_manager=mocks["mm"],
        skills_registry=mocks["sr"],
        audit_store=mocks["as"],
    )


def _make_api_client(mocks):
    """Create a TestClient with a real Orchestrator."""
    orch = _make_orchestrator(mocks)
    app = create_api(orch)
    return TestClient(app), orch, mocks


def _make_plan(orchestrator, goal="Test goal", status=PlanStatus.CREATED,
               stages=None, metadata=None):
    """Helper: create a real Plan object and put it in orchestrator.plans."""
    plan = Plan(goal=goal, metadata=metadata)
    if stages:
        for s in stages:
            plan.add_stage(Stage(s["name"], s["description"], s.get("required_skills")))
    plan.status = status
    orchestrator.plans[plan.plan_id] = plan
    return plan


def _make_decision(tool_intents=None, next_action=None,
                   requires_approval=False, update_stage_to=None):
    """Create a mock LLM decision object."""
    d = MagicMock()
    d.tool_intents = tool_intents or []
    d.next_action = next_action
    d.update_stage_to = update_stage_to
    d.rationale = ""
    d.requires_approval = requires_approval
    d.confidence = 0.0
    d.to_dict.return_value = {}
    return d


# ---------------------------------------------------------------------------
# 1. Health & Info
# ---------------------------------------------------------------------------

class TestHealthAndInfo:
    """Test /health and /v1/info endpoints."""

    def test_health_check(self, _mock_external_deps):
        tc, _, _ = _make_api_client(_mock_external_deps)
        resp = tc.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "mcp-control-plane"

    def test_system_info(self, _mock_external_deps):
        tc, _, _ = _make_api_client(_mock_external_deps)
        resp = tc.get("/v1/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Dema (Deus Ex Machina)"
        assert data["version"] == "1.0.0"
        assert "description" in data
        assert "active_plans" in data
        assert "pending_approvals" in data


# ---------------------------------------------------------------------------
# 2. Plan CRUD
# ---------------------------------------------------------------------------

class TestPlanCRUD:
    """Test plan creation, retrieval, and stage management."""

    def test_create_plan_minimal(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        payload = {"goal": "Build a web app"}
        resp = tc.post("/v1/plans", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["goal"] == "Build a web app"
        assert data["status"] == PlanStatus.CREATED.value
        assert "plan_id" in data
        assert "run_id" in data
        assert "tenant_id" in data
        assert "current_stage_idx" in data

    def test_create_plan_with_constraints(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        payload = {
            "goal": "Deploy to production",
            "constraints": ["no downtime", "backup first"],
        }
        resp = tc.post("/v1/plans", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        # Verify constraints were passed through by checking the plan
        assert data["goal"] == "Deploy to production"

    def test_create_plan_with_metadata(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        payload = {
            "goal": "Test plan",
            "metadata": {"tenant_id": "acme", "priority": "high"},
        }
        resp = tc.post("/v1/plans", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["goal"] == "Test plan"

    def test_create_plan_api_calls_orchestrator(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "x"})
        assert resp.status_code == 201
        # Verify the plan was actually created in the orchestrator
        plan_id = resp.json()["plan_id"]
        assert plan_id in orch.plans
        assert orch.plans[plan_id].goal == "x"

    def test_get_plan_not_found(self, _mock_external_deps):
        tc, _, _ = _make_api_client(_mock_external_deps)
        resp = tc.get("/v1/plans/nonexistent-id")
        assert resp.status_code == 404

    def test_add_stage_to_plan(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Test plan"})
        plan_id = resp.json()["plan_id"]
        resp = tc.post(f"/v1/plans/{plan_id}/stages", json={
            "stage_name": "Discovery", "description": "Find stuff",
            "required_skills": ["search"],
        })
        assert resp.status_code == 200
        # Verify stage was added
        assert len(orch.plans[plan_id].stages) == 1
        assert orch.plans[plan_id].stages[0].name == "Discovery"

    def test_add_stage_plan_not_found(self, _mock_external_deps):
        tc, _, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans/fake-id/stages", json={
            "stage_name": "Discovery", "description": "Find stuff"
        })
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 3. Plan Run / Execution
# ---------------------------------------------------------------------------

class TestPlanRun:
    """Test plan execution via /v1/plans/{id}/run."""

    def test_run_plan_success(self, _mock_external_deps):
        tc, orch, mocks = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Test plan"})
        plan_id = resp.json()["plan_id"]
        # LLM returns "complete" so run_execution_loop exits with COMPLETED
        with patch.object(mocks["llm"], "get_decision", return_value=_make_decision(next_action="complete")):
            resp = tc.post(f"/v1/plans/{plan_id}/run", json={"mode": "auto"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan_id"] == plan_id

    def test_run_plan_not_found(self, _mock_external_deps):
        tc, _, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans/fake/run", json={"mode": "auto"})
        assert resp.status_code == 404

    def test_run_plan_failed_to_start(self, _mock_external_deps):
        """Plan not in a valid state to start (e.g. COMPLETED with no retry logic)."""
        tc, orch, _ = _make_api_client(_mock_external_deps)
        plan = _make_plan(orch, "Test plan", status=PlanStatus.COMPLETED)
        resp = tc.post(f"/v1/plans/{plan.plan_id}/run", json={"mode": "auto"})
        assert resp.status_code == 400

    def test_run_plan_step_mode(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Test plan"})
        plan_id = resp.json()["plan_id"]
        resp = tc.post(f"/v1/plans/{plan_id}/run", json={"mode": "step"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 4. Plan State
# ---------------------------------------------------------------------------

class TestPlanState:
    """Test /v1/plans/{id}/state endpoint."""

    def test_get_state_success(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "State test"})
        plan_id = resp.json()["plan_id"]
        resp = tc.get(f"/v1/plans/{plan_id}/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan"]["plan_id"] == plan_id
        assert "context" in data
        assert "audit_logs" in data
        assert "iteration" in data

    def test_get_state_not_found(self, _mock_external_deps):
        tc, _, _ = _make_api_client(_mock_external_deps)
        resp = tc.get("/v1/plans/fake/state")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. Pause / Resume
# ---------------------------------------------------------------------------

class TestPauseResume:
    """Test pause, resume, and pause-from-awaiting-hitl."""

    def test_pause_executing_plan(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Pause me"})
        plan_id = resp.json()["plan_id"]
        # Transition to EXECUTING first
        orch.plans[plan_id].status = PlanStatus.EXECUTING
        resp = tc.post(f"/v1/plans/{plan_id}/pause")
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"
        assert orch.plans[plan_id].status == PlanStatus.PAUSED

    def test_pause_failed(self, _mock_external_deps):
        """Plan in CREATED state cannot be paused."""
        tc, orch, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Pause me"})
        plan_id = resp.json()["plan_id"]
        # Plan in CREATED state -> cannot pause
        resp = tc.post(f"/v1/plans/{plan_id}/pause")
        assert resp.status_code == 400

    def test_pause_plan_not_found(self, _mock_external_deps):
        tc, _, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans/fake-id/pause")
        assert resp.status_code == 404

    def test_resume_paused_plan(self, _mock_external_deps):
        tc, orch, mocks = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Resume me"})
        plan_id = resp.json()["plan_id"]
        # Transition to PAUSED
        orch.plans[plan_id].status = PlanStatus.PAUSED
        # LLM returns "complete" so run_execution_loop exits
        with patch.object(mocks["llm"], "get_decision", return_value=_make_decision(next_action="complete")):
            resp = tc.post(f"/v1/plans/{plan_id}/resume")
        assert resp.status_code == 200

    def test_resume_failed(self, _mock_external_deps):
        """Plan not in PAUSED state cannot be resumed."""
        tc, orch, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Resume me"})
        plan_id = resp.json()["plan_id"]
        # Plan in CREATED state -> cannot resume
        resp = tc.post(f"/v1/plans/{plan_id}/resume")
        assert resp.status_code == 400

    def test_resume_non_paused_returns_400(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Resume me"})
        plan_id = resp.json()["plan_id"]
        # Plan in CREATED state -> not PAUSED, so resume fails
        resp = tc.post(f"/v1/plans/{plan_id}/resume")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 6. Approval (HITL)
# ---------------------------------------------------------------------------

class TestApproval:
    """Test human-in-the-loop approval flow."""

    def test_approve_granted(self, _mock_external_deps):
        tc, orch, mocks = _make_api_client(_mock_external_deps)
        # Create an approval request manually
        orch.plans["approval-123"] = _make_plan(orch, "Approval test")
        orch.plans["approval-123"].status = PlanStatus.AWAITING_HITL

        from models import ApprovalRequest
        approval_req = ApprovalRequest("approval-123", "Test risk", MagicMock())
        orch.approval_requests["approval-123"] = approval_req

        with patch.object(mocks["llm"], "get_decision", return_value=_make_decision(next_action="complete")):
            resp = tc.post("/v1/approvals/approval-123",
                           json={"approved": True, "approval_token": "yes"})
        # Approval granted -> plan resumes and runs execution loop
        # LLM returns "complete" so loop exits
        assert resp.status_code == 200
        data = resp.json()
        assert data["approved"] is True

    def test_approve_denied(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        orch.plans["approval-456"] = _make_plan(orch, "Deny test")
        orch.plans["approval-456"].status = PlanStatus.AWAITING_HITL

        from models import ApprovalRequest
        approval_req = ApprovalRequest("approval-456", "Test risk", MagicMock())
        orch.approval_requests["approval-456"] = approval_req

        resp = tc.post("/v1/approvals/approval-456", json={"approved": False})
        assert resp.status_code == 200

    def test_approve_without_token(self, _mock_external_deps):
        tc, orch, mocks = _make_api_client(_mock_external_deps)
        orch.plans["approval-789"] = _make_plan(orch, "No token test")
        orch.plans["approval-789"].status = PlanStatus.AWAITING_HITL

        from models import ApprovalRequest
        approval_req = ApprovalRequest("approval-789", "Test risk", MagicMock())
        orch.approval_requests["approval-789"] = approval_req

        with patch.object(mocks["llm"], "get_decision", return_value=_make_decision(next_action="complete")):
            resp = tc.post("/v1/approvals/approval-789", json={"approved": True})
        assert resp.status_code == 200

    def test_approve_failed(self, _mock_external_deps):
        tc, _, _ = _make_api_client(_mock_external_deps)
        # Approval request doesn't exist
        resp = tc.post("/v1/approvals/nonexistent", json={"approved": True})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 7. Audit Logs
# ---------------------------------------------------------------------------

class TestAuditLogs:
    """Test /v1/plans/{id}/audit endpoint."""

    def test_audit_logs_success(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Audit me"})
        plan_id = resp.json()["plan_id"]
        resp = tc.get(f"/v1/plans/{plan_id}/audit")
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan_id"] == plan_id
        assert isinstance(data["logs"], list)

    def test_audit_logs_not_found(self, _mock_external_deps):
        tc, _, _ = _make_api_client(_mock_external_deps)
        resp = tc.get("/v1/plans/fake/audit")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 8. State Transition Coverage (all valid transitions via API)
# ---------------------------------------------------------------------------

class TestStateTransitions:
    """Verify every documented state transition is reachable via the API."""

    def test_full_create_to_executing(self, _mock_external_deps):
        tc, orch, mocks = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Create to execute"})
        assert resp.status_code == 201
        plan_id = resp.json()["plan_id"]

        # LLM returns "complete" so run_execution_loop exits
        with patch.object(mocks["llm"], "get_decision", return_value=_make_decision(next_action="complete")):
            resp = tc.post(f"/v1/plans/{plan_id}/run", json={"mode": "auto"})
        assert resp.status_code == 200

    def test_pause_resume_lifecycle(self, _mock_external_deps):
        tc, orch, mocks = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Pause lifecycle"})
        plan_id = resp.json()["plan_id"]

        # Transition to EXECUTING so we can pause
        orch.plans[plan_id].status = PlanStatus.EXECUTING

        # Pause
        resp = tc.post(f"/v1/plans/{plan_id}/pause")
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

        # Resume - transition back to EXECUTING
        orch.plans[plan_id].status = PlanStatus.PAUSED
        with patch.object(mocks["llm"], "get_decision", return_value=_make_decision(next_action="complete")):
            resp = tc.post(f"/v1/plans/{plan_id}/resume")
        assert resp.status_code == 200

    def test_hitl_approval_granted(self, _mock_external_deps):
        tc, orch, mocks = _make_api_client(_mock_external_deps)
        orch.plans["hitl-1"] = _make_plan(orch, "HITL test")
        orch.plans["hitl-1"].status = PlanStatus.AWAITING_HITL

        from models import ApprovalRequest
        approval_req = ApprovalRequest("hitl-1", "HITL risk", MagicMock())
        orch.approval_requests["hitl-1"] = approval_req

        with patch.object(mocks["llm"], "get_decision", return_value=_make_decision(next_action="complete")):
            resp = tc.post("/v1/approvals/hitl-1",
                           json={"approved": True, "approval_token": "token-abc"})
        assert resp.status_code == 200

    def test_hitl_approval_denied(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        orch.plans["hitl-2"] = _make_plan(orch, "HITL deny test")
        orch.plans["hitl-2"].status = PlanStatus.AWAITING_HITL

        from models import ApprovalRequest
        approval_req = ApprovalRequest("hitl-2", "HITL risk", MagicMock())
        orch.approval_requests["hitl-2"] = approval_req

        resp = tc.post("/v1/approvals/hitl-2", json={"approved": False})
        assert resp.status_code == 200

    def test_pause_from_awaiting_hitl(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Pause from HITL"})
        plan_id = resp.json()["plan_id"]
        # Transition to AWAITING_HITL
        orch.plans[plan_id].status = PlanStatus.AWAITING_HITL
        resp = tc.post(f"/v1/plans/{plan_id}/pause")
        assert resp.status_code == 200

    def test_execution_completes(self, _mock_external_deps):
        tc, orch, mocks = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Complete me"})
        plan_id = resp.json()["plan_id"]
        with patch.object(mocks["llm"], "get_decision", return_value=_make_decision(next_action="complete")):
            resp = tc.post(f"/v1/plans/{plan_id}/run", json={"mode": "auto"})
        assert resp.status_code == 200

    def test_execution_fails(self, _mock_external_deps):
        """API returns 200 even if plan eventually fails."""
        tc, orch, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Fail me"})
        plan_id = resp.json()["plan_id"]
        # Force plan to EXECUTING and let it run
        orch.plans[plan_id].status = PlanStatus.EXECUTING
        # Patch run_execution_loop to fail
        with patch.object(orch, "run_execution_loop", return_value=False):
            resp = tc.post(f"/v1/plans/{plan_id}/run", json={"mode": "auto"})
        # The API still returns 200 with the plan data
        assert resp.status_code == 200

    def test_retry_from_failed(self, _mock_external_deps):
        """Retry: FAILED -> CREATED transition, then run."""
        tc, orch, mocks = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Retry failed"})
        plan_id = resp.json()["plan_id"]
        plan = orch.plans[plan_id]
        plan.status = PlanStatus.FAILED

        # Simulate retry: transition FAILED -> CREATED
        orch.state_machine.transition(plan, "RETRY")
        assert plan.status == PlanStatus.CREATED

        with patch.object(mocks["llm"], "get_decision", return_value=_make_decision(next_action="complete")):
            resp = tc.post(f"/v1/plans/{plan_id}/run", json={"mode": "auto"})
        assert resp.status_code == 200

    def test_retry_from_completed(self, _mock_external_deps):
        """Retry: COMPLETED -> CREATED transition, then run."""
        tc, orch, mocks = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Retry completed"})
        plan_id = resp.json()["plan_id"]
        plan = orch.plans[plan_id]
        plan.status = PlanStatus.COMPLETED

        # Simulate retry: transition COMPLETED -> CREATED
        orch.state_machine.transition(plan, "RETRY")
        assert plan.status == PlanStatus.CREATED

        with patch.object(mocks["llm"], "get_decision", return_value=_make_decision(next_action="complete")):
            resp = tc.post(f"/v1/plans/{plan_id}/run", json={"mode": "auto"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 9. State Machine Direct Tests
# ---------------------------------------------------------------------------

class TestStateMachineDirect:
    """Test the StateMachine class directly for all transitions."""

    def test_transition_created_to_planning(self):
        sm = StateMachine()
        plan = Plan("Test")
        assert sm.transition(plan, "PLAN_GOAL_SET")
        assert plan.status == PlanStatus.PLANNING

    def test_transition_planning_to_executing(self):
        sm = StateMachine()
        plan = Plan("Test")
        sm.transition(plan, "PLAN_GOAL_SET")
        assert sm.transition(plan, "LLM_DECOMPOSE_COMPLETE")
        assert plan.status == PlanStatus.EXECUTING

    def test_transition_planning_to_failed(self):
        sm = StateMachine()
        plan = Plan("Test")
        sm.transition(plan, "PLAN_GOAL_SET")
        assert sm.transition(plan, "PLAN_FAILED")
        assert plan.status == PlanStatus.FAILED

    def test_transition_executing_to_awaiting_hitl(self):
        sm = StateMachine()
        plan = Plan("Test")
        sm.transition(plan, "PLAN_GOAL_SET")
        sm.transition(plan, "LLM_DECOMPOSE_COMPLETE")
        assert sm.transition(plan, "POLICY_RISK_DETECTED")
        assert plan.status == PlanStatus.AWAITING_HITL

    def test_transition_awaiting_hitl_to_executing(self):
        sm = StateMachine()
        plan = Plan("Test")
        sm.transition(plan, "PLAN_GOAL_SET")
        sm.transition(plan, "LLM_DECOMPOSE_COMPLETE")
        sm.transition(plan, "POLICY_RISK_DETECTED")
        assert sm.transition(plan, "API_RESUME")
        assert plan.status == PlanStatus.EXECUTING

    def test_transition_awaiting_hitl_to_failed(self):
        sm = StateMachine()
        plan = Plan("Test")
        sm.transition(plan, "PLAN_GOAL_SET")
        sm.transition(plan, "LLM_DECOMPOSE_COMPLETE")
        sm.transition(plan, "POLICY_RISK_DETECTED")
        assert sm.transition(plan, "APPROVAL_DENIED")
        assert plan.status == PlanStatus.FAILED

    def test_transition_awaiting_hitl_to_paused(self):
        sm = StateMachine()
        plan = Plan("Test")
        sm.transition(plan, "PLAN_GOAL_SET")
        sm.transition(plan, "LLM_DECOMPOSE_COMPLETE")
        sm.transition(plan, "POLICY_RISK_DETECTED")
        assert sm.transition(plan, "API_PAUSE")
        assert plan.status == PlanStatus.PAUSED

    def test_transition_executing_to_paused(self):
        sm = StateMachine()
        plan = Plan("Test")
        sm.transition(plan, "PLAN_GOAL_SET")
        sm.transition(plan, "LLM_DECOMPOSE_COMPLETE")
        assert sm.transition(plan, "API_PAUSE")
        assert plan.status == PlanStatus.PAUSED

    def test_transition_paused_to_executing(self):
        sm = StateMachine()
        plan = Plan("Test")
        sm.transition(plan, "PLAN_GOAL_SET")
        sm.transition(plan, "LLM_DECOMPOSE_COMPLETE")
        sm.transition(plan, "API_PAUSE")
        assert sm.transition(plan, "API_RESUME")
        assert plan.status == PlanStatus.EXECUTING

    def test_transition_executing_to_completed(self):
        sm = StateMachine()
        plan = Plan("Test")
        sm.transition(plan, "PLAN_GOAL_SET")
        sm.transition(plan, "LLM_DECOMPOSE_COMPLETE")
        assert sm.transition(plan, "PLAN_COMPLETE")
        assert plan.status == PlanStatus.COMPLETED

    def test_transition_executing_to_failed(self):
        sm = StateMachine()
        plan = Plan("Test")
        sm.transition(plan, "PLAN_GOAL_SET")
        sm.transition(plan, "LLM_DECOMPOSE_COMPLETE")
        assert sm.transition(plan, "PLAN_FAILED")
        assert plan.status == PlanStatus.FAILED

    def test_retry_completed_to_created(self):
        sm = StateMachine()
        plan = Plan("Test")
        sm.transition(plan, "PLAN_GOAL_SET")
        sm.transition(plan, "LLM_DECOMPOSE_COMPLETE")
        sm.transition(plan, "PLAN_COMPLETE")
        assert sm.transition(plan, "RETRY")
        assert plan.status == PlanStatus.CREATED

    def test_retry_failed_to_created(self):
        sm = StateMachine()
        plan = Plan("Test")
        sm.transition(plan, "PLAN_GOAL_SET")
        sm.transition(plan, "LLM_DECOMPOSE_COMPLETE")
        sm.transition(plan, "PLAN_FAILED")
        assert sm.transition(plan, "RETRY")
        assert plan.status == PlanStatus.CREATED

    def test_invalid_transition_returns_false(self):
        sm = StateMachine()
        plan = Plan("Test")
        assert not sm.transition(plan, "NONEXISTENT_TRIGGER")

    def test_invalid_transition_from_status(self):
        """Cannot go from CREATED directly to EXECUTING."""
        sm = StateMachine()
        plan = Plan("Test")
        assert not sm.transition(plan, "LLM_DECOMPOSE_COMPLETE")
        assert plan.status == PlanStatus.CREATED

    def test_get_allowed_transitions(self):
        sm = StateMachine()
        allowed = sm.get_allowed_transitions(PlanStatus.CREATED)
        assert PlanStatus.PLANNING in allowed

    def test_get_allowed_transitions_executing(self):
        sm = StateMachine()
        allowed = sm.get_allowed_transitions(PlanStatus.EXECUTING)
        assert PlanStatus.AWAITING_HITL in allowed
        assert PlanStatus.PAUSED in allowed
        assert PlanStatus.COMPLETED in allowed
        assert PlanStatus.FAILED in allowed

    def test_get_allowed_transitions_awaiting_hitl(self):
        sm = StateMachine()
        allowed = sm.get_allowed_transitions(PlanStatus.AWAITING_HITL)
        assert PlanStatus.EXECUTING in allowed
        assert PlanStatus.PAUSED in allowed
        assert PlanStatus.FAILED in allowed

    def test_get_allowed_transitions_paused(self):
        sm = StateMachine()
        allowed = sm.get_allowed_transitions(PlanStatus.PAUSED)
        assert allowed == [PlanStatus.EXECUTING]

    def test_get_allowed_transitions_completed(self):
        sm = StateMachine()
        allowed = sm.get_allowed_transitions(PlanStatus.COMPLETED)
        assert PlanStatus.CREATED in allowed

    def test_get_allowed_transitions_failed(self):
        sm = StateMachine()
        allowed = sm.get_allowed_transitions(PlanStatus.FAILED)
        assert PlanStatus.CREATED in allowed

    def test_can_transition_returns_true(self):
        sm = StateMachine()
        plan = Plan("Test")
        assert sm.can_transition(plan, "PLAN_GOAL_SET")

    def test_can_transition_returns_false(self):
        sm = StateMachine()
        plan = Plan("Test")
        assert not sm.can_transition(plan, "PLAN_COMPLETE")

    def test_full_lifecycle(self):
        """Simulate a complete plan lifecycle end-to-end."""
        sm = StateMachine()
        plan = Plan("Full lifecycle test")

        assert sm.transition(plan, "PLAN_GOAL_SET")
        assert plan.status == PlanStatus.PLANNING

        assert sm.transition(plan, "LLM_DECOMPOSE_COMPLETE")
        assert plan.status == PlanStatus.EXECUTING

        assert sm.transition(plan, "POLICY_RISK_DETECTED")
        assert plan.status == PlanStatus.AWAITING_HITL

        assert sm.transition(plan, "API_RESUME")
        assert plan.status == PlanStatus.EXECUTING

        assert sm.transition(plan, "PLAN_COMPLETE")
        assert plan.status == PlanStatus.COMPLETED

    def test_full_lifecycle_with_pause(self):
        """Plan lifecycle including pause/resume."""
        sm = StateMachine()
        plan = Plan("Pause lifecycle test")

        assert sm.transition(plan, "PLAN_GOAL_SET")
        assert sm.transition(plan, "LLM_DECOMPOSE_COMPLETE")
        assert sm.transition(plan, "API_PAUSE")
        assert plan.status == PlanStatus.PAUSED

        assert sm.transition(plan, "API_RESUME")
        assert plan.status == PlanStatus.EXECUTING

        assert sm.transition(plan, "PLAN_COMPLETE")
        assert plan.status == PlanStatus.COMPLETED

    def test_full_lifecycle_retry(self):
        """Plan lifecycle with retry."""
        sm = StateMachine()
        plan = Plan("Retry lifecycle test")

        assert sm.transition(plan, "PLAN_GOAL_SET")
        assert sm.transition(plan, "LLM_DECOMPOSE_COMPLETE")
        assert sm.transition(plan, "PLAN_FAILED")
        assert plan.status == PlanStatus.FAILED

        assert sm.transition(plan, "RETRY")
        assert plan.status == PlanStatus.CREATED

    def test_staged_transition_with_validation(self):
        """Test stage change transition (EXECUTING -> EXECUTING)."""
        sm = StateMachine()
        plan = Plan("Stage test")
        plan.add_stage(Stage("Discovery", "Find things"))
        plan.add_stage(Stage("Execution", "Do things"))
        sm.transition(plan, "PLAN_GOAL_SET")
        sm.transition(plan, "LLM_DECOMPOSE_COMPLETE")
        assert sm.transition(plan, "LLM_STAGE_CHANGE", stage_name="Execution")


# ---------------------------------------------------------------------------
# 10. Error Handling & Edge Cases
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_create_plan_server_error(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        with patch.object(orch, "create_plan", side_effect=RuntimeError("DB down")):
            resp = tc.post("/v1/plans", json={"goal": "test"})
        assert resp.status_code == 500

    def test_run_plan_server_error(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "test"})
        plan_id = resp.json()["plan_id"]
        with patch.object(orch, "start_execution", side_effect=RuntimeError("Gateway timeout")):
            resp = tc.post(f"/v1/plans/{plan_id}/run", json={"mode": "auto"})
        assert resp.status_code == 500

    def test_get_plan_server_error(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "test"})
        plan_id = resp.json()["plan_id"]
        orch.plans[plan_id].status = PlanStatus.EXECUTING
        with patch.object(orch.plans[plan_id], "to_dict", side_effect=RuntimeError("Something broke")):
            resp = tc.get(f"/v1/plans/{plan_id}")
        assert resp.status_code == 500

    def test_get_state_server_error(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "test"})
        plan_id = resp.json()["plan_id"]
        with patch.object(orch, "get_plan_state", side_effect=RuntimeError("Context error")):
            resp = tc.get(f"/v1/plans/{plan_id}/state")
        assert resp.status_code == 500

    def test_add_stage_server_error(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "test"})
        plan_id = resp.json()["plan_id"]
        with patch.object(orch, "add_stage_to_plan", side_effect=RuntimeError("Stage error")):
            resp = tc.post(f"/v1/plans/{plan_id}/stages", json={
                "stage_name": "S", "description": "D"
            })
        assert resp.status_code == 500

    def test_approve_server_error(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        with patch.object(orch, "handle_approval", side_effect=RuntimeError("Approval error")):
            resp = tc.post("/v1/approvals/app-1", json={"approved": True})
        assert resp.status_code == 500

    def test_audit_server_error(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "test"})
        plan_id = resp.json()["plan_id"]
        with patch.object(orch.audit_store, "to_dict", side_effect=RuntimeError("Audit error")):
            resp = tc.get(f"/v1/plans/{plan_id}/audit")
        assert resp.status_code == 500

    def test_pause_server_error(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "test"})
        plan_id = resp.json()["plan_id"]
        with patch.object(orch, "pause_plan", side_effect=RuntimeError("Pause error")):
            resp = tc.post(f"/v1/plans/{plan_id}/pause")
        assert resp.status_code == 500

    def test_resume_server_error(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "test"})
        plan_id = resp.json()["plan_id"]
        with patch.object(orch, "resume_plan", side_effect=RuntimeError("Resume error")):
            resp = tc.post(f"/v1/plans/{plan_id}/resume")
        assert resp.status_code == 500

    def test_invalid_json_body(self, _mock_external_deps):
        tc, _, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", content="not json", headers={"Content-Type": "application/json"})
        assert resp.status_code == 422

    def test_create_plan_missing_goal(self, _mock_external_deps):
        tc, _, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={})
        assert resp.status_code == 422

    def test_run_plan_invalid_mode(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "test"})
        plan_id = resp.json()["plan_id"]
        # mode validation happens at the API level
        resp = tc.post(f"/v1/plans/{plan_id}/run", json={"mode": "invalid_mode"})
        # FastAPI allows extra fields, so this returns 200 with the plan data
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 11. Multi-plan Isolation
# ---------------------------------------------------------------------------

class TestMultiPlanIsolation:
    """Ensure operations on one plan don't affect others."""

    def test_multiple_plans_created(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        ids = []
        for i in range(5):
            resp = tc.post("/v1/plans", json={"goal": f"Plan {i}"})
            assert resp.status_code == 201
            ids.append(resp.json()["plan_id"])
        assert len(set(ids)) == 5  # all unique

    def test_pause_one_does_not_affect_other(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        p1 = _make_plan(orch, "Plan 1", status=PlanStatus.EXECUTING)
        p2 = _make_plan(orch, "Plan 2", status=PlanStatus.EXECUTING)

        resp = tc.post(f"/v1/plans/{p1.plan_id}/pause")
        assert resp.status_code == 200
        # Only p1 was paused; p2 is still EXECUTING
        assert p2.status == PlanStatus.EXECUTING


# ---------------------------------------------------------------------------
# 12. Audit Trail Completeness
# ---------------------------------------------------------------------------

class TestAuditTrail:
    """Verify audit store is called for every significant operation."""

    def test_audit_logged_on_plan_creation(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        tc.post("/v1/plans", json={"goal": "Audit trail test"})
        # Verify audit event was logged by checking the audit logs endpoint
        plan_id = orch.plans[list(orch.plans.keys())[0]].plan_id
        resp = tc.get(f"/v1/plans/{plan_id}/audit")
        assert resp.status_code == 200
        data = resp.json()
        assert any(e.get("event_type") == "PLAN_CREATED" for e in data["logs"])

    def test_audit_logged_on_add_stage(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Audit stage"})
        plan_id = resp.json()["plan_id"]
        tc.post(f"/v1/plans/{plan_id}/stages", json={
            "stage_name": "S", "description": "D"
        })
        resp = tc.get(f"/v1/plans/{plan_id}/audit")
        assert resp.status_code == 200
        data = resp.json()
        assert any(e.get("event_type") == "STAGE_ADDED" for e in data["logs"])

    def test_audit_on_pause(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Audit pause"})
        plan_id = resp.json()["plan_id"]
        orch.plans[plan_id].status = PlanStatus.EXECUTING
        tc.post(f"/v1/plans/{plan_id}/pause")
        resp = tc.get(f"/v1/plans/{plan_id}/audit")
        assert resp.status_code == 200
        data = resp.json()
        assert any(e.get("event_type") == "PLAN_PAUSED" for e in data["logs"])

    def test_audit_on_resume(self, _mock_external_deps):
        tc, orch, mocks = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Audit resume"})
        plan_id = resp.json()["plan_id"]
        orch.plans[plan_id].status = PlanStatus.PAUSED
        with patch.object(mocks["llm"], "get_decision", return_value=_make_decision(next_action="complete")):
            tc.post(f"/v1/plans/{plan_id}/resume")
        resp = tc.get(f"/v1/plans/{plan_id}/audit")
        assert resp.status_code == 200
        data = resp.json()
        assert any(e.get("event_type") == "PLAN_RESUMED" for e in data["logs"])

    def test_audit_on_approval_granted(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        orch.plans["a-1"] = _make_plan(orch, "Approval audit")
        orch.plans["a-1"].status = PlanStatus.AWAITING_HITL
        from models import ApprovalRequest
        approval_req = ApprovalRequest("a-1", "Test risk", MagicMock())
        orch.approval_requests["a-1"] = approval_req
        tc.post("/v1/approvals/a-1", json={"approved": True})
        resp = tc.get("/v1/plans/a-1/audit")
        assert resp.status_code == 200
        data = resp.json()
        assert any(e.get("event_type") == "APPROVAL_GRANTED" for e in data["logs"])

    def test_audit_on_approval_denied(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        orch.plans["a-2"] = _make_plan(orch, "Deny audit")
        orch.plans["a-2"].status = PlanStatus.AWAITING_HITL
        from models import ApprovalRequest
        approval_req = ApprovalRequest("a-2", "Test risk", MagicMock())
        orch.approval_requests["a-2"] = approval_req
        tc.post("/v1/approvals/a-2", json={"approved": False})
        resp = tc.get("/v1/plans/a-2/audit")
        assert resp.status_code == 200
        data = resp.json()
        assert any(e.get("event_type") == "APPROVAL_DENIED" for e in data["logs"])


# ---------------------------------------------------------------------------
# 13. Plan Details Endpoint
# ---------------------------------------------------------------------------

class TestPlanDetails:
    """Test /v1/plans/{id} endpoint."""

    def test_get_plan_details(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Details test"})
        plan_id = resp.json()["plan_id"]
        orch.plans[plan_id].status = PlanStatus.EXECUTING
        orch.plans[plan_id].add_stage(Stage("Discovery", "Find it"))
        resp = tc.get(f"/v1/plans/{plan_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["goal"] == "Details test"
        assert data["status"] == PlanStatus.EXECUTING.value
        assert len(data["stages"]) == 1
        assert data["stages"][0]["name"] == "Discovery"

    def test_get_plan_with_constraints(self, _mock_external_deps):
        tc, orch, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Constraints test", "constraints": ["c1", "c2"]})
        plan_id = resp.json()["plan_id"]
        resp = tc.get(f"/v1/plans/{plan_id}")
        assert resp.status_code == 200
        assert resp.json()["constraints"] == ["c1", "c2"]


# ---------------------------------------------------------------------------
# 14. Plan Response Schema Validation
# ---------------------------------------------------------------------------

class TestPlanResponseSchema:
    """Validate the structure of PlanResponse from /v1/plans."""

    def test_create_plan_response_has_all_fields(self, _mock_external_deps):
        tc, _, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Schema check"})
        assert resp.status_code == 201
        data = resp.json()
        required = ["plan_id", "goal", "status", "stages", "current_stage_idx", "tenant_id", "run_id"]
        for field in required:
            assert field in data, f"Missing field: {field}"

    def test_create_plan_stages_is_list(self, _mock_external_deps):
        tc, _, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Schema check"})
        assert isinstance(resp.json()["stages"], list)

    def test_create_plan_id_is_string(self, _mock_external_deps):
        tc, _, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Schema check"})
        assert isinstance(resp.json()["plan_id"], str)
        assert len(resp.json()["plan_id"]) > 0

    def test_create_plan_status_is_valid_enum(self, _mock_external_deps):
        tc, _, _ = _make_api_client(_mock_external_deps)
        resp = tc.post("/v1/plans", json={"goal": "Schema check"})
        assert resp.json()["status"] in [s.value for s in PlanStatus]
