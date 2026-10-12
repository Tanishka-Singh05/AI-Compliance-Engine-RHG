"""Tests for the RHG v3 agentic proxy (``POST /rhg/agentic-submit``).

RHG owns no agent logic here: it forwards a release to ACE's ``/ace/agent`` and
relays the decision. These tests pin that forwarding contract and the mapping
onto the RHG response schema. The ACE client is mocked; no network is used.
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from rhg.api.routes import get_ace_client
from rhg.main import app

DEPLOY_YAML = base64.b64encode(
    b"apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: api\n"
).decode()

ACE_AGENT_RESPONSE = {
    "pipeline_id": "pipe-agent",
    "scan_id": "scan-agent",
    "decision": "PATCHED",
    "risk_score": 6.0,
    "overall_severity": "HIGH",
    "mutations_applied": 2,
    "compatibility_verdict": "COMPATIBLE",
    "escalated": False,
    "escalation_reason": "",
    "findings": [
        {"rule_id": "CIS-K8S-5.2.1", "severity": "HIGH", "artifact": "deploy.yaml", "patchable": True}
    ],
    "blocked_findings": [],
    "resolved_findings": [{"rule_id": "CIS-K8S-5.2.1"}],
    "patched_artifacts": [
        {"name": "deploy.yaml", "content": DEPLOY_YAML, "patches_applied": ["replace /x -> False"]}
    ],
    "audit_trail": [{"step": "gate", "decision": "PATCHED"}],
    "report_url": "http://dashboard/report/scan-agent",
}

ACE_BLOCK_RESPONSE = {
    **ACE_AGENT_RESPONSE,
    "decision": "BLOCK",
    "mutations_applied": 0,
    "compatibility_verdict": "SKIPPED",
    "escalated": True,
    "escalation_reason": "needs a human",
    "patched_artifacts": [],
    "blocked_findings": [
        {"rule_id": "CIS-K8S-5.2.1", "severity": "HIGH", "message": "Privileged", "artifact": "deploy.yaml"}
    ],
}


def _body():
    return {
        "pipeline_id": "pipe-agent",
        "repo": "org/svc",
        "branch": "main",
        "environment": "production",
        "artifacts": [{"type": "kubernetes", "name": "deploy.yaml", "content": DEPLOY_YAML}],
        "backend_source": [],
    }


def _mock_client(data, status=200):
    client = AsyncMock(spec=httpx.AsyncClient)
    resp = AsyncMock(spec=httpx.Response)
    resp.status_code = status
    resp.json.return_value = data
    client.post = AsyncMock(return_value=resp)
    return client


@pytest.mark.asyncio
class TestAgenticSubmit:
    async def test_patched_response_is_relayed(self):
        app.dependency_overrides[get_ace_client] = lambda: _mock_client(ACE_AGENT_RESPONSE)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post("/rhg/agentic-submit", json=_body())
                assert resp.status_code == 200
                data = resp.json()
                assert data["decision"] == "PATCHED"
                assert data["mutations_applied"] == 2
                assert data["compatibility_verdict"] == "COMPATIBLE"
                assert data["patched_artifacts"][0]["name"] == "deploy.yaml"
                assert data["report_url"].endswith("scan-agent")
        finally:
            app.dependency_overrides.clear()

    async def test_forwards_to_the_ace_agent_endpoint(self):
        client = _mock_client(ACE_AGENT_RESPONSE)
        app.dependency_overrides[get_ace_client] = lambda: client
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                await c.post("/rhg/agentic-submit", json=_body())
        finally:
            app.dependency_overrides.clear()

        assert client.post.await_count == 1
        url = client.post.call_args.args[0]
        assert url.endswith("/ace/agent")

    async def test_block_response_surfaces_blocking_findings(self):
        app.dependency_overrides[get_ace_client] = lambda: _mock_client(ACE_BLOCK_RESPONSE)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post("/rhg/agentic-submit", json=_body())
                data = resp.json()
                assert data["decision"] == "BLOCK"
                assert data["escalated"] is True
                assert data["escalation_reason"] == "needs a human"
                assert len(data["blocking_findings"]) == 1
        finally:
            app.dependency_overrides.clear()

    async def test_upstream_failure_becomes_502(self):
        app.dependency_overrides[get_ace_client] = lambda: _mock_client({}, status=500)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post("/rhg/agentic-submit", json=_body())
                assert resp.status_code == 502
        finally:
            app.dependency_overrides.clear()

    async def test_missing_artifacts_is_a_validation_error(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/rhg/agentic-submit", json={"pipeline_id": "x"})
            assert resp.status_code == 422

    async def test_route_is_registered_on_the_app(self):
        paths = {route.path for route in app.routes}
        assert "/rhg/agentic-submit" in paths
