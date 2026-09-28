"""P2.6 -- AI behind one interface: EU/UK providers, masked samples, fake for tests.

Acceptance:
- only EU/UK hosting can be configured (Bedrock eu-*, Azure EU/UK regions);
  the fake provider cannot run in production;
- masking keeps a value's shape, never its content;
- during ingest the provider receives only the headers the alias stage
  could not match plus up to three MASKED samples each -- no cell value
  leaves the server; AI suggestions are stored MAPPED_BY_AI in review and are
  never applied without a person confirming them (processing is refused
  until the sheet is confirmed);
- with no provider configured, AI is reported as not configured and
  headers stay UNMAPPED -- never guessed;
- Azure OpenAI and Bedrock adapters send the forced tool call to the right
  place and parse the structured reply; failures become customer-safe
  errors without echoing provider text.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from app.ai import providers
from app.ai.masking import mask_value, masked_samples
from app.ai.providers import AIProviderError, AzureOpenAIProvider, BedrockProvider, FakeProvider
from app.models.jobs import Job
from app.settings import Settings
from conftest import Api, run_jobs, xlsx_bytes
from pydantic import ValidationError
from sqlalchemy.orm import Session

from bordereaux import mapping as engine_mapping

TOOL = {"name": "propose_mapping", "description": "d", "input_schema": {"type": "object"}}


@pytest.mark.parametrize(
    ("env", "fragment"),
    [
        ({"AI_PROVIDER": "bedrock", "BEDROCK_REGION": "us-east-1"}, "EU region"),
        ({"AI_PROVIDER": "azure_openai", "AZURE_OPENAI_REGION": "eastus"}, "EU/UK Azure region"),
        (
            {"AI_PROVIDER": "fake", "TRUEBIND_ENV": "production", "SECRET_KEY": "x" * 40,
             "DATABASE_URL": "postgresql://u:p@h/db"},
            "tests only",
        ),
    ],
)  # fmt: skip
def test_only_eu_uk_providers_can_be_configured(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str], fragment: str
) -> None:
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(ValidationError, match=fragment):
        Settings()


def test_eu_regions_are_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "azure_openai")
    monkeypatch.setenv("AZURE_OPENAI_REGION", "swedencentral")
    assert Settings().azure_openai_region == "swedencentral"


def test_masking_keeps_shape_not_content() -> None:
    assert mask_value("Harbour Freight Ltd") == "Xxxxxxx Xxxxxxx Xxx"
    assert mask_value("2024-03-15") == "9999-99-99"
    assert mask_value("GBP 1,250.00") == "XXX 9,999.99"
    assert mask_value(None) is None and mask_value("  ") is None
    assert len(mask_value("x" * 200) or "") == 24
    assert masked_samples(["A1", "B2", "C3", "D4"]) == ["X9"], "duplicate shapes collapse"


HEADERS = ["Clm No.", "Insd Nm", "LossDt", "Claim Status", "Currency", "Paid to Date", "Outstanding Reserve",
           "Total Incurred"]  # fmt: skip


def _odd_headers_file() -> bytes:
    rows: list[list[Any]] = [
        HEADERS,
        ["ZZ-99812", "Wexford Distinctive Holdings", "2024-01-15", "Open", "GBP", 10, 5, 15],
        ["ZZ-99813", "Kilkenny Unusual Traders", "2024-01-16", "Open", "GBP", 20, 5, 25],
    ]  # fmt: skip
    return xlsx_bytes(rows)


def test_ingest_sends_only_headers_and_masked_samples(api: Api, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeProvider()
    monkeypatch.setattr(providers, "get_provider", lambda: fake)
    rid = api.ingest("odd.xlsx", _odd_headers_file())
    assert fake.calls, "the provider was consulted for the unmatched headers"
    prompt = fake.calls[0]["prompt"]
    for secret in ("Wexford Distinctive Holdings", "ZZ-99812", "Kilkenny"):
        assert secret not in prompt, secret
    block = json.loads(prompt.split("<untrusted_headers>")[1].split("</untrusted_headers>")[0])
    sent = {c["header"]: c["masked_samples"] for c in block}
    unmatched = {h for h, sg in engine_mapping.fuzzy_match_headers(HEADERS).items() if sg.method == "unmapped"}
    assert "Insd Nm" in unmatched
    assert set(sent) == unmatched, "only headers the alias stage could not match"
    assert sent["Insd Nm"] == ["Xxxxxxx Xxxxxxxxxxx Xxxx", "Xxxxxxxx Xxxxxxx Xxxxxxx"]  # capped at 24 chars

    sheet = api.get(f"/api/v1/reports/{rid}/sheets").json()[0]
    fields = api.get(f"/api/v1/reports/{rid}/sheets/{sheet['id']}/mapping").json()["fields"]
    by_code = {f["field_code"]: f for f in fields}
    ref = by_code["CR0035M"]
    assert ref["source_column"] == "Insd Nm" and ref["mapping_state"] == "MAPPED_BY_AI"
    assert ref["confirmed"] is False and ref["ai_model"] == "fake:fake-deterministic-1"
    assert api.post(f"/api/v1/reports/{rid}/process").status_code == 409, "never applied without confirmation"

    job = db.query(Job).filter_by(report_id=rid, kind="INGEST").one()
    metrics = job.metrics or {}
    assert metrics["ai_calls"] == 1


def test_without_a_provider_headers_stay_unmapped(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(providers, "get_provider", lambda: None)
    rid = api.ingest("odd.xlsx", _odd_headers_file())
    sheet = api.get(f"/api/v1/reports/{rid}/sheets").json()[0]
    fields = api.get(f"/api/v1/reports/{rid}/sheets/{sheet['id']}/mapping").json()["fields"]
    ref = next(f for f in fields if f["field_code"] == "CR0035M")
    assert ref["source_column"] is None and ref["mapping_state"] == "UNMAPPED"
    run_jobs()


def _azure(handler: Any) -> AzureOpenAIProvider:
    return AzureOpenAIProvider(
        "https://tb-eu.openai.azure.com/",
        "azure-key-value",
        "gpt-mapping",
        "2024-10-21",
        "swedencentral",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_azure_openai_adapter() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        call = {"name": "propose_mapping", "arguments": json.dumps({"mappings": []})}
        body = {"choices": [{"message": {"tool_calls": [{"function": call}]}}], "usage": {"prompt_tokens": 12}}
        return httpx.Response(200, json=body)

    args, usage = _azure(handler).structured("sys", "prompt", TOOL)
    assert args == {"mappings": []} and usage == {"input_tokens": 12, "output_tokens": None}
    [req] = seen
    assert req.url.path == "/openai/deployments/gpt-mapping/chat/completions"
    assert req.url.params["api-version"] == "2024-10-21" and req.headers["api-key"] == "azure-key-value"
    sent = json.loads(req.content)
    assert sent["tool_choice"] == {"type": "function", "function": {"name": "propose_mapping"}}
    assert sent["temperature"] == 0


def test_azure_errors_are_customer_safe() -> None:
    def failing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal detail: prompt was ...")

    with pytest.raises(AIProviderError) as err:
        _azure(failing).structured("s", "p", TOOL)
    assert "internal detail" not in str(err.value) and "500" in str(err.value)


def test_bedrock_adapter() -> None:
    import boto3
    from botocore.stub import ANY, Stubber

    client = boto3.client(
        "bedrock-runtime", region_name="eu-central-1", aws_access_key_id="x", aws_secret_access_key="y"
    )
    stub = Stubber(client)
    tool_use = {"toolUse": {"toolUseId": "t1", "name": "propose_mapping", "input": {"mappings": []}}}
    stub.add_response(
        "converse",
        {
            "output": {"message": {"role": "assistant", "content": [tool_use]}},
            "stopReason": "tool_use",
            "usage": {"inputTokens": 7, "outputTokens": 3, "totalTokens": 10},
            "metrics": {"latencyMs": 1},
        },
        {
            "modelId": "eu.anthropic.test-model",
            "system": ANY,
            "messages": ANY,
            "toolConfig": ANY,
            "inferenceConfig": ANY,
        },
    )
    with stub:
        args, usage = BedrockProvider("eu.anthropic.test-model", "eu-central-1", client=client).structured(
            "s", "p", TOOL
        )
    assert args == {"mappings": []} and usage == {"input_tokens": 7, "output_tokens": 3}
    assert client.meta.region_name == "eu-central-1"


def test_describe_never_exposes_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(providers, "get_provider", lambda: _azure(lambda r: httpx.Response(200)))
    d = providers.describe()
    assert d == {"configured": True, "provider": "azure_openai", "region": "swedencentral", "model": "gpt-mapping"}
