"""Gateway Client for communicating with the tinymcp MCP Gateway."""
import logging
import json
import uuid
from typing import List, Dict, Any, Optional
import httpx


logger = logging.getLogger(__name__)


class GatewayClient:
    """HTTP client for the tinymcp MCP Gateway with session-based JSON-RPC."""

    def __init__(self, gateway_url: str, auth_token: str = None):
        self.gateway_url = gateway_url.rstrip("/")
        self.auth_token = auth_token
        self.session_id: Optional[str] = None
        self.client = httpx.Client(timeout=30.0)
        self._init_session()

    def _init_session(self) -> None:
        """Create a session with the gateway."""
        try:
            resp = self.client.post(f"{self.gateway_url}/sessions")
            resp.raise_for_status()
            self.session_id = resp.json().get("sessionId")
            logger.info(f"[Gateway] Session created: {self.session_id}")
        except Exception as e:
            logger.error(f"[Gateway] Failed to create session: {e}")
            self.session_id = str(uuid.uuid4())
            logger.warning(f"[Gateway] Using fallback session ID: {self.session_id}")

    def _headers(self, extra: Dict[str, str] = None) -> Dict[str, str]:
        """Build request headers with auth and session."""
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        if extra:
            headers.update(extra)
        return headers

    def _session_headers(self) -> Dict[str, str]:
        """Build headers including session ID."""
        headers = self._headers({"X-Session-ID": self.session_id or ""})
        return headers

    def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools from the gateway."""
        logger.info("[Gateway] Listing all tools")
        try:
            resp = self.client.get(f"{self.gateway_url}/tools")
            resp.raise_for_status()
            data = resp.json()
            tools = data.get("tools", [])
            logger.info(f"[Gateway] Found {len(tools)} tools")
            return tools
        except Exception as e:
            logger.error(f"[Gateway] Error listing tools: {e}")
            return []

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool via the gateway using standard JSON-RPC over /execute."""
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        logger.info(f"[Gateway] Executing tool: {tool_name}")
        logger.debug(f"[Gateway] Arguments: {json.dumps(arguments, default=str)}")

        try:
            resp = self.client.post(
                f"{self.gateway_url}/execute",
                json=payload,
                headers=self._session_headers(),
            )
            resp.raise_for_status()
            result = resp.json()
            if "error" in result:
                logger.error(f"[Gateway] Tool error: {result['error']}")
            return result
        except Exception as e:
            logger.error(f"[Gateway] Error executing tool {tool_name}: {e}")
            return {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "error": {"code": -32603, "message": str(e)},
            }

    def execute_batch(self, tool_intents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute multiple tool calls (batch mode)."""
        results = []
        logger.info(f"[Gateway] Executing batch of {len(tool_intents)} tools")
        for intent in tool_intents:
            tool_name = intent.get("tool") or intent.get("name")
            arguments = intent.get("arguments", {})
            if not tool_name:
                logger.warning("[Gateway] Skipping intent without tool name")
                continue
            result = self.execute_tool(tool_name, arguments)
            results.append(result)
        return results

    def list_servers(self) -> List[Dict[str, Any]]:
        """List all registered MCP servers from the gateway."""
        logger.info("[Gateway] Listing registered servers")
        try:
            resp = self.client.get(f"{self.gateway_url}/registry/servers")
            resp.raise_for_status()
            servers = resp.json()
            if isinstance(servers, list):
                logger.info(f"[Gateway] Found {len(servers)} servers")
            else:
                servers = servers.get("servers", [])
                logger.info(f"[Gateway] Found {len(servers)} servers")
            return servers
        except Exception as e:
            logger.error(f"[Gateway] Error listing servers: {e}")
            return []

    def health_check(self) -> bool:
        """Check if the gateway is healthy."""
        try:
            resp = self.client.get(f"{self.gateway_url}/healthz")
            return resp.status_code == 200
        except Exception:
            return False

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
        logger.info("[Gateway] Client closed")
