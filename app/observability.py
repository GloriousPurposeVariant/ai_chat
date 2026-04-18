# -*- coding: utf-8 -*-
import json
import time
import uuid


def log_request(
    intent: str,
    user_type: str,
    tools_called: list,
    latency_ms: int,
    tool_details: list | None = None,
    prompt_tokens_est: int = 0,
    request_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    """
    Emit a structured JSON log line for every request.

    MINIMUM FIELDS REQUIRED BY THE TASK:
      - request_id
      - user_type
      - intent
      - tools_called + args
      - latency_ms per tool + total
      - prompt size estimate
    """
    log = {
        "request_id": request_id or str(uuid.uuid4()),
        "session_id": session_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "user_type":user_type,
        "intent": intent,
        "tools_called": tools_called,
        "tool_details": tool_details or [],   # per-tool timing + args
        "total_latency_ms": latency_ms,
        "prompt_tokens_estimate": prompt_tokens_est,
    }

    # Print as single-line JSON — easy to grep and parse
    print("[OBSERVABILITY]", json.dumps(log))
    return log


def make_tool_record(
    tool_name: str,
    args: dict,
    latency_ms: int,
    result_size: int = 0,
) -> dict:
    """
    Create a per-tool timing record.

    """
    return {
        "tool": tool_name,
        "args":  args,
        "latency_ms": latency_ms,
        "result_size": result_size,  # number of items returned
    }


def estimate_tokens(text: str) -> int:
    """
    Rough token estimate: ~4 characters per token (OpenAI rule of thumb).
    WHY: Exact token counts need a tokenizer library. For a PoC,
    character-based estimation is accurate enough to spot bloated prompts.
    """
    return len(text) // 4
