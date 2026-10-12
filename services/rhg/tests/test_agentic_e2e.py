"""End-to-end test: RHG ``/rhg/agentic-submit`` -> ACE ``/ace/agent``.

Unlike the unit suites, nothing is mocked at the service boundary here. The RHG
app routes a real HTTP request through an ``ASGITransport`` bound to the ACE
app, so the full chain runs:

    RHG proxy -> ACE scanner (real parsers + real PatchEngine + real codec)
              -> LangGraph release loop -> RHG response mapping

Only two leaves are stubbed, both because they are external processes: OPA
(transport boundary) and the LLM agents (nondeterministic / need an API key).
Everything the two services own between them runs for real.
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from ace.agents.graph import build_release_graph
from ace.agents.state import NextAction, Verdict
from ace.api import agent_routes
from ace.main import app as ace_app
from rhg.api.routes import get_ace_client
from rhg.main import app as rhg_app

VULN_YAML = base64.b64encode(
    b"""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vuln-app
spec:
  template:
    spec:
      containers:
        - name: app
          image: nginx
          securityContext:
            privileged: true
"""
).decode()

FINDING = {
    "rule_id": "CIS-K8S-5.2.1",
    "severity": "HIGH",
    "message": "Privileged container",
    "artifact": "deploy.yaml",
    "patchable": True,
}

PRIVILEGED_PATCH = [
    {"op": "replace", "path": "/spec/containers/0/securityContext/privileged", "value": False}
]

PASS = {"verdict": Verdict.PASS, "next_action": NextAction.GATE, "diagnosis": "fixed"}


class _Context:
    name = "stub-context"

    async def analyze(self, state, finding):
        return {"why_violation_matters": finding.get("message", "")}


class _Remediation:
    name = "stub-remediation"

    def __init__(self, plans):
        self.plans = list(plans)
        self.calls = []

    async def plan(self, finding, context, backend_scan, retry_count=0):
        self.calls.append(finding.get("rule_id"))
        return dict(self.plans[min(len(self.calls) - 1, len(self.plans) - 1)])


class _Verification:
    name = "stub-verification"

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    async def evaluate(
        self, finding, remediation_plan, rescan_findings, compatibility_result, retry_count, max_retries
    ):
        self.calls.append(finding.get("rule_id"))
        return dict(self.results[min(len(self.calls) - 1, len(self.results) - 1)])


def _plan(patches, action="PATCH", confidence=0.95, reason="safe"):
    return {
        "action": action,
        "reason": reason,
        "confidence": confidence,
        "requires_human_review": False,
        "proposed_patches": patches,
    }


def _graph(rem, verif):
    opa = AsyncMock()
    opa.health = AsyncMock(return_value=True)
    opa.evaluate_deny = AsyncMock(return_value=[])
    return build_release_graph(
        agents={"reasoning": _Context(), "plan_remediation": rem, "verification": verif},
        opa_client=opa,
    )


def _body():
    return {
        "pipeline_id": "pipe-e2e",
        "repo": "org/svc",
        "branch": "main",
        "environment": "production",
        "artifacts": [{"type": "kubernetes", "name": "deploy.yaml", "content": VULN_YAML}],
        "backend_source": [],
    }


async def _run(monkeypatch, graph, findings):
    """Wire ACE's OPA stub + agent stub, then POST through the RHG app."""
    monkeypatch.setattr("ace.api.routes.opa.health", AsyncMock(return_value=True))
    monkeypatch.setattr("ace.api.routes.opa.evaluate_deny", AsyncMock(return_value=list(findings)))
    monkeypatch.setattr(agent_routes, "_build_graph", lambda provider: graph)

    client = AsyncClient(transport=ASGITransport(app=ace_app), base_url="http://ace")
    rhg_app.dependency_overrides[get_ace_client] = lambda: client
    try:
        async with AsyncClient(transport=ASGITransport(app=rhg_app), base_url="http://test") as c:
            return await c.post("/rhg/agentic-submit", json=_body())
    finally:
        rhg_app.dependency_overrides.clear()
        await client.aclose()


@pytest.mark.asyncio
class TestAgenticEndToEnd:
    async def test_remediated_release_flows_patched_end_to_end(self, monkeypatch):
        rem = _Remediation([_plan(PRIVILEGED_PATCH)])
        resp = await _run(monkeypatch, _graph(rem, _Verification([PASS])), [FINDING])
        assert resp.status_code == 200
        data = resp.json()
        # The finding reached the graph from the real scanner...
        assert rem.calls == ["CIS-K8S-5.2.1"]
        # ...the real PatchEngine applied it, and RHG relayed PATCHED.
        assert data["decision"] == "PATCHED"
        assert data["mutations_applied"] == 1
        assert data["compatibility_verdict"] == "SKIPPED"
        assert len(data["patched_artifacts"]) == 1
        assert data["patched_artifacts"][0]["patches_applied"]

    async def test_clean_release_allows_end_to_end(self, monkeypatch):
        resp = await _run(monkeypatch, _graph(_Remediation([]), _Verification([])), [])
        assert resp.status_code == 200
        assert resp.json()["decision"] == "ALLOW"

    async def test_escalated_release_blocks_end_to_end(self, monkeypatch):
        rem = _Remediation([_plan(PRIVILEGED_PATCH, confidence=0.4)])
        resp = await _run(monkeypatch, _graph(rem, _Verification([PASS])), [FINDING])
        data = resp.json()
        assert data["decision"] == "BLOCK"
        assert data["escalated"] is True
        assert "0.40" in data["escalation_reason"]
        assert data["patched_artifacts"] == []
