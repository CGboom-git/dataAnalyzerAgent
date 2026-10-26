"""Host MCP bridge: frozen catalog, qualified tools and schema enforcement."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from jsonschema import Draft202012Validator, ValidationError


@dataclass(frozen=True)
class MCPTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    read_only: bool
    server_id: str


class MCPProvider(Protocol):
    """Transport, identity, auth and deadlines belong to the host session."""
    def list_tools(self) -> list[MCPTool]: ...
    def call_tool(self, *, server_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


def _reject_remote_refs(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"$ref", "$dynamicRef"} and (not isinstance(item, str) or not item.startswith("#")):
                raise ValueError("mcp_remote_schema_ref_not_allowed")
            _reject_remote_refs(item)
    elif isinstance(value, list):
        for item in value:
            _reject_remote_refs(item)


class MCPToolBridge:
    """Allowlist entries use server_id/tool_name, never unqualified remote names."""
    def __init__(self, provider: MCPProvider, allowlist: set[str]) -> None:
        self.provider = provider
        self._tools: dict[str, MCPTool] = {}
        seen = set()
        for tool in provider.list_tools():
            qualified = f"{tool.server_id}/{tool.name}"
            if qualified in seen:
                raise ValueError("mcp_duplicate_tool")
            seen.add(qualified)
            if qualified not in allowlist or tool.read_only is not True:
                continue
            _reject_remote_refs(tool.input_schema)
            Draft202012Validator.check_schema(tool.input_schema)
            slug = re.sub(r"[^a-zA-Z0-9_-]", "_", f"{tool.server_id}_{tool.name}")[:40]
            digest = hashlib.sha256(qualified.encode()).hexdigest()[:10]
            self._tools[f"mcp_{slug}_{digest}"] = copy.deepcopy(tool)

    def contains(self, name: str) -> bool:
        return name in self._tools

    def catalog(self) -> list[dict]:
        return [{"name": alias, "description": t.description, "input_schema": copy.deepcopy(t.input_schema),
                 "read_only": True, "server_id": t.server_id, "remote_name": t.name, "source": "mcp"}
                for alias, t in self._tools.items()]

    def schemas(self) -> list[dict]:
        return [{"type": "function", "function": {
            "name": t["name"], "description": t["description"], "parameters": t["input_schema"],
        }} for t in self.catalog()]

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            raise ValueError("mcp_tool_not_allowlisted")
        if not isinstance(arguments, dict) or len(json.dumps(arguments)) > 12000:
            raise ValueError("mcp_arguments_invalid")
        try:
            Draft202012Validator(tool.input_schema).validate(arguments)
        except ValidationError as exc:
            raise ValueError("mcp_arguments_schema_mismatch") from exc
        try:
            raw = self.provider.call_tool(server_id=tool.server_id, name=tool.name,
                                          arguments=copy.deepcopy(arguments))
        except Exception:
            return {"ok": False, "source": "mcp", "error": {"code": "mcp_provider_failed"}}
        if not isinstance(raw, dict):
            return {"ok": False, "source": "mcp", "error": {"code": "mcp_invalid_result"}}
        if raw.get("isError"):
            return {"ok": False, "source": f"mcp:{tool.server_id}",
                    "error": {"code": "mcp_tool_error"}}
        return {"ok": True, "source": f"mcp:{tool.server_id}",
                "data": raw.get("structuredContent", raw)}
