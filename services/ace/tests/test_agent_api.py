"""Tests for the v3 agentic HTTP surface (``POST /ace/agent``).

The scanning path (``/ace/scan``) and the release graph both have their own
suites. These tests pin the *seam between them*: that findings produced by the
scanner are threaded into the graph, that the graph's decision and patched
artifacts are surfaced in the response, and that the documented schema is
stable. The graph's agents are stubbed (deterministic); the scanner, artifact
codec and ``PatchEngine`` run for real. OPA is stubbed at the transport
boundary only.
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from ace.agents.graph import build_release_graph
from ace.agents.state import NextAction, Verdict
from ace.api import agent_routes
from ace.main import app

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


def _plan(patches, action="PATCH", confidence=0.95, review=False, reason="safe"):
    return {
        "action": action,
        "reason": reason,
        "confidence": confidence,
        "requires_human_review": review,
        "proposed_patches": patches,
    }


def _graph(rem, verif, rescan_findings=None):
    opa = AsyncMock()
    opa.health = AsyncMock(return_value=True)
    opa.evaluate_deny = AsyncMock(return_value=list(rescan_findings or []))
    return build_release_graph(
        agents={"reasoning": _Context(), "plan_remediation": rem, "verification": verif},
        opa_client=opa,
    )


def _body(**overrides):
    body = {
        "pipeline_id": "pipe-agent",
        "environment": "production",
        "artifacts": [{"type": "kubernetes", "name": "deploy.yaml", "content": VULN_YAML}],
    }
    body.update(overrides)
    return body


def _stub_scan(monkeypatch, findings):
    monkeypatch.setattr("ace.api.routes.opa.health", AsyncMock(return_value=True))
    monkeypatch.setattr("ace.api.routes.opa.evaluate_deny", AsyncMock(return_value=list(findings)))


async def _post(monkeypatch, graph, findings, **overrides):
    _stub_scan(monkeypatch, findings)
    monkeypatch.setattr(agent_routes, "_build_graph", lambda provider: graph)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/ace/agent", json=_body(**overrides))


@pytest.mark.asyncio
class TestAgentEndpoint:
    async def test_no_findings_allows_immediately(self, monkeypatch):
        resp = await _post(monkeypatch, _graph(_Remediation([]), _Verification([])), [])
        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] == "ALLOW"
        assert data["mutations_applied"] == 0
        assert data["patched_artifacts"] == []

    async def test_finding_is_remediated_and_decision_is_patched(self, monkeypatch):
        graph = _graph(_Remediation([_plan(PRIVILEGED_PATCH)]), _Verification([PASS]))
        resp = await _post(monkeypatch, graph, [FINDING])
        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] == "PATCHED"
        assert data["escalated"] is False
        assert data["mutations_applied"] == 1
        assert len(data["patched_artifacts"]) == 1
        assert data["patched_artifacts"][0]["name"] == "deploy.yaml"
        assert data["patched_artifacts"][0]["patches_applied"]
        assert data["compatibility_verdict"] == "SKIPPED"

    async def test_scanner_findings_are_threaded_into_the_graph(self, monkeypatch):
        rem = _Remediation([_plan(PRIVILEGED_PATCH)])
        resp = await _post(monkeypatch, _graph(rem, _Verification([PASS])), [FINDING])
        assert resp.status_code == 200
        assert rem.calls == ["CIS-K8S-5.2.1"]
        assert resp.json()["findings"][0]["rule_id"] == "CIS-K8S-5.2.1"

    async def test_low_confidence_escalates_to_block(self, monkeypatch):
        graph = _graph(_Remediation([_plan(PRIVILEGED_PATCH, confidence=0.4)]), _Verification([PASS]))
        resp = await _post(monkeypatch, graph, [FINDING])
        data = resp.json()
        assert data["decision"] == "BLOCK"
        assert data["escalated"] is True
        assert "0.40" in data["escalation_reason"]
        assert data["patched_artifacts"] == []

    async def test_escalated_finding_is_surfaced_as_blocked(self, monkeypatch):
        graph = _graph(
            _Remediation([_plan([], action="ESCALATE", reason="needs a human")]),
            _Verification([PASS]),
        )
        resp = await _post(monkeypatch, graph, [FINDING])
        data = resp.json()
        assert data["decision"] == "BLOCK"
        assert data["blocked_findings"]
        assert data["blocked_findings"][0]["rule_id"] == "CIS-K8S-5.2.1"

    async def test_audit_trail_is_returned(self, monkeypatch):
        graph = _graph(_Remediation([_plan(PRIVILEGED_PATCH)]), _Verification([PASS]))
        resp = await _post(monkeypatch, graph, [FINDING])
        steps = [entry["step"] for entry in resp.json()["audit_trail"]]
        assert "gate" in steps
        assert "mutation_applied" in steps

    async def test_response_has_every_documented_field(self, monkeypatch):
        graph = _graph(_Remediation([_plan(PRIVILEGED_PATCH)]), _Verification([PASS]))
        resp = await _post(monkeypatch, graph, [FINDING])
        expected = {
            "pipeline_id", "scan_id", "decision", "risk_score", "overall_severity",
            "mutations_applied", "compatibility_verdict", "escalated", "escalation_reason",
            "findings", "blocked_findings", "resolved_findings", "patched_artifacts",
            "audit_trail", "report_url",
        }
        assert expected <= set(resp.json().keys())

    async def test_returns_503_when_opa_is_down(self, monkeypatch):
        monkeypatch.setattr("ace.api.routes.opa.health", AsyncMock(return_value=False))
        monkeypatch.setattr(
            agent_routes, "_build_graph", lambda provider: _graph(_Remediation([]), _Verification([]))
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/ace/agent", json=_body())
        assert resp.status_code == 503

    async def test_agent_route_is_registered_on_the_app(self):
        # app.routes may hold router wrappers without `.path` on some FastAPI
        # versions; the OpenAPI schema is the stable, resolved view of paths.
        paths = set(app.openapi()["paths"])
        assert "/ace/agent" in paths
