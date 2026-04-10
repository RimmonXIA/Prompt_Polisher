"""A2A Protocol Server (Spec §9-11).

Implements JSON-RPC 2.0 over HTTP mapping to Prompt Polisher logic.
Provides both synchronous and real-time streaming (SSE) task management.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from prompt_polisher.agent_card import build_agent_card
from prompt_polisher.config import get_settings
from prompt_polisher.graph import run_compiler_async
from prompt_polisher.llm import build_llm_client

logger = logging.getLogger(__name__)

app = FastAPI(title="Prompt Polisher A2A Server")

# In-memory task store (demo / dev). Production should use a persistent backend.
tasks: dict[str, dict[str, Any]] = {}


@app.get("/.well-known/agent-card.json")
async def get_agent_card() -> dict[str, Any]:
    """Discovery endpoint mandated by A2A Spec §8.2."""
    card = build_agent_card()
    # Dynamic capability updates for the live server
    capabilities = cast(dict[str, Any], card.get("capabilities", {}))
    capabilities["streaming"] = True
    card["supportedInterfaces"] = [
        {
            "url": "/a2a/v1",
            "protocolBinding": "HTTP+JSON",
            "protocolVersion": "1.0",
        }
    ]
    return card


@app.post("/a2a/v1", response_model=None)
async def handle_rpc(
    request: Request, background_tasks: BackgroundTasks
) -> JSONResponse | EventSourceResponse | dict[str, Any]:
    """JSON-RPC 2.0 Entry point (Spec §9)."""
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": "Parse error"},
                "id": None,
            },
        )

    method = body.get("method")
    rpc_id = body.get("id")

    if method == "SendMessage":
        return await handle_send_message(body, background_tasks)
    elif method == "SendStreamingMessage":
        return await handle_send_streaming_message(body)
    elif method == "GetTask":
        return await handle_get_task(body)
    elif method == "ListTasks":
        return await handle_list_tasks(body)

    return JSONResponse(
        status_code=405,
        content={
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": "Method not found"},
            "id": rpc_id,
        },
    )


async def handle_send_message(
    body: dict[str, Any], background_tasks: BackgroundTasks
) -> dict[str, Any] | JSONResponse:
    """Starts an asynchronous compilation task."""
    params = body.get("params", {})
    user_input = _extract_input(params)

    if not user_input:
        return _rpc_error(body.get("id"), -32602, "Invalid params: missing input")

    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "id": task_id,
        "status": "WORKING",
        "created_at": datetime.now(UTC).isoformat(),
        "result": None,
        "input": user_input,
    }

    # Execute in background
    background_tasks.add_task(execute_task, task_id, user_input)

    return {
        "jsonrpc": "2.0",
        "result": {"task": {"id": task_id, "status": {"state": "TASK_STATE_WORKING"}}},
        "id": body.get("id"),
    }


async def handle_send_streaming_message(
    body: dict[str, Any],
) -> EventSourceResponse | dict[str, Any]:
    """Starts a streaming task via Server-Sent Events (SSE)."""
    params = body.get("params", {})
    user_input = _extract_input(params)

    if not user_input:
        return _rpc_error(body.get("id"), -32602, "Invalid params: missing input")

    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "id": task_id,
        "status": "WORKING",
        "created_at": datetime.now(UTC).isoformat(),
        "result": None,
        "input": user_input,
    }

    return EventSourceResponse(stream_task_events(task_id, user_input, body.get("id")))


async def handle_get_task(body: dict[str, Any]) -> dict[str, Any]:
    """Polls for task status and results."""
    task_id = body.get("params", {}).get("id")
    task = tasks.get(task_id)

    if not task:
        return _rpc_error(body.get("id"), -32001, "Task not found")

    state_map = {
        "WORKING": "TASK_STATE_WORKING",
        "COMPLETED": "TASK_STATE_COMPLETED",
        "FAILED": "TASK_STATE_FAILED",
        "ABORTED": "TASK_STATE_REJECTED",
    }

    response = {
        "jsonrpc": "2.0",
        "result": {
            "task": {
                "id": task_id,
                "status": {"state": state_map.get(task["status"], "TASK_STATE_FAILED")},
            }
        },
        "id": body.get("id"),
    }

    if task["status"] == "ABORTED":
        msg = f"SAFETY_INTERVENTION: {task.get('error')}"
        # Cast nested dictionary for Mypy
        result_dict = cast(dict[str, Any], response["result"])
        res_task = cast(dict[str, Any], result_dict["task"])
        res_task["status"]["message"] = msg

    if task["result"]:
        # Map GraphState to A2A Artifacts (§4.1.7)
        result_dict = cast(dict[str, Any], response["result"])
        res_task = cast(dict[str, Any], result_dict["task"])
        res_task["artifacts"] = [
            {
                "id": "final-prompt",
                "name": "Compiled Prompt",
                "mimeType": "text/plain",
                "parts": [{"text": task["result"].get("final_prompt", "")}],
            }
        ]
        # Include audit trail if available
        if "radar_analysis" in task["result"]:
            artifacts = cast(list[dict[str, Any]], res_task["artifacts"])
            artifacts.append(
                {
                    "id": "audit-trail",
                    "name": "Radar Audit",
                    "mimeType": "application/json",
                    "parts": [{"json": task["result"]["radar_analysis"]}],
                }
            )

    return response


async def handle_list_tasks(body: dict[str, Any]) -> dict[str, Any]:
    """Lists recent tasks (§9.4.4)."""
    # Simple implementation: return all tasks from memory
    return {
        "jsonrpc": "2.0",
        "result": {
            "tasks": [
                {
                    "id": tid,
                    "status": {"state": t["status"]},
                    "createdAt": t["created_at"],
                }
                for tid, t in tasks.items()
            ]
        },
        "id": body.get("id"),
    }


async def stream_task_events(
    task_id: str, user_input: str, rpc_id: Any
) -> AsyncGenerator[dict[str, Any], None]:
    """Yields A2A StreamResponse objects (§3.2.3)."""
    # Initial Task Event
    yield {
        "data": json.dumps(
            {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {"task": {"id": task_id, "status": {"state": "TASK_STATE_WORKING"}}},
            }
        )
    }

    settings = get_settings()
    llm = build_llm_client(settings)

    try:
        # Simulate incremental status: run_compiler_async is one call, not streamed.
        # Future: wire LangGraph stream events to SSE if needed.
        yield _sse_update(task_id, rpc_id, "ST_RADAR", "Running Radar analysis...")
        await asyncio.sleep(0.5)

        yield _sse_update(task_id, rpc_id, "ST_COMPILE", "Compiling prompt...")
        result = await run_compiler_async(user_input, settings, llm)

        aborted = bool(result.get("compilation_aborted"))
        tasks[task_id]["status"] = "COMPLETED" if not aborted else "ABORTED"
        tasks[task_id]["result"] = result

        if result.get("compilation_aborted"):
            error_msg = result.get("abort_reason", "Safety Check Failed")
            tasks[task_id]["error"] = error_msg
            yield _sse_terminal(
                task_id, rpc_id, "TASK_STATE_REJECTED", f"SAFETY_INTERVENTION: {error_msg}"
            )
        else:
            yield _sse_terminal(task_id, rpc_id, "TASK_STATE_COMPLETED", "Compilation complete")
            # Send final artifact update
            yield {
                "data": json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "result": {
                            "artifactUpdate": {
                                "taskId": task_id,
                                "artifact": {
                                    "id": "final-prompt",
                                    "name": "Compiled Prompt",
                                    "parts": [{"text": result.get("final_prompt", "")}],
                                },
                            }
                        },
                    }
                )
            }

    except Exception as e:
        logger.exception("Task execution failed")
        tasks[task_id]["status"] = "FAILED"
        tasks[task_id]["error"] = str(e)
        yield _sse_terminal(task_id, rpc_id, "TASK_STATE_FAILED", str(e))


def _extract_input(params: dict[str, Any]) -> str:
    """Extracts text input from A2A SendMessageRequest."""
    val = params.get("input")
    if isinstance(val, str):
        return val
    if "message" in params and "parts" in params["message"]:
        for part in params["message"]["parts"]:
            if "text" in part:
                return str(part["text"])
    return ""


def _sse_update(task_id: str, rpc_id: Any, code: str, message: str) -> dict[str, Any]:
    return {
        "data": json.dumps(
            {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "statusUpdate": {
                        "taskId": task_id,
                        "status": {"state": "TASK_STATE_WORKING", "code": code, "message": message},
                    }
                },
            }
        )
    }


def _sse_terminal(task_id: str, rpc_id: Any, state: str, message: str) -> dict[str, Any]:
    return {
        "data": json.dumps(
            {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "statusUpdate": {
                        "taskId": task_id,
                        "status": {"state": state, "message": message},
                    }
                },
            }
        )
    }


def _rpc_error(rpc_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "error": {"code": code, "message": message},
        "id": rpc_id,
    }


async def execute_task(task_id: str, user_input: str) -> None:
    """Background execution for non-streaming SendMessage."""
    settings = get_settings()
    llm = build_llm_client(settings)
    try:
        result = await run_compiler_async(user_input, settings, llm)
        aborted = bool(result.get("compilation_aborted"))
        tasks[task_id]["status"] = "COMPLETED" if not aborted else "ABORTED"
        tasks[task_id]["result"] = result
        if result.get("compilation_aborted"):
            tasks[task_id]["error"] = result.get("abort_reason", "Safety Check Failed")
    except Exception as e:
        logger.exception("Background task failed")
        tasks[task_id]["status"] = "FAILED"
        tasks[task_id]["error"] = str(e)
