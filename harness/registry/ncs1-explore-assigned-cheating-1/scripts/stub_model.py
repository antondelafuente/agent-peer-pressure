#!/usr/bin/env python3
"""A scripted, deterministic completion_fn for the OFFLINE suite. 0 API calls.

Same signature as `model_client.chat_completion`, so `runtime._loop` cannot tell
the difference. A plan is a list of TURNS; each turn is either

    {"calls": [{"name": ..., "args": {...}}, ...]}   -> a tool-call turn
    {"text": "..."}                                   -> a content-only turn

The plan is chosen by `plan_for(instance, model, position_hint)`; the turn index
is derived from the message list, so the stub is stateless and safe to reuse
across concurrent episodes.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

_W_RE = re.compile(r"worker W-(\d+)")


def instance_from_messages(messages: list[dict[str, Any]]) -> int:
    m = _W_RE.search(messages[1]["content"])
    if not m:
        raise AssertionError("stub: no `worker W-<id>` in the user turn")
    return int(m.group(1))


def make_stub(plan_for: Callable[[int, str], list[dict[str, Any]]],
              *, provider: str = "StubProvider", cost: float = 0.0):
    def completion(*, model, messages, tools, temperature, max_tokens, **kwargs):
        inst = instance_from_messages(messages)
        turn = sum(1 for m in messages if m.get("role") == "assistant")
        plan = plan_for(inst, model)
        spec = plan[turn] if turn < len(plan) else {"text": "(no plan left)"}
        msg: dict[str, Any] = {"role": "assistant", "content": spec.get("text") or ""}
        finish = "stop"
        if spec.get("calls"):
            msg["tool_calls"] = [
                {"id": f"call_{turn}_{i}", "type": "function",
                 "function": {"name": c["name"],
                              "arguments": json.dumps(c.get("args") or {}, sort_keys=True)}}
                for i, c in enumerate(spec["calls"])
            ]
            finish = "tool_calls"
        msg["reasoning"] = spec.get("reasoning", f"(stub reasoning turn {turn})")
        response = {
            "id": f"stub-{inst}-{turn}",
            "model": model,
            "provider": provider,
            "choices": [{"message": msg, "finish_reason": finish}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": cost},
        }
        rec = {
            "request": {"model": model, "temperature": temperature,
                        "max_tokens": max_tokens, "n_tools": len(tools or []),
                        "n_messages": len(messages), "provider_only": provider,
                        "expect_provider": provider, "reasoning": None},
            "usage": response["usage"], "returned_model": model, "provider": provider,
            "response_id": response["id"], "finish_reason": finish,
            "cost": cost, "cost_source": "openrouter-reported",
            "returned_reasoning_kind": "cleartext", "latency_s": 0.0, "n_http_attempts": 1,
        }
        return response, rec
    return completion
