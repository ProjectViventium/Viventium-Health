"""Minimal read-only MCP server over newline-delimited stdio JSON-RPC."""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from . import __version__
from .archive import ArchiveError, RawArchive

PROTOCOL_VERSION = "2025-06-18"


TOOLS = [
    {
        "name": "health_list_runs",
        "description": "List bounded health-source capture runs with status and timestamps.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "provider": {"type": "string", "description": "Optional provider slug, such as whoop."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 20},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "health_list_records",
        "description": "List bounded raw response records by opaque ID without exposing file paths.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "provider": {"type": "string"},
                "run_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 50},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "health_read_record",
        "description": "Read a bounded byte range from one archived response by opaque record ID.",
        "inputSchema": {
            "type": "object",
            "required": ["record_id"],
            "properties": {
                "record_id": {"type": "string"},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
                "max_bytes": {"type": "integer", "minimum": 1, "maximum": 1048576, "default": 65536},
            },
            "additionalProperties": False,
        },
    },
]


def _rpc_result(identifier: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": identifier, "result": result}


def _rpc_error(identifier: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": identifier, "error": {"code": code, "message": message}}


def _tool_result(value: Any, *, is_error: bool = False) -> dict[str, Any]:
    result = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(value, ensure_ascii=False, separators=(",", ":")),
            }
        ],
        "structuredContent": value,
    }
    if is_error:
        result["isError"] = True
    return result


def _arguments(params: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(params, dict):
        raise ArchiveError("tool parameters must be an object")
    name = params.get("name")
    arguments = params.get("arguments", {})
    if not isinstance(name, str) or not isinstance(arguments, dict):
        raise ArchiveError("tool name and arguments are required")
    return name, arguments


def _reject_extra(arguments: dict[str, Any], allowed: set[str]) -> None:
    if set(arguments) - allowed:
        raise ArchiveError("unsupported tool argument")


def _integer(arguments: dict[str, Any], name: str, default: int) -> int:
    value = arguments.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ArchiveError(f"{name} must be an integer")
    return value


def call_tool(archive: RawArchive, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "health_list_runs":
        _reject_extra(arguments, {"provider", "limit"})
        provider = arguments.get("provider")
        if provider is not None and not isinstance(provider, str):
            raise ArchiveError("provider must be a string")
        return {"runs": archive.list_runs(provider=provider, limit=_integer(arguments, "limit", 20))}
    if name == "health_list_records":
        _reject_extra(arguments, {"provider", "run_id", "limit"})
        provider = arguments.get("provider")
        run_id = arguments.get("run_id")
        if provider is not None and not isinstance(provider, str):
            raise ArchiveError("provider must be a string")
        if run_id is not None and not isinstance(run_id, str):
            raise ArchiveError("run_id must be a string")
        return {
            "records": archive.list_records(
                provider=provider,
                run_id=run_id,
                limit=_integer(arguments, "limit", 50),
            )
        }
    if name == "health_read_record":
        _reject_extra(arguments, {"record_id", "offset", "max_bytes"})
        record_id = arguments.get("record_id")
        if not isinstance(record_id, str):
            raise ArchiveError("record_id must be a string")
        return archive.read_record(
            record_id,
            offset=_integer(arguments, "offset", 0),
            max_bytes=_integer(arguments, "max_bytes", 65_536),
        )
    raise ArchiveError("unknown health tool")


def serve(archive: RawArchive, *, stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> int:
    initialized = False
    for raw_line in stdin:
        try:
            message = json.loads(raw_line)
        except json.JSONDecodeError:
            response = _rpc_error(None, -32700, "Parse error")
        else:
            if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                response = _rpc_error(message.get("id") if isinstance(message, dict) else None, -32600, "Invalid Request")
            else:
                identifier = message.get("id")
                method = message.get("method")
                if method == "notifications/initialized" or identifier is None:
                    response = None
                elif method == "initialize":
                    initialized = True
                    response = _rpc_result(
                        identifier,
                        {
                            "protocolVersion": PROTOCOL_VERSION,
                            "capabilities": {"tools": {"listChanged": False}},
                            "serverInfo": {"name": "viventium-health", "version": __version__},
                        },
                    )
                elif method == "ping":
                    response = _rpc_result(identifier, {})
                elif not initialized:
                    response = _rpc_error(identifier, -32002, "Server not initialized")
                elif method == "tools/list":
                    response = _rpc_result(identifier, {"tools": TOOLS})
                elif method == "tools/call":
                    try:
                        name, arguments = _arguments(message.get("params"))
                        value = call_tool(archive, name, arguments)
                        response = _rpc_result(identifier, _tool_result(value))
                    except ArchiveError as error:
                        response = _rpc_result(identifier, _tool_result({"error": str(error)}, is_error=True))
                    except (OSError, json.JSONDecodeError):
                        response = _rpc_result(
                            identifier,
                            _tool_result({"error": "health archive operation failed"}, is_error=True),
                        )
                else:
                    response = _rpc_error(identifier, -32601, "Method not found")
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            stdout.flush()
    return 0
