"""Skills Registry for managing available tools/skills from the tinymcp Gateway."""
import logging
from typing import Dict, List, Any, Optional
from gateway_client import GatewayClient


logger = logging.getLogger(__name__)


class SkillsRegistry:
    """Registry for skills (MCP tools) discovered from the tinymcp Gateway."""

    def __init__(self, gateway_client: GatewayClient, skills_server_name: str = "skills-provider"):
        self.gateway_client = gateway_client
        self.skills_server_name = skills_server_name
        self.skills: Dict[str, Dict[str, Any]] = {}
        self.skills_by_stage: Dict[str, List[str]] = {}

    def refresh_skills(self) -> int:
        """Refresh the skills list from the gateway via tool discovery."""
        logger.info("[Skills] Refreshing skills from gateway")

        tools = self.gateway_client.list_tools()

        self.skills = {}
        for tool in tools:
            tool_name = tool.get("name", "")
            if tool_name:
                self.skills[tool_name] = {
                    "name": tool_name,
                    "description": tool.get("description", ""),
                    "inputSchema": tool.get("inputSchema", {}),
                    "server": tool.get("server", self.skills_server_name),
                }

        logger.info(f"[Skills] Loaded {len(self.skills)} skills")
        return len(self.skills)

    def get_skill(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """Get a specific skill by name."""
        return self.skills.get(skill_name)

    def get_skills_for_stage(self, stage_name: str) -> List[Dict[str, Any]]:
        """Get all available skills for a stage."""
        # All discovered skills are available unless filtered by stage tags
        return list(self.skills.values())

    def register_stage_skills(self, stage_name: str, skill_names: List[str]) -> None:
        """Register which skills are available for a stage."""
        self.skills_by_stage[stage_name] = skill_names
        logger.debug(f"[Skills] Registered {len(skill_names)} skills for stage: {stage_name}")

    def list_all_skills(self) -> List[str]:
        """List all available skill names."""
        return list(self.skills.keys())

    def get_skill_description(self, skill_name: str) -> str:
        """Get a human-readable description of a skill."""
        skill = self.get_skill(skill_name)
        if not skill:
            return f"Skill '{skill_name}' not found"
        return skill.get("description", "No description")

    def validate_skill_exists(self, skill_name: str) -> bool:
        """Check if a skill exists."""
        return skill_name in self.skills

    def get_skills_summary(self) -> str:
        """Get a formatted summary of all available skills."""
        summary = f"Available Skills ({len(self.skills)}):\n"
        for skill_name, skill_info in self.skills.items():
            description = skill_info.get("description", "No description")
            summary += f"- {skill_name}: {description}\n"
        return summary

    def to_dict(self) -> Dict[str, Any]:
        """Convert skills registry to dict format."""
        return {
            "skills": self.skills,
            "skills_by_stage": self.skills_by_stage,
            "total_skills": len(self.skills),
        }
