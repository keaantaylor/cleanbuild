"""AI providers behind one interface: a single structured (tool) call.

    provider.structured(system, prompt, tool) -> (tool_input_dict, usage)

`tool` is {"name", "description", "input_schema"}; the provider forces that
tool and returns its arguments. Implementations:
- AzureOpenAIProvider: Azure OpenAI in an EU/UK region (settings enforce the
  region), REST via httpx, function calling, temperature 0.
- BedrockProvider: Amazon Bedrock Converse API in an eu-* region, forced tool.
- FakeProvider: deterministic, offline; used by tests (AI_PROVIDER=fake).
get_provider() returns None when AI_PROVIDER=none -- AI is then reported as
not configured, never silently faked.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, ClassVar, Protocol

import httpx

from ..settings import get_settings

Usage = dict[str, Any]
Tool = dict[str, Any]


class AIProviderError(RuntimeError):
    """Customer-safe failure description (never provider response text)."""


class AIProvider(Protocol):
    name: str
    model: str
    region: str

    def structured(self, system: str, prompt: str, tool: Tool) -> tuple[dict[str, Any], Usage | None]: ...


class AzureOpenAIProvider:
    name = "azure_openai"

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        deployment: str,
        api_version: str,
        region: str,
        client: httpx.Client | None = None,
    ) -> None:
        self.endpoint, self.api_key, self.model = endpoint.rstrip("/"), api_key, deployment
        self.api_version, self.region = api_version, region
        self._client = client

    def structured(self, system: str, prompt: str, tool: Tool) -> tuple[dict[str, Any], Usage | None]:
        url = f"{self.endpoint}/openai/deployments/{self.model}/chat/completions"
        body = {
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["input_schema"],
                    },
                }
            ],
            "tool_choice": {"type": "function", "function": {"name": tool["name"]}},
            "temperature": 0,
        }
        client = self._client or httpx.Client(timeout=30)
        try:
            r = client.post(url, params={"api-version": self.api_version}, headers={"api-key": self.api_key}, json=body)
        except httpx.HTTPError as exc:
            raise AIProviderError(f"The AI service could not be reached ({type(exc).__name__}).") from exc
        finally:
            if self._client is None:
                client.close()
        if r.status_code != 200:
            raise AIProviderError(f"The AI service answered HTTP {r.status_code}.")
        try:
            data = r.json()
            call = data["choices"][0]["message"]["tool_calls"][0]["function"]
            if call["name"] != tool["name"]:
                raise AIProviderError("The AI service returned an unexpected function.")
            args = json.loads(call["arguments"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIProviderError("The AI service returned an unreadable response.") from exc
        u = data.get("usage") or {}
        return args, {"input_tokens": u.get("prompt_tokens"), "output_tokens": u.get("completion_tokens")}


class BedrockProvider:
    name = "bedrock"

    def __init__(self, model_id: str, region: str, client: Any | None = None) -> None:
        self.model, self.region = model_id, region
        self._client = client

    def _bedrock(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("bedrock-runtime", region_name=self.region)
        return self._client

    def structured(self, system: str, prompt: str, tool: Tool) -> tuple[dict[str, Any], Usage | None]:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            out = self._bedrock().converse(
                modelId=self.model,
                system=[{"text": system}],
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                toolConfig={
                    "tools": [
                        {
                            "toolSpec": {
                                "name": tool["name"],
                                "description": tool["description"],
                                "inputSchema": {"json": tool["input_schema"]},
                            }
                        }
                    ],
                    "toolChoice": {"tool": {"name": tool["name"]}},
                },
                inferenceConfig={"temperature": 0, "maxTokens": 2048},
            )
        except (BotoCoreError, ClientError) as exc:
            raise AIProviderError(f"The AI service call failed ({type(exc).__name__}).") from exc
        for block in out.get("output", {}).get("message", {}).get("content", []):
            use = block.get("toolUse")
            if use and use.get("name") == tool["name"] and isinstance(use.get("input"), dict):
                u = out.get("usage") or {}
                return dict(use["input"]), {
                    "input_tokens": u.get("inputTokens"),
                    "output_tokens": u.get("outputTokens"),
                }
        raise AIProviderError("The AI service did not return the requested structure.")


_UNTRUSTED = re.compile(r"<untrusted_headers>\s*(.*?)\s*</untrusted_headers>", re.S)


class FakeProvider:
    """Deterministic, offline. For mapping: headers containing a known
    keyword map to a field with confidence 0.9, everything else to null.
    For anything else: `responses[tool_name]` if given. Records every call
    so tests can inspect exactly what would have left the server."""

    name = "fake"
    model = "fake-deterministic-1"
    region = "local"
    KEYWORDS: ClassVar[dict[str, str]] = {
        "clm": "CR0104M",
        "insd": "CR0035M",
        "lossdt": "CR0119CM",
        "ccy": "CR0110CM",
        "stat": "CR0105CM",
    }

    def __init__(self, responses: dict[str, Callable[[str], dict[str, Any]]] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[dict[str, Any]] = []

    def structured(self, system: str, prompt: str, tool: Tool) -> tuple[dict[str, Any], Usage | None]:
        self.calls.append({"system": system, "prompt": prompt, "tool": tool["name"]})
        if tool["name"] in self.responses:
            return self.responses[tool["name"]](prompt), {"input_tokens": len(prompt) // 4, "output_tokens": 10}
        if tool["name"] == "propose_mapping":
            m = _UNTRUSTED.search(prompt)
            columns = json.loads(m.group(1)) if m else []
            mappings = []
            for col in columns:
                header = str(col["header"] if isinstance(col, dict) else col)
                key = re.sub(r"[^a-z]", "", header.lower())
                code = next((c for k, c in self.KEYWORDS.items() if k in key), None)
                mappings.append({"source_column": header, "field_code": code, "confidence": 0.9 if code else 0.0})
            return {"mappings": mappings}, {"input_tokens": len(prompt) // 4, "output_tokens": 10}
        raise AIProviderError(f"The fake provider has no response for {tool['name']}.")


_fake_singleton: FakeProvider | None = None


def get_provider() -> AIProvider | None:
    s = get_settings()
    if s.ai_provider == "azure_openai":
        return AzureOpenAIProvider(
            s.azure_openai_endpoint,
            s.azure_openai_api_key.get_secret_value(),
            s.azure_openai_deployment,
            s.azure_openai_api_version,
            s.azure_openai_region,
        )
    if s.ai_provider == "bedrock":
        return BedrockProvider(s.bedrock_model_id, s.bedrock_region)
    if s.ai_provider == "fake":
        global _fake_singleton
        _fake_singleton = _fake_singleton or FakeProvider()
        return _fake_singleton
    return None


def describe() -> dict[str, Any]:
    """What the Settings page shows: provider, region, model -- no secrets."""
    p = get_provider()
    if p is None:
        return {"configured": False, "provider": None, "region": None, "model": None}
    return {"configured": True, "provider": p.name, "region": p.region, "model": p.model}
