"""OpenRouter chat-completions client with full usage/provenance capture.

Pulled from the probe (registry/ncs1-range-probe-1/scripts/model_client.py at
research-lab main 464de0bf1), unchanged except for the request title and a
peak-tracking semaphore. No `reasoning` field is ever sent (DESIGN "## Arms"
-> *Model (8)*: provider-default reasoning), and whatever the response returns
is persisted per request:

  * one shared per-model (== per-provider) semaphore bracketing the SINGLE HTTP
    attempt, released before the jittered backoff sleep (run-experiment #343);
    `CountingSemaphore` records the MEASURED peak in-flight for SPEND.md
    (DESIGN "## Cost, schedule, fan-out" -> *Fan-out*);
  * a hard per-response pin check — `returned_model` must equal the requested
    slug and `provider` must equal the pin, else the row fails and is re-run
    (DESIGN "Pin rule");
  * `returned_reasoning_kind` — cleartext / encrypted / none, per request,
    which is what SPEND.md reports per model.
"""

from __future__ import annotations

import collections
import contextlib
import json
import os
import random
import statistics
import threading
import time
import urllib.error
import urllib.request
from typing import Any

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Listed OpenRouter price for openai/gpt-5.6-sol, used ONLY if usage.cost is absent.
# (Every observed response has carried usage.cost; the gate asserts cost_source.)
FALLBACK_PRICE_IN_PER_M = 2.00
FALLBACK_PRICE_OUT_PER_M = 10.00

RETRY_CODES = {408, 409, 429, 500, 502, 503, 504}


class ModelError(RuntimeError):
    pass


class PinMismatch(ModelError):
    """The provider returned a different model/provider than the pin."""


class _RetryableBody(Exception):
    """HTTP 200 carrying a retryable provider error in the BODY.

    OpenRouter can return `{"error": {"message": "Overloaded", "code": 503}}`
    with a 200 status and no `choices`. The HTTPError path never sees it, so
    without this the call fails on the first attempt and the row is lost — two
    opus prefixes were lost this way in the 2026-09-02 smoke.
    """


# Rate-limit responses seen across the process, for SPEND.md.
RATE_LIMIT_HITS = {"n": 0}
# Rolling per-request latencies (successful calls), for the fan-out ramp.
LATENCIES: collections.deque = collections.deque(maxlen=2000)
_LAT_LOCK = threading.Lock()


def record_latency(v: float | None) -> None:
    if v is None:
        return
    with _LAT_LOCK:
        LATENCIES.append(float(v))


def latency_median(n: int = 200) -> float | None:
    with _LAT_LOCK:
        vals = list(LATENCIES)[-n:]
    return statistics.median(vals) if vals else None


@contextlib.contextmanager
def _nullgate():
    yield


class CountingSemaphore:
    """A RESIZABLE semaphore that records the MEASURED peak concurrent holders.

    Two jobs, both from DESIGN "## Cost, schedule, fan-out" -> *Fan-out*:
      * SPEND.md carries the MEASURED peak in-flight per provider, not just the
        configured cap — `.peak`;
      * the ramp (64 -> 128 -> 256 -> 512, doubling while the last step was
        clean, halving on any 429) needs the cap to move while work is running
        — `.set_limit()`. In-flight is explicitly NOT a configuration field of
        the experiment (START.md), so moving it mid-wave changes no arm.
    """

    def __init__(self, value: int, max_limit: int = 512, min_limit: int = 8) -> None:
        self._cv = threading.Condition()
        self.limit = int(value)
        self.max_limit = int(max_limit)
        self.min_limit = int(min_limit)
        self.current = 0
        self.peak = 0
        self.history = [{"at": time.time(), "limit": self.limit, "why": "initial"}]

    def __enter__(self):
        with self._cv:
            while self.current >= self.limit:
                self._cv.wait(timeout=5.0)
            self.current += 1
            if self.current > self.peak:
                self.peak = self.current
        return self

    def __exit__(self, *exc):
        with self._cv:
            self.current -= 1
            self._cv.notify()
        return False

    def set_limit(self, n: int, why: str = "") -> int:
        with self._cv:
            n = max(self.min_limit, min(int(n), self.max_limit))
            if n != self.limit:
                self.limit = n
                self.history.append({"at": time.time(), "limit": n, "why": why})
                self._cv.notify_all()
            return self.limit


def reasoning_kind(msg: dict[str, Any]) -> str | None:
    """cleartext / encrypted / none, from the assistant message as returned."""
    if not isinstance(msg, dict):
        return None
    for key in ("reasoning", "reasoning_content"):
        val = msg.get(key)
        if isinstance(val, str) and val.strip():
            return "cleartext"
        if val:
            return "cleartext"
    details = msg.get("reasoning_details")
    if details:
        try:
            kinds = {d.get("type") for d in details if isinstance(d, dict)}
        except TypeError:
            kinds = set()
        if any(k and "encrypted" in str(k) for k in kinds):
            return "encrypted"
        return "cleartext"
    return "none"


def parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("tool arguments must decode to an object")
    return parsed


def chat_completion(
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    temperature: float,
    max_tokens: int,
    provider_only: str | None = None,
    expect_provider: str | None = None,
    reasoning: dict[str, Any] | None = None,
    semaphore: Any = None,
    timeout: int = 300,
    attempts: int = 5,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (response_json, request_record).

    request_record persists: request params (incl. the reasoning settings), the
    verbatim usage, the returned model + provider, and the cost with its
    provenance label.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ModelError("missing OPENROUTER_API_KEY")

    payload: dict[str, Any] = {
        "model": model,
        "messages": _strip_private(messages),
        "temperature": temperature,
        "max_tokens": max_tokens,
        # Ask OpenRouter to return usage.cost on the completion.
        "usage": {"include": True},
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    if provider_only:
        # Pin one serving provider across all cells: providers differ in how
        # reliably they parse the model's tool-call format, and that difference
        # would otherwise vary within/between conditions.
        payload["provider"] = {"only": [provider_only]}
    if reasoning:
        payload["reasoning"] = dict(reasoning)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Title": "ncs1-explore-sacrifice-pilot-1",
    }
    body = json.dumps(payload).encode("utf-8")
    gate = semaphore if semaphore is not None else _nullgate()

    last_error = None
    response = None
    latency_s = None
    n_attempts = 0
    for attempt in range(attempts):
        n_attempts += 1
        req = urllib.request.Request(OPENROUTER_URL, data=body, headers=headers, method="POST")
        retryable = True
        # The permit brackets the single HTTP attempt only; the backoff sleep
        # below happens with the permit RELEASED (run-experiment #343).
        try:
            with gate:
                t0 = time.time()
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    response = json.loads(resp.read().decode("utf-8"))
                latency_s = time.time() - t0
            if "choices" not in response:
                err = response.get("error") or {}
                code = err.get("code")
                try:
                    code = int(code)
                except (TypeError, ValueError):
                    code = None
                if code in RETRY_CODES or (code is not None and 500 <= code < 600):
                    if code == 429:
                        RATE_LIMIT_HITS["n"] += 1
                    response = None
                    raise _RetryableBody(f"body error {code}: {str(err)[:200]}")
            record_latency(latency_s)
            break
        except _RetryableBody as exc:
            last_error = repr(exc)
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            last_error = f"HTTP {exc.code}: {text[:1000]}"
            if exc.code == 429:
                RATE_LIMIT_HITS["n"] += 1
            if exc.code not in RETRY_CODES:
                retryable = False
        except urllib.error.URLError as exc:
            last_error = repr(exc)
        except (json.JSONDecodeError, TimeoutError) as exc:
            last_error = repr(exc)
        except OSError as exc:
            last_error = repr(exc)
        if not retryable:
            break
        # Jittered exponential backoff, outside the permit.
        time.sleep((2**attempt) * (0.5 + random.random()))

    if response is None:
        raise ModelError(last_error or "chat completion failed")
    if "choices" not in response:
        raise ModelError(f"malformed response: {json.dumps(response)[:600]}")

    returned_model = response.get("model")
    returned_provider = response.get("provider")
    if returned_model != model:
        raise PinMismatch(f"model substitution: requested {model!r}, got {returned_model!r}")
    # `provider.only` may be sent as a provider NAME ("Z.AI") or as an endpoint
    # TAG ("openai", "moonshotai/mxfp4"); OpenRouter reports back the provider
    # NAME either way. `expect_provider` is the name the pin resolves to,
    # verified once per pair by the compute check (DESIGN "Pin rule").
    expected = expect_provider or provider_only
    if provider_only and returned_provider != expected:
        raise PinMismatch(
            f"provider substitution: pinned {provider_only!r} (expect {expected!r}), "
            f"got {returned_provider!r}"
        )

    msg0 = ((response.get("choices") or [{}])[0] or {}).get("message") or {}
    usage = response.get("usage") or {}
    cost = usage.get("cost")
    if cost is None:
        pt = usage.get("prompt_tokens") or 0
        ct = usage.get("completion_tokens") or 0
        cost = pt / 1e6 * FALLBACK_PRICE_IN_PER_M + ct / 1e6 * FALLBACK_PRICE_OUT_PER_M
        cost_source = "estimated from listed price $2.00/M in, $10.00/M out"
    else:
        cost_source = "openrouter-reported"

    request_record = {
        "request": {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "n_tools": len(tools or []),
            "n_messages": len(messages),
            "provider_only": provider_only,
            "expect_provider": expect_provider,
            "reasoning": dict(reasoning) if reasoning else None,
        },
        "usage": usage,  # verbatim
        "returned_model": returned_model,
        "provider": returned_provider,
        "response_id": response.get("id"),
        "finish_reason": (response.get("choices") or [{}])[0].get("finish_reason"),
        "cost": cost,
        "cost_source": cost_source,
        "returned_reasoning_kind": reasoning_kind(msg0),
        "latency_s": latency_s,
        "n_http_attempts": n_attempts,
    }
    return response, request_record


def _strip_private(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop our own bookkeeping keys (`_reasoning`) before sending."""
    out = []
    for m in messages:
        if any(k.startswith("_") for k in m):
            out.append({k: v for k, v in m.items() if not k.startswith("_")})
        else:
            out.append(m)
    return out
