"""LLM Connector for local OpenAI-compatible API."""
import logging
import json
from typing import Dict, Any, Optional
from openai import OpenAI
from models import LLMDecision


logger = logging.getLogger(__name__)


class LLMConnector:
    """Connector to local OpenAI-compatible LLM."""
    
    def __init__(self, base_url: str, api_key: str, model_name: str, 
                 max_tokens: int = 4096, temperature: float = 0.2):
        self.base_url = base_url
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        logger.info(f"[LLM] Initialized with model: {model_name} at {base_url}")

    def get_decision(self, context_dict: Dict[str, Any], schema: Optional[Dict[str, Any]] = None) -> LLMDecision:
        """Get a decision from the LLM based on context."""
        
        # Prepare context for LLM
        context_str = json.dumps(context_dict, indent=2, default=str)
        
        # Build the prompt
        system_prompt = """You are an enterprise-grade orchestration engine for autonomous agentic workflows.
Your role is to:
1. Analyze the current plan stage and observations
2. Decide on the next action(s) to take
3. Recommend tool calls to execute via the MCP Gateway
4. Decide if stage transitions are needed
5. Flag any decisions that require human approval due to risk or policy

Always respond with valid JSON matching the provided schema.
"""
        
        user_prompt = f"""Analyze the following workflow context and provide your decision:

{context_str}

Provide your response as JSON with the following structure:
{{
    "next_action": "string describing the next action",
    "tool_intents": [
        {{"tool": "tool_name", "arguments": {{}}, "description": "why this tool"}},
        ...
    ],
    "update_stage_to": "target_stage_name or null if staying in current stage",
    "rationale": "explanation of your decision",
    "requires_approval": false,
    "confidence": 0.85
}}
"""
        
        logger.debug("[LLM] Sending context to LLM for decision")
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            
            # Extract the response
            response_text = response.choices[0].message.content
            logger.debug(f"[LLM] Response: {response_text[:500]}...")
            
            # Parse the JSON response
            try:
                response_json = json.loads(response_text)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code blocks
                if "```json" in response_text:
                    json_start = response_text.index("```json") + 7
                    json_end = response_text.index("```", json_start)
                    response_json = json.loads(response_text[json_start:json_end].strip())
                elif "```" in response_text:
                    json_start = response_text.index("```") + 3
                    json_end = response_text.index("```", json_start)
                    response_json = json.loads(response_text[json_start:json_end].strip())
                else:
                    raise ValueError("Could not parse JSON response from LLM")
            
            # Convert to LLMDecision object
            decision = LLMDecision()
            decision.tool_intents = response_json.get("tool_intents", [])
            decision.next_action = response_json.get("next_action", "")
            decision.update_stage_to = response_json.get("update_stage_to")
            decision.rationale = response_json.get("rationale", "")
            decision.requires_approval = response_json.get("requires_approval", False)
            decision.confidence = response_json.get("confidence", 0.0)
            
            logger.info(f"[LLM] Decision: {decision.next_action} (confidence: {decision.confidence})")
            
            return decision
            
        except Exception as e:
            logger.error(f"[LLM] Error getting decision: {e}")
            
            # Return a safe default decision
            decision = LLMDecision()
            decision.next_action = "error_occurred"
            decision.rationale = f"LLM error: {str(e)}"
            decision.tool_intents = []
            return decision

    def summarize_observations(self, observations: list) -> str:
        """Summarize a list of observations using the LLM."""
        
        observations_str = json.dumps([o.to_dict() if hasattr(o, 'to_dict') else o for o in observations], 
                                      indent=2, default=str)
        
        prompt = f"""Summarize the following observations into a concise bullet point list, 
preserving all critical data points:

{observations_str}

Provide a brief, structured summary that can be injected back into the context."""
        
        logger.debug("[LLM] Requesting observation summarization")
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1000,
                temperature=0.3,
            )
            
            summary = response.choices[0].message.content
            logger.info("[LLM] Observations summarized")
            return summary
            
        except Exception as e:
            logger.error(f"[LLM] Error summarizing observations: {e}")
            return "Summary generation failed"

    def validate_json_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Validate and extract JSON from LLM response."""
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            # Try markdown code blocks
            if "```json" in response_text:
                json_start = response_text.index("```json") + 7
                json_end = response_text.index("```", json_start)
                return json.loads(response_text[json_start:json_end].strip())
            elif "```" in response_text:
                json_start = response_text.index("```") + 3
                json_end = response_text.index("```", json_start)
                return json.loads(response_text[json_start:json_end].strip())
        return None
