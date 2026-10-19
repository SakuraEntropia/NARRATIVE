"""Small structured-output provider boundary with a deterministic offline mock.

External providers are explicit Python adapters; no key, network call, or vendor
SDK is required by this package. Their reported usage must come from the API.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError

from .memory import Budget, Telemetry, estimate_units


class Provider(Protocol):
    name: str
    live: bool

    def generate(self, request: dict[str, Any]) -> ProviderResponse | dict[str, Any] | str:
        ...


@dataclass
class ProviderResponse:
    content: dict[str, Any] | str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None


class ProviderOutputError(ValueError):
    """The provider did not satisfy the output contract within finite retries."""


class OutputRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MockProvider:
    name = "offline-template"
    live = False

    def generate(self, request: dict[str, Any]) -> ProviderResponse:
        parent = request["node"]
        level = min(parent["level"] + 1, 9)
        kind = {1: "Arc", 2: "Act", 3: "Arc", 4: "Act", 5: "Sequence",
                6: "Beat", 7: "Scene", 8: "Event", 9: "Event"}.get(level, "Scene")
        content = {
            "children": [
                {"label": f"{parent['label']} / establish", "kind": kind,
                 "purpose": "Template slot: establish a prerequisite or open question",
                 "attributes": {"template_slot": "establish", "requires_authoring": True}},
                {"label": f"{parent['label']} / consequence", "kind": kind,
                 "purpose": "Template slot: develop a consequence or unresolved choice",
                 "attributes": {"template_slot": "consequence", "requires_authoring": True}},
                {"label": f"{parent['label']} / transformation", "kind": kind,
                 "purpose": "Template slot: locate a transformation that needs authoring",
                 "attributes": {"template_slot": "transformation", "requires_authoring": True}},
                {"label": f"{parent['label']} / payoff", "kind": kind,
                 "purpose": "Template slot: reserve space for a setup or payoff",
                 "attributes": {"template_slot": "payoff", "requires_authoring": True}},
            ],
            "information_gain": 0.25 if level <= 7 else 0.0,
            "feedback": ["Template decomposition requires author review; no literary quality is inferred"],
            "uncertainty": "Deterministic structural template; no inferred events or validated prose",
        }
        content["children"] = content["children"][:request.get("max_children", 2)]
        return ProviderResponse(content, prompt_tokens=0, completion_tokens=0, cost_usd=0.0)


class CallableProvider:
    """Adapter for an explicitly configured provider returning API usage.

    Credentials stay inside the caller's function and are never serialized.
    Set live=True for any adapter that may call a billed external service.
    """

    def __init__(self, name: str, generate: Callable[[dict[str, Any]], Any], *, live: bool = True):
        self.name, self.live, self._generate = name, live, generate

    def generate(self, request: dict[str, Any]) -> ProviderResponse | dict[str, Any] | str:
        return self._generate(request)


ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


def structured_generate(provider: Provider, request: dict[str, Any],
                        response_model: type[ResponseModel], *, budget: Budget | None = None,
                        telemetry: Telemetry | None = None, max_retries: int = 1,
                        max_response_units: int = 24_000) -> ResponseModel:
    """Validate every response, retry at most max_retries times, record real usage.

    Context and call reservations precede each provider invocation. A response
    that exceeds the bounded output size is rejected before JSON validation.
    Under a monetary cap, live adapters with unknown maximum cost fail safely.
    """
    if not 0 <= max_retries <= 3 or max_response_units < 1:
        raise ValueError("Retries must be in 0..3 and response size must be positive")
    telemetry = telemetry if telemetry is not None else Telemetry()
    telemetry.provider = provider.name
    live = bool(getattr(provider, "live", True))
    if live:
        if telemetry.calls == 0:
            telemetry.prompt_tokens = telemetry.completion_tokens = None
            telemetry.estimated_api_cost_usd = None
    started = time.perf_counter()
    base_request = dict(request)
    error = ""
    for attempt in range(max_retries + 1):
        current_request = dict(base_request)
        current_request["output_schema"] = response_model.model_json_schema()
        if error:
            current_request["validation_feedback"] = error[:1000]
        context_units = estimate_units(current_request)
        if budget is not None:
            budget.reserve(context_units=context_units, calls=1, cost_usd=None if live else 0.0)
        telemetry.estimated_context_units += context_units
        telemetry.calls += 1
        telemetry.retries += int(attempt > 0)
        try:
            raw = provider.generate(current_request)
            result = raw if isinstance(raw, ProviderResponse) else ProviderResponse(raw)
            if not live:
                result.prompt_tokens = result.completion_tokens = 0
                result.cost_usd = 0.0
            else:
                for field, reported in (("prompt_tokens", result.prompt_tokens),
                                        ("completion_tokens", result.completion_tokens),
                                        ("estimated_api_cost_usd", result.cost_usd)):
                    previous = getattr(telemetry, field)
                    complete = reported is not None and (telemetry.calls == 1 or previous is not None)
                    setattr(telemetry, field, (previous or 0) + reported if complete else None)
            content_units = estimate_units(result.content)
            telemetry.estimated_output_units += content_units
            if budget is not None:
                budget.reserve(output_units=content_units, cost_usd=result.cost_usd)
            if content_units > max_response_units:
                raise ProviderOutputError(f"Provider response exceeds {max_response_units} byte units")
            payload = json.loads(result.content) if isinstance(result.content, str) else result.content
            value = response_model.model_validate(payload)
            telemetry.latency_seconds += time.perf_counter() - started
            return value
        except (ValidationError, json.JSONDecodeError, TypeError, ProviderOutputError) as exc:
            error = f"{type(exc).__name__}: {exc}"
        except Exception:
            telemetry.latency_seconds += time.perf_counter() - started
            raise
    telemetry.latency_seconds += time.perf_counter() - started
    raise ProviderOutputError(f"Provider output rejected after {max_retries + 1} attempt(s): {error}")
