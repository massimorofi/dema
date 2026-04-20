"""Policy Engine for risk assessment and decision validation."""
import logging
from typing import Dict, Any, Callable, List
from models import LLMDecision, Plan


logger = logging.getLogger(__name__)


class PolicyRule:
    """Represents a single policy rule."""
    
    def __init__(self, name: str, description: str, 
                 check_fn: Callable[[LLMDecision, Plan], bool],
                 severity: str = "warning"):
        self.name = name
        self.description = description
        self.check_fn = check_fn
        self.severity = severity  # "warning", "error", "critical"

    def evaluate(self, decision: LLMDecision, plan: Plan) -> bool:
        """Evaluate if rule is violated (returns True if violated)."""
        try:
            return self.check_fn(decision, plan)
        except Exception as e:
            logger.error(f"[Policy] Error evaluating rule {self.name}: {e}")
            return False


class PolicyEngine:
    """Validates decisions against defined policies."""
    
    def __init__(self):
        self.rules: List[PolicyRule] = []
        self._setup_default_rules()

    def _setup_default_rules(self) -> None:
        """Setup default policy rules."""
        
        # Rule 1: Low confidence decisions require approval
        def low_confidence_check(decision: LLMDecision, plan: Plan) -> bool:
            return decision.confidence < 0.5
        
        self.add_rule(PolicyRule(
            "low_confidence",
            "Decision confidence below 50%",
            low_confidence_check,
            severity="warning"
        ))
        
        # Rule 2: Dangerous tools require approval
        def dangerous_tools_check(decision: LLMDecision, plan: Plan) -> bool:
            dangerous_tools = ["delete_all", "drop_database", "terminate", "format_disk"]
            for intent in decision.tool_intents:
                tool = intent.get("tool", "").lower()
                if any(dt in tool for dt in dangerous_tools):
                    return True
            return False
        
        self.add_rule(PolicyRule(
            "dangerous_tools",
            "Decision uses dangerous tools",
            dangerous_tools_check,
            severity="critical"
        ))
        
        # Rule 3: Stage changes require approval if not in final stage
        def stage_change_check(decision: LLMDecision, plan: Plan) -> bool:
            if not decision.update_stage_to:
                return False
            
            # Allow stage changes, but log them
            current_stage = plan.current_stage
            if current_stage:
                logger.info(f"[Policy] Stage change requested: {current_stage.name} -> {decision.update_stage_to}")
            
            return False  # Don't require approval for stage changes by default
        
        self.add_rule(PolicyRule(
            "stage_changes",
            "Plan stage transition",
            stage_change_check,
            severity="info"
        ))
        
        # Rule 4: Multiple parallel tool calls require approval
        def parallel_tools_check(decision: LLMDecision, plan: Plan) -> bool:
            if len(decision.tool_intents) > 5:
                logger.warning(f"[Policy] Large batch of tools: {len(decision.tool_intents)}")
                return True
            return False
        
        self.add_rule(PolicyRule(
            "parallel_tools",
            "Large batch of parallel tool calls",
            parallel_tools_check,
            severity="warning"
        ))

    def add_rule(self, rule: PolicyRule) -> None:
        """Add a new policy rule."""
        self.rules.append(rule)
        logger.debug(f"[Policy] Added rule: {rule.name}")

    def evaluate_decision(self, decision: LLMDecision, plan: Plan) -> Dict[str, Any]:
        """Evaluate a decision against all policies."""
        
        violations = []
        warnings = []
        requires_approval = decision.requires_approval  # Start with LLM's assessment
        
        for rule in self.rules:
            try:
                if rule.evaluate(decision, plan):
                    violation = {
                        "rule": rule.name,
                        "description": rule.description,
                        "severity": rule.severity,
                    }
                    
                    if rule.severity == "critical":
                        violations.append(violation)
                        requires_approval = True
                    elif rule.severity == "error":
                        violations.append(violation)
                        requires_approval = True
                    else:  # warning or info
                        warnings.append(violation)
                        if rule.severity == "warning":
                            requires_approval = True
            except Exception as e:
                logger.error(f"[Policy] Error evaluating rule {rule.name}: {e}")
        
        return {
            "approved": len(violations) == 0,
            "requires_approval": requires_approval,
            "violations": violations,
            "warnings": warnings,
        }

    def is_high_risk(self, decision: LLMDecision, plan: Plan) -> bool:
        """Determine if a decision is high-risk."""
        
        evaluation = self.evaluate_decision(decision, plan)
        return len(evaluation.get("violations", [])) > 0


class RiskAssessment:
    """Assess risk level of decisions and actions."""
    
    RISK_LEVELS = {
        "low": 0,
        "medium": 1,
        "high": 2,
        "critical": 3,
    }
    
    @staticmethod
    def assess_tool_risk(tool_name: str) -> str:
        """Assess risk level of a tool."""
        
        high_risk_tools = [
            "delete", "drop", "terminate", "kill", "format",
            "remove", "purge", "wipe", "reset"
        ]
        
        medium_risk_tools = [
            "write", "update", "modify", "change",
            "execute", "run", "deploy", "apply"
        ]
        
        tool_lower = tool_name.lower()
        
        for word in high_risk_tools:
            if word in tool_lower:
                return "high"
        
        for word in medium_risk_tools:
            if word in tool_lower:
                return "medium"
        
        return "low"

    @staticmethod
    def assess_decision_risk(decision: LLMDecision) -> str:
        """Assess overall risk of a decision."""
        
        risks = [RiskAssessment.assess_tool_risk(
            intent.get("tool", "")
        ) for intent in decision.tool_intents]
        
        if not risks:
            return "low"
        
        risk_scores = [RiskAssessment.RISK_LEVELS[r] for r in risks]
        max_risk_score = max(risk_scores)
        
        for level, score in RiskAssessment.RISK_LEVELS.items():
            if score == max_risk_score:
                return level
        
        return "low"
