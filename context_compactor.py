"""Context Compactor for handling P2 space management."""
import logging
from typing import List, Dict, Any
from models import ToolResult


logger = logging.getLogger(__name__)


class ContextCompactor:
    """Handles context compaction and space management."""
    
    def __init__(self, llm_connector):
        self.llm_connector = llm_connector

    def should_compact(self, observations: List[ToolResult], threshold_tokens: int) -> bool:
        """Check if compaction is needed."""
        total_tokens = sum(obs.token_count for obs in observations)
        return total_tokens > threshold_tokens

    def estimate_token_count(self, text: str) -> int:
        """Estimate token count (simple heuristic: ~1 token per 4 characters)."""
        return len(text) // 4

    def compact_observations(self, observations: List[ToolResult]) -> str:
        """Compact multiple observations into a summary."""
        
        if not observations:
            return "No observations to summarize"
        
        logger.info(f"[Compactor] Compacting {len(observations)} observations")
        
        # Format observations for LLM
        formatted = "Recent observations:\n\n"
        for i, obs in enumerate(observations, 1):
            formatted += f"{i}. {obs.tool_name}: {obs.result}\n"
        
        # Use LLM to summarize
        prompt = f"""Summarize the following observations into concise bullet points that preserve critical information:

{formatted}

Provide a brief, structured summary focusing on key findings and recommendations."""
        
        try:
            summary = self.llm_connector.summarize_observations(observations)
            logger.info(f"[Compactor] Summary token count: {self.estimate_token_count(summary)}")
            return summary
        except Exception as e:
            logger.error(f"[Compactor] Error summarizing: {e}")
            # Fallback to simple summarization
            return self._fallback_summary(observations)

    def _fallback_summary(self, observations: List[ToolResult]) -> str:
        """Fallback summarization without LLM."""
        summary = f"Archived {len(observations)} tool results:\n"
        
        for obs in observations[:10]:  # Limit to first 10
            status = "✓" if obs.status == "success" else "✗"
            summary += f"- {status} {obs.tool_name}: {str(obs.result)[:100]}\n"
        
        if len(observations) > 10:
            summary += f"- ... and {len(observations) - 10} more results\n"
        
        return summary

    def prune_stale_signals(self, signals: List[Dict[str, Any]], ttl_seconds: int) -> List[Dict[str, Any]]:
        """Remove stale signals based on TTL."""
        from datetime import datetime, timedelta
        
        now = datetime.utcnow()
        ttl_delta = timedelta(seconds=ttl_seconds)
        
        active_signals = []
        pruned_count = 0
        
        for signal in signals:
            if "added_at" in signal:
                try:
                    added_at = datetime.fromisoformat(signal["added_at"])
                    if added_at > now - ttl_delta:
                        active_signals.append(signal)
                    else:
                        pruned_count += 1
                except (ValueError, TypeError):
                    active_signals.append(signal)
            else:
                active_signals.append(signal)
        
        if pruned_count > 0:
            logger.debug(f"[Compactor] Pruned {pruned_count} stale signals")
        
        return active_signals
