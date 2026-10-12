from unittest.mock import AsyncMock, MagicMock, patch

from ace_compliance.cli import cli
from click.testing import CliRunner

MOCK_AGENT_RESPONSE = {
    "pipeline_id": "cli-agent",
    "scan_id": "scan-1",
    "decision": "PATCHED",
    "risk_score": 6.1,
    "overall_severity": "MEDIUM",
    "mutations_applied": 2,
    "compatibility_verdict": "COMPATIBLE",
    "escalated": False,
    "escalation_reason": "",
    "findings": [
        {"rule_id": "CIS-K8S-5.2.1", "severity": "HIGH",
         "message": "Privileged container", "artifact": "deploy.yaml", "patchable": True}
    ],
    "blocked_findings": [],
    "resolved_findings": [{"rule_id": "CIS-K8S-5.2.1", "severity": "HIGH"}],
    "patched_artifacts": [
        {"name": "deploy.yaml", "content": "abc", "patches_applied": ["remove_privileged"]}
    ],
    "audit_trail": [{"step": "gate", "decision": "PATCHED"}],
    "report_url": "http://localhost:3000/report/scan-1",
}


def _patch_client(response):
    client = MagicMock()
    post = AsyncMock(
        return_value=MagicMock(
            status_code=200,
            json=lambda: response,
            raise_for_status=lambda: None,
            text="",
        )
    )
    client.return_value.__aenter__.return_value.post = post
    return client, post


class TestAgentCLI:
    def setup_method(self):
        self.runner = CliRunner()

    def _artifact(self, tmp_path):
        f = tmp_path / "deploy.yaml"
        f.write_text("apiVersion: v1\nkind: Pod")
        return f

    def test_command_is_registered(self):
        assert "agent" in cli.commands

    def test_calls_ace_agent_endpoint(self, tmp_path):
        f = self._artifact(tmp_path)
        client, post = _patch_client(MOCK_AGENT_RESPONSE)
        with patch("ace_compliance.agent_cli.httpx.AsyncClient", client):
            result = self.runner.invoke(
                cli, ["agent", str(f)], env={"ACE_URL": "http://localhost:8000"}
            )
            assert result.exit_code == 0
            assert post.call_args.args[0] == "http://localhost:8000/ace/agent"

    def test_profile_local_overrides_ambient_ace_url(self, tmp_path):
        f = self._artifact(tmp_path)
        client, post = _patch_client(MOCK_AGENT_RESPONSE)
        with patch("ace_compliance.agent_cli.httpx.AsyncClient", client):
            result = self.runner.invoke(
                cli,
                ["agent", str(f), "--profile", "local"],
                env={"ACE_URL": "https://cloud.example.com"},
            )
            assert result.exit_code == 0
            assert post.call_args.args[0] == "http://localhost:8000/ace/agent"

    def test_profile_cloud_without_url_errors(self, tmp_path):
        f = self._artifact(tmp_path)
        result = self.runner.invoke(
            cli, ["agent", str(f), "--profile", "cloud"], env={"ACE_URL": ""}
        )
        assert result.exit_code == 2
        assert "requires ACE_URL" in result.output

    def test_via_rhg_calls_proxy_endpoint(self, tmp_path):
        f = self._artifact(tmp_path)
        client, post = _patch_client(MOCK_AGENT_RESPONSE)
        with patch("ace_compliance.agent_cli.httpx.AsyncClient", client):
            result = self.runner.invoke(
                cli, ["agent", str(f), "--via", "rhg", "--rhg-url", "http://rhg:8001"]
            )
            assert result.exit_code == 0
            assert post.call_args.args[0] == "http://rhg:8001/rhg/agentic-submit"
            payload = post.call_args.kwargs["json"]
            assert payload["repo"] == "unknown/repo"
            assert payload["branch"] == "main"

    def test_exits_nonzero_on_block(self, tmp_path):
        f = self._artifact(tmp_path)
        blocked = {
            **MOCK_AGENT_RESPONSE,
            "decision": "BLOCK",
            "compatibility_verdict": "INCOMPATIBLE",
            "blocked_findings": [
                {"rule_id": "K8S_PRIVILEGED", "severity": "CRITICAL", "message": "privileged"}
            ],
        }
        client, _ = _patch_client(blocked)
        with patch("ace_compliance.agent_cli.httpx.AsyncClient", client):
            result = self.runner.invoke(cli, ["agent", str(f)])
            assert result.exit_code == 1

    def test_exits_nonzero_when_severity_meets_fail_on(self, tmp_path):
        f = self._artifact(tmp_path)
        severe = {**MOCK_AGENT_RESPONSE, "decision": "ALLOW", "overall_severity": "CRITICAL"}
        client, _ = _patch_client(severe)
        with patch("ace_compliance.agent_cli.httpx.AsyncClient", client):
            result = self.runner.invoke(cli, ["agent", str(f), "--fail-on", "HIGH"])
            assert result.exit_code == 1

    def test_fail_on_escalation(self, tmp_path):
        f = self._artifact(tmp_path)
        escalated = {**MOCK_AGENT_RESPONSE, "escalated": True, "escalation_reason": "low confidence"}
        client, _ = _patch_client(escalated)
        with patch("ace_compliance.agent_cli.httpx.AsyncClient", client):
            no_fail = self.runner.invoke(cli, ["agent", str(f)])
            assert no_fail.exit_code == 0
            fail = self.runner.invoke(cli, ["agent", str(f), "--fail-on-escalation"])
            assert fail.exit_code == 1

    def test_json_output(self, tmp_path):
        f = self._artifact(tmp_path)
        client, _ = _patch_client(MOCK_AGENT_RESPONSE)
        with patch("ace_compliance.agent_cli.httpx.AsyncClient", client):
            result = self.runner.invoke(cli, ["agent", str(f), "--output", "json"])
            assert result.exit_code == 0
            assert '"decision": "PATCHED"' in result.output

    def test_backend_path_is_sent(self, tmp_path):
        f = self._artifact(tmp_path)
        backend = tmp_path / "backend"
        backend.mkdir()
        (backend / "app.py").write_text("print('hi')")
        client, post = _patch_client(MOCK_AGENT_RESPONSE)
        with patch("ace_compliance.agent_cli.httpx.AsyncClient", client):
            result = self.runner.invoke(cli, ["agent", str(f), "--backend-path", str(backend)])
            assert result.exit_code == 0
            payload = post.call_args.kwargs["json"]
            assert payload["backend_source"][0]["filename"] == "app.py"
            assert payload["backend_source"][0]["language"] == "python"

    def test_no_artifacts(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        result = self.runner.invoke(cli, ["agent", str(empty)])
        assert result.exit_code == 1
        assert "No supported artifacts found" in result.output
