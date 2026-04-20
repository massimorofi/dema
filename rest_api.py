"""REST API for the MCP Control Plane using FastAPI."""
import logging
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from orchestrator import Orchestrator


logger = logging.getLogger(__name__)


# Pydantic models for API requests/responses
class CreatePlanRequest(BaseModel):
    goal: str
    constraints: Optional[list] = None
    metadata: Optional[Dict[str, Any]] = None


class RunPlanRequest(BaseModel):
    mode: str = "auto"  # "auto" or "step"


class ApprovalResponse(BaseModel):
    approved: bool
    approval_token: Optional[str] = None


class AddStageRequest(BaseModel):
    stage_name: str
    description: str
    required_skills: Optional[list] = None


class PlanResponse(BaseModel):
    plan_id: str
    goal: str
    status: str
    stages: Optional[list] = None
    current_stage_idx: int
    tenant_id: str
    run_id: str


class ContextResponse(BaseModel):
    p0_plan_intent: Dict[str, Any]
    p1_task_context: Dict[str, Any]
    p2_observations: list
    p3_signals: list


class StateResponse(BaseModel):
    plan: Dict[str, Any]
    context: Dict[str, Any]
    audit_logs: list
    iteration: int


def create_api(orchestrator: Orchestrator) -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="MCP Control Plane (Dema)",
        description="Deus Ex Machina - Enterprise Orchestration Engine",
        version="1.0.0",
    )
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "service": "mcp-control-plane"}
    
    @app.post("/v1/plans", response_model=PlanResponse, status_code=201)
    async def create_plan(request: CreatePlanRequest):
        """
        Create a new orchestration plan.
        
        - **goal**: The objective of the plan
        - **constraints**: List of constraints or requirements
        - **metadata**: Additional metadata (tenant_id, etc.)
        """
        try:
            plan = orchestrator.create_plan(
                goal=request.goal,
                constraints=request.constraints,
                metadata=request.metadata,
            )
            
            return {
                "plan_id": plan.plan_id,
                "goal": plan.goal,
                "status": plan.status.value,
                "stages": [s.to_dict() for s in plan.stages],
                "current_stage_idx": plan.current_stage_idx,
                "tenant_id": plan.tenant_id,
                "run_id": plan.run_id,
            }
        except Exception as e:
            logger.error(f"[API] Error creating plan: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/v1/plans/{plan_id}/stages")
    async def add_stage(plan_id: str, request: AddStageRequest):
        """Add a stage to an existing plan."""
        try:
            stage = orchestrator.add_stage_to_plan(
                plan_id,
                request.stage_name,
                request.description,
                request.required_skills,
            )
            
            if not stage:
                raise HTTPException(status_code=404, detail="Plan not found")
            
            return {"status": "success", "stage": stage.to_dict()}
        except Exception as e:
            logger.error(f"[API] Error adding stage: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/v1/plans/{plan_id}/run")
    async def run_plan(plan_id: str, request: RunPlanRequest):
        """
        Trigger or resume execution of a plan.
        
        - **mode**: "auto" for continuous execution, "step" for step-by-step
        """
        try:
            plan = orchestrator.plans.get(plan_id)
            if not plan:
                raise HTTPException(status_code=404, detail="Plan not found")
            
            success = orchestrator.start_execution(plan_id, mode=request.mode)
            
            if success:
                return {"status": "executing", "plan_id": plan_id}
            else:
                raise HTTPException(status_code=400, detail="Failed to start execution")
        except Exception as e:
            logger.error(f"[API] Error running plan: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/v1/plans/{plan_id}/state")
    async def get_plan_state(plan_id: str):
        """
        Get the current state of a plan.
        
        Returns P0-P3 context tiers, current stage, and audit logs.
        """
        try:
            state = orchestrator.get_plan_state(plan_id)
            
            if not state:
                raise HTTPException(status_code=404, detail="Plan not found")
            
            return state
        except Exception as e:
            logger.error(f"[API] Error getting plan state: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/v1/plans/{plan_id}")
    async def get_plan(plan_id: str):
        """Get plan details."""
        try:
            plan = orchestrator.plans.get(plan_id)
            
            if not plan:
                raise HTTPException(status_code=404, detail="Plan not found")
            
            return plan.to_dict()
        except Exception as e:
            logger.error(f"[API] Error getting plan: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/v1/plans/{plan_id}/pause")
    async def pause_plan(plan_id: str):
        """Pause plan execution."""
        try:
            success = orchestrator.pause_plan(plan_id)
            
            if success:
                return {"status": "paused", "plan_id": plan_id}
            else:
                raise HTTPException(status_code=400, detail="Failed to pause plan")
        except Exception as e:
            logger.error(f"[API] Error pausing plan: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/v1/plans/{plan_id}/resume")
    async def resume_plan(plan_id: str):
        """Resume paused plan execution."""
        try:
            success = orchestrator.resume_plan(plan_id)
            
            if success:
                return {"status": "executing", "plan_id": plan_id}
            else:
                raise HTTPException(status_code=400, detail="Failed to resume plan")
        except Exception as e:
            logger.error(f"[API] Error resuming plan: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/v1/approvals/{approval_id}")
    async def handle_approval(approval_id: str, request: ApprovalResponse):
        """
        Provide human approval for a high-risk decision.
        
        - **approved**: Boolean approval status
        - **approval_token**: Optional token to include in the context
        """
        try:
            success = orchestrator.handle_approval(
                approval_id,
                request.approved,
                request.approval_token,
            )
            
            if success:
                return {
                    "status": "processed",
                    "approval_id": approval_id,
                    "approved": request.approved,
                }
            else:
                raise HTTPException(status_code=400, detail="Failed to process approval")
        except Exception as e:
            logger.error(f"[API] Error processing approval: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/v1/plans/{plan_id}/audit")
    async def get_audit_logs(plan_id: str):
        """Get audit logs for a plan."""
        try:
            if plan_id not in orchestrator.plans:
                raise HTTPException(status_code=404, detail="Plan not found")
            
            logs = orchestrator.audit_store.to_dict(plan_id)
            return {"plan_id": plan_id, "logs": logs}
        except Exception as e:
            logger.error(f"[API] Error getting audit logs: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/v1/info")
    async def get_system_info():
        """Get system information."""
        return {
            "name": "Dema (Deus Ex Machina)",
            "version": "1.0.0",
            "description": "MCP Control Plane",
            "active_plans": len(orchestrator.plans),
            "pending_approvals": len(orchestrator.approval_requests),
        }
    
    return app
