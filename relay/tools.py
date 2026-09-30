"""Dynamic tool manifests and exactly-once protection for side effects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    state_modifying: bool = False
    max_retries: int = 1


@dataclass(slots=True)
class ToolCallRecord:
    call_id: str
    task_id: str
    tool_name: str
    arguments: dict[str, Any]
    attempt: int = 1
    idempotency_key: str | None = None
    branch_id: str | None = None


@dataclass(slots=True)
class ToolRegistry:
    definitions: dict[str, ToolDefinition] = field(default_factory=dict)
    committed_idempotency_keys: set[str] = field(default_factory=set)

    def load_manifest(self, manifest: list[dict[str, Any]]) -> None:
        self.definitions = {
            item["name"]: ToolDefinition(
                name=item["name"],
                description=item.get("description", ""),
                parameters=dict(item.get("parameters", {})),
                state_modifying=bool(item.get("state_modifying", False)),
                max_retries=int(item.get("max_retries", 1)),
            )
            for item in manifest
        }

    def get(self, name: str) -> ToolDefinition:
        if name not in self.definitions:
            raise KeyError(f"Unknown tool: {name}")
        return self.definitions[name]

    def reserve_side_effect(self, tool_name: str, idempotency_key: str) -> bool:
        definition = self.get(tool_name)
        if not definition.state_modifying:
            return True
        if idempotency_key in self.committed_idempotency_keys:
            return False
        self.committed_idempotency_keys.add(idempotency_key)
        return True

    def validate_arguments(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Validate the small JSON-Schema subset used by scenario manifests."""
        definition = self.get(tool_name)
        schema = definition.parameters
        required = schema.get("required", [])
        missing = [name for name in required if name not in arguments]
        if missing:
            raise ValueError(f"Missing required arguments for {tool_name}: {missing}")

        expected_python_types = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "object": dict,
            "array": list,
        }
        for name, property_schema in schema.get("properties", {}).items():
            if name not in arguments or "type" not in property_schema:
                continue
            expected = expected_python_types.get(property_schema["type"])
            value = arguments[name]
            boolean_as_number = (
                isinstance(value, bool)
                and property_schema["type"] in {"integer", "number"}
            )
            if expected and (not isinstance(value, expected) or boolean_as_number):
                raise ValueError(
                    f"Argument {name!r} for {tool_name} must be "
                    f"{property_schema['type']}"
                )

    def can_retry(self, tool_name: str, attempt: int) -> bool:
        definition = self.get(tool_name)
        return not definition.state_modifying and attempt <= definition.max_retries
