"""Main entry point for the MCP Control Plane application."""
import logging
import os
import yaml
import uvicorn
from typing import Optional

from dotenv import load_dotenv
from gateway_client import GatewayClient
from llm_connector import LLMConnector
from memory_manager import MemoryManager
from skills_registry import SkillsRegistry
from audit_store import AuditStore
from orchestrator import Orchestrator
from rest_api import create_api

# Load .env as the central configuration source
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ConfigManager:
    """Manage configuration from YAML and environment variables."""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
    
    def _load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file."""
        if not os.path.exists(config_path):
            logger.warning(f"Config file not found: {config_path}. Using defaults.")
            return self._get_defaults()
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Replace environment variables in config
        config = self._substitute_env_vars(config)
        
        return config
    
    def _substitute_env_vars(self, obj):
        """Recursively substitute environment variables in config.

        Supports ${VAR} (uses os.getenv with None default) and
        ${VAR:default_value} (uses os.getenv with explicit default).
        """
        if isinstance(obj, dict):
            return {k: self._substitute_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._substitute_env_vars(item) for item in obj]
        elif isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            inner = obj[2:-1]
            if ":" in inner:
                var_name, default = inner.split(":", 1)
                return os.getenv(var_name, default)
            return os.getenv(inner, obj)
        # Convert string "null" to Python None
        if obj == "null":
            return None
        return obj
    
    def _get_defaults(self) -> dict:
        """Get default configuration — values fall back to .env when available."""
        return {
            "system": {
                "env": os.getenv("DEMA_ENV", "dev"),
                "port": os.getenv("DEMA_PORT", "8080"),
                "log_level": os.getenv("DEMA_LOG_LEVEL", "info"),
            },
            "llm_provider": {
                "base_url": os.getenv("LLM_BASE_URL", "http://localhost:1234/v1"),
                "api_key": os.getenv("LLM_API_KEY", "not-needed-for-local"),
                "model_name": os.getenv("LLM_MODEL_NAME", "hermes-3-llama-3.1"),
                "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "4096")),
                "temperature": float(os.getenv("LLM_TEMPERATURE", "0.2")),
            },
            "gateway": {
                "url": os.getenv("GATEWAY_URL", "http://localhost:8080"),
                "auth_token": os.getenv("GATEWAY_SECRET") or None,
                "skills_server_name": os.getenv("GATEWAY_SKILLS_SERVER", "skills-provider"),
            },
            "memory": {
                "p2_summary_threshold_tokens": int(os.getenv("MEMORY_P2_THRESHOLD", "2000")),
                "p3_ttl_seconds": int(os.getenv("MEMORY_P3_TTL", "3600")),
            },
        }
    
    def get(self, path: str, default=None):
        """Get config value by dot-notation path."""
        parts = path.split('.')
        obj = self.config
        
        for part in parts:
            if isinstance(obj, dict):
                obj = obj.get(part)
            else:
                return default
        
        return obj if obj is not None else default


def initialize_components(config: ConfigManager):
    """Initialize all system components."""
    
    logger.info("Initializing MCP Control Plane components...")
    
    # 1. Gateway Client
    gateway_url = config.get("gateway.url")
    gateway_auth = config.get("gateway.auth_token")
    gateway_client = GatewayClient(gateway_url, gateway_auth)
    logger.info(f"[Init] Gateway Client initialized: {gateway_url}")
    
    # 2. LLM Connector
    llm_base_url = config.get("llm_provider.base_url")
    llm_api_key = config.get("llm_provider.api_key")
    llm_model = config.get("llm_provider.model_name")
    llm_max_tokens = int(config.get("llm_provider.max_tokens", 4096))
    llm_temperature = float(config.get("llm_provider.temperature", 0.2))
    
    llm_connector = LLMConnector(
        base_url=llm_base_url,
        api_key=llm_api_key,
        model_name=llm_model,
        max_tokens=llm_max_tokens,
        temperature=llm_temperature,
    )
    logger.info(f"[Init] LLM Connector initialized: {llm_model} at {llm_base_url}")
    
    # 3. Memory Manager
    p2_threshold = int(config.get("memory.p2_summary_threshold_tokens", 2000))
    p3_ttl = int(config.get("memory.p3_ttl_seconds", 3600))
    
    memory_manager = MemoryManager(p2_threshold, p3_ttl)
    logger.info(f"[Init] Memory Manager initialized (P2 threshold: {p2_threshold} tokens)")
    
    # 4. Skills Registry
    skills_server = config.get("gateway.skills_server_name", "skills-provider")
    skills_registry = SkillsRegistry(gateway_client, skills_server)
    skills_count = skills_registry.refresh_skills()
    logger.info(f"[Init] Skills Registry initialized ({skills_count} skills)")
    
    # 5. Audit Store
    audit_store = AuditStore()
    logger.info("[Init] Audit Store initialized")
    
    # 6. Orchestrator
    orchestrator = Orchestrator(
        llm_connector=llm_connector,
        gateway_client=gateway_client,
        memory_manager=memory_manager,
        skills_registry=skills_registry,
        audit_store=audit_store,
    )
    logger.info("[Init] Orchestrator initialized")
    
    return {
        "gateway_client": gateway_client,
        "llm_connector": llm_connector,
        "memory_manager": memory_manager,
        "skills_registry": skills_registry,
        "audit_store": audit_store,
        "orchestrator": orchestrator,
    }


def main():
    """Main entry point."""
    
    logger.info("=" * 80)
    logger.info("MCP CONTROL PLANE (DEMA) - Deus Ex Machina")
    logger.info("=" * 80)
    
    # Load configuration
    config = ConfigManager("config.yaml")
    env = config.get("system.env", "dev")
    port = int(config.get("system.port", 8080))
    log_level = config.get("system.log_level", "info")
    
    logger.info(f"Environment: {env}")
    logger.info(f"Port: {port}")
    logger.info(f"Log Level: {log_level}")
    
    # Set log level
    logging.getLogger().setLevel(getattr(logging, log_level.upper()))
    
    # Initialize components
    try:
        components = initialize_components(config)
        orchestrator = components["orchestrator"]
    except Exception as e:
        logger.error(f"Failed to initialize components: {e}")
        return 1
    
    # Create FastAPI application
    app = create_api(orchestrator)
    
    logger.info("=" * 80)
    logger.info("Starting MCP Control Plane server...")
    logger.info(f"Listening on http://0.0.0.0:{port}")
    logger.info("=" * 80)
    
    # Run the server
    try:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            log_level=log_level.lower(),
        )
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        components["gateway_client"].close()
        return 0
    except Exception as e:
        logger.error(f"Server error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
