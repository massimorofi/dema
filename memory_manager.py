"""Memory Manager for the Context Focus Manager (CFM)."""
import logging
import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from models import ContextSnapshot, ToolResult, Plan


logger = logging.getLogger(__name__)


class MemoryManager:
    """Manages P0-P3 context tiers and compaction."""
    
    def __init__(self, p2_summary_threshold_tokens: int = 2000, p3_ttl_seconds: int = 3600):
        self.p2_summary_threshold_tokens = p2_summary_threshold_tokens
        self.p3_ttl_seconds = p3_ttl_seconds
        self.snapshots: Dict[str, ContextSnapshot] = {}
        self.historical_archives: Dict[str, List[ContextSnapshot]] = {}

    def create_snapshot(self, plan: Plan, current_stage_name: str) -> ContextSnapshot:
        """Create a new context snapshot."""
        snapshot = ContextSnapshot()
        
        # P0: Plan Intent (never evicted)
        snapshot.p0_plan_intent = {
            "goal": plan.goal,
            "constraints": plan.constraints,
            "tenant_id": plan.tenant_id,
            "run_id": plan.run_id,
        }
        
        # P1: Task Context (current stage)
        snapshot.p1_task_context = {
            "current_stage": current_stage_name,
            "stage_index": plan.current_stage_idx,
            "status": plan.status.value,
        }
        
        self.snapshots[plan.plan_id] = snapshot
        return snapshot

    def get_snapshot(self, plan_id: str) -> Optional[ContextSnapshot]:
        """Get the current context snapshot."""
        return self.snapshots.get(plan_id)

    def add_observation(self, plan_id: str, tool_result: ToolResult) -> None:
        """Add a tool result to P2 (Observations)."""
        snapshot = self.snapshots.get(plan_id)
        if not snapshot:
            logger.warning(f"[Memory] No snapshot for plan {plan_id}")
            return
        
        # Estimate token count (simple heuristic: ~1 token per 4 characters)
        result_str = json.dumps(tool_result.to_dict(), default=str)
        token_count = len(result_str) // 4
        tool_result.token_count = token_count
        
        snapshot.p2_observations.append(tool_result)
        logger.debug(f"[Memory] Added observation for {plan_id}: {tool_result.tool_name}")

    def add_signal(self, plan_id: str, signal: Dict[str, Any]) -> None:
        """Add a signal to P3 (Ephemeral events)."""
        snapshot = self.snapshots.get(plan_id)
        if not snapshot:
            logger.warning(f"[Memory] No snapshot for plan {plan_id}")
            return
        
        signal["added_at"] = datetime.utcnow().isoformat()
        snapshot.p3_signals.append(signal)
        logger.debug(f"[Memory] Added signal for {plan_id}")

    def get_p2_token_count(self, plan_id: str) -> int:
        """Calculate total tokens in P2 (Observations)."""
        snapshot = self.snapshots.get(plan_id)
        if not snapshot:
            return 0
        
        return sum(obs.token_count for obs in snapshot.p2_observations)

    def should_compact_p2(self, plan_id: str) -> bool:
        """Check if P2 should be compacted."""
        return self.get_p2_token_count(plan_id) > self.p2_summary_threshold_tokens

    def compact_p2(self, plan_id: str, summary: str) -> None:
        """Compact P2 observations into a summary."""
        snapshot = self.snapshots.get(plan_id)
        if not snapshot:
            logger.warning(f"[Memory] No snapshot for plan {plan_id}")
            return
        
        logger.info(f"[Memory] Compacting P2 for plan {plan_id}. From {len(snapshot.p2_observations)} observations")
        
        # Save current P2 to historical archive
        if plan_id not in self.historical_archives:
            self.historical_archives[plan_id] = []
        
        # Create archive entry
        archive_snapshot = ContextSnapshot()
        archive_snapshot.p0_plan_intent = snapshot.p0_plan_intent
        archive_snapshot.p1_task_context = snapshot.p1_task_context
        archive_snapshot.p2_observations = snapshot.p2_observations
        self.historical_archives[plan_id].append(archive_snapshot)
        
        # Replace P2 with summary
        summary_result = ToolResult(
            tool_name="memory_compactor",
            status="success",
            result=summary,
        )
        snapshot.p2_observations = [summary_result]
        logger.info(f"[Memory] P2 compacted successfully for plan {plan_id}")

    def clean_p3_expired(self, plan_id: str) -> None:
        """Remove expired P3 signals (based on TTL)."""
        snapshot = self.snapshots.get(plan_id)
        if not snapshot:
            return
        
        now = datetime.utcnow()
        ttl_delta = timedelta(seconds=self.p3_ttl_seconds)
        
        original_count = len(snapshot.p3_signals)
        snapshot.p3_signals = [
            sig for sig in snapshot.p3_signals
            if datetime.fromisoformat(sig["added_at"]) > now - ttl_delta
        ]
        
        removed = original_count - len(snapshot.p3_signals)
        if removed > 0:
            logger.debug(f"[Memory] Removed {removed} expired P3 signals for plan {plan_id}")

    def clear_p1_context(self, plan_id: str) -> None:
        """Clear P1 (Task Context) when transitioning stages."""
        snapshot = self.snapshots.get(plan_id)
        if not snapshot:
            logger.warning(f"[Memory] No snapshot for plan {plan_id}")
            return
        
        # Archive current P1 before clearing
        if plan_id not in self.historical_archives:
            self.historical_archives[plan_id] = []
        
        # Snapshot for archival
        archive_snapshot = ContextSnapshot()
        archive_snapshot.p1_task_context = snapshot.p1_task_context
        self.historical_archives[plan_id].append(archive_snapshot)
        
        # Clear P1
        snapshot.p1_task_context = {}
        logger.info(f"[Memory] Cleared P1 context for plan {plan_id}")

    def get_full_context(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """Get the full context snapshot as a dict for LLM."""
        snapshot = self.snapshots.get(plan_id)
        if not snapshot:
            return None
        
        # Clean expired P3 signals
        self.clean_p3_expired(plan_id)
        
        return snapshot.to_dict()

    def inject_approval_token(self, plan_id: str, approval_token: str) -> None:
        """Inject an approval token into P2."""
        snapshot = self.snapshots.get(plan_id)
        if not snapshot:
            logger.warning(f"[Memory] No snapshot for plan {plan_id}")
            return
        
        approval_signal = {
            "approval_token": approval_token,
            "injected_at": datetime.utcnow().isoformat(),
        }
        
        # Add as a special P2 observation
        approval_result = ToolResult(
            tool_name="approval_system",
            status="success",
            result=approval_signal,
        )
        snapshot.p2_observations.append(approval_result)
        logger.info(f"[Memory] Injected approval token for plan {plan_id}")

    def reset_for_plan(self, plan_id: str) -> None:
        """Reset memory for a plan (e.g., on retry)."""
        if plan_id in self.snapshots:
            del self.snapshots[plan_id]
        if plan_id in self.historical_archives:
            del self.historical_archives[plan_id]
        logger.info(f"[Memory] Reset memory for plan {plan_id}")
