"""Stage Gate implementation for managing plan stage transitions."""
import logging
from typing import Optional
from models import Plan, LLMDecision
from memory_manager import MemoryManager
from skills_registry import SkillsRegistry
from audit_store import AuditStore


logger = logging.getLogger(__name__)


class StageGate:
    """Manages stage transitions and context scrubbing."""
    
    def __init__(self, memory_manager: MemoryManager, 
                 skills_registry: SkillsRegistry,
                 audit_store: AuditStore):
        self.memory_manager = memory_manager
        self.skills_registry = skills_registry
        self.audit_store = audit_store

    def can_transition(self, plan: Plan, target_stage_name: str) -> bool:
        """Check if stage transition is valid."""
        if target_stage_name == (plan.current_stage.name if plan.current_stage else None):
            logger.debug(f"[Gate] Already in stage: {target_stage_name}")
            return False
        
        # Verify target stage exists
        stage_names = [s.name for s in plan.stages]
        if target_stage_name not in stage_names:
            logger.error(f"[Gate] Target stage does not exist: {target_stage_name}")
            return False
        
        return True

    def transition_stage(self, plan: Plan, target_stage_name: str, decision: LLMDecision) -> bool:
        """Perform a stage transition with context scrubbing."""
        
        if not self.can_transition(plan, target_stage_name):
            logger.warning(f"[Gate] Cannot transition to stage: {target_stage_name}")
            return False
        
        logger.info(f"[Gate] Transitioning to stage: {target_stage_name}")
        
        # Find the target stage index
        target_idx = next(
            (i for i, s in enumerate(plan.stages) if s.name == target_stage_name),
            -1
        )
        
        if target_idx == -1:
            logger.error(f"[Gate] Stage not found: {target_stage_name}")
            return False
        
        old_stage = plan.current_stage
        old_stage_name = old_stage.name if old_stage else "None"
        
        # Perform "Context Scrub"
        # 1. Archive current P2 (Observations)
        logger.debug(f"[Gate] Archiving P2 observations")
        self.memory_manager.clear_p1_context(plan.plan_id)
        
        # 2. Load skills for new stage
        logger.debug(f"[Gate] Loading skills for new stage")
        new_skills = self.skills_registry.get_skills_for_stage(target_stage_name)
        logger.info(f"[Gate] Found {len(new_skills)} skills for stage: {target_stage_name}")
        
        # 3. Update plan state
        plan.current_stage_idx = target_idx
        
        # 4. Create new P1 context
        current_stage = plan.current_stage
        if current_stage:
            stage_context = {
                "stage_name": target_stage_name,
                "description": current_stage.description,
                "required_skills": current_stage.required_skills,
                "available_skills": [s.get("name") for s in new_skills],
            }
            
            snapshot = self.memory_manager.get_snapshot(plan.plan_id)
            if snapshot:
                snapshot.p1_task_context = stage_context
        
        # 5. Log the transition
        self.audit_store.log_event(
            plan.plan_id,
            "STAGE_TRANSITION",
            {
                "from_stage": old_stage_name,
                "to_stage": target_stage_name,
                "rationale": decision.rationale,
                "skill_count": len(new_skills),
            }
        )
        
        logger.info(f"[Gate] Stage transition completed: {old_stage_name} -> {target_stage_name}")
        return True

    def mark_stage_complete(self, plan: Plan) -> bool:
        """Mark current stage as complete."""
        current_stage = plan.current_stage
        
        if not current_stage:
            logger.warning(f"[Gate] No current stage to complete")
            return False
        
        current_stage.completed = True
        
        self.audit_store.log_event(
            plan.plan_id,
            "STAGE_COMPLETED",
            {
                "stage": current_stage.name,
            }
        )
        
        logger.info(f"[Gate] Marked stage as complete: {current_stage.name}")
        return True

    def get_stage_instructions(self, plan: Plan) -> str:
        """Get task instructions for current stage."""
        current_stage = plan.current_stage
        
        if not current_stage:
            return "No active stage"
        
        # Build instructions from stage info and available skills
        available_skills = self.skills_registry.get_skills_for_stage(current_stage.name)
        
        instructions = f"""
## Stage: {current_stage.name}

### Objective
{current_stage.description}

### Required Skills
{', '.join(current_stage.required_skills) if current_stage.required_skills else 'None specified'}

### Available Tools via Gateway
"""
        
        for skill in available_skills:
            skill_name = skill.get("name", "Unknown")
            skill_desc = skill.get("description", "No description")
            instructions += f"- **{skill_name}**: {skill_desc}\n"
        
        return instructions
