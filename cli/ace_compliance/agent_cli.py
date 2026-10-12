"""``ace agent`` — run the v3 agentic release loop from the CLI.

``ace scan`` only reports findings; ``ace agent`` drives the full ACE agent
loop: parse -> OPA evaluate -> reason -> remediate through ``PatchEngine`` ->
compatibility gate -> ALLOW/PATCHED/BLOCK. It reaches the work over the same
HTTP boundary as every other client.

By default it calls ACE directly (``POST /ace/agent``). Pass ``--via rhg`` to
route through RHG's ``POST /rhg/agentic-submit`` proxy, which additionally
records the gate metric and dispatches the ``gate.decision`` alert.

Exit code is non-zero when the gate blocks, when the residual severity meets
``--fail-on``, or (with ``--fail-on-escalation``) when the loop escalates.
"""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

import click
import httpx

from ace_compliance.config import EndpointError, resolve_ace_url, resolve_rhg_url

SEVERITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}
SEVERITY_CHOICE = click.Choice(["CRITICAL", "HIGH", "MEDIUM", "LOW"])
LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "node",
    ".ts": "node",
    ".go": "go",
    ".java": "java",
    ".rb": "ruby",
    ".rs": "rust",
}
_IGNORE_DIRS = {".git", "node_modules", "__pycache__", "dist", "build", ".venv", "venv"}


@click.command(name="agent")
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.option("--env", default="production", help="Target environment")
@click.option("--output", type=click.Choice(["text", "json"]), default="text")
@click.option("--fail-on", type=SEVERITY_CHOICE, default="HIGH",
              help="Exit non-zero when residual severity is at least this level")
@click.option("--fail-on-escalation", is_flag=True, default=False,
              help="Exit non-zero when the loop escalates to a human")
@click.option("--via", type=click.Choice(["ace", "rhg"]), default="ace",
              help="Call ACE /ace/agent directly (default) or the RHG /rhg/agentic-submit proxy")
@click.option("--profile", type=click.Choice(["local", "cloud", "auto"]), default=None, envvar="ACE_PROFILE",
              help="Deployment profile: local (localhost), cloud (ACE_URL/RHG_URL), or auto (default)")
@click.option("--ace-url", default=None, help="ACE service URL (overrides the profile; used with --via ace)")
@click.option("--rhg-url", default=None, help="RHG service URL (overrides the profile; used with --via rhg)")
@click.option("--backend-path", multiple=True, type=click.Path(exists=True),
              help="Backend source file or directory to analyze (repeatable; .env is never sent)")
@click.option("--repo", default="unknown/repo", show_default=True,
              help="Repository slug (only sent with --via rhg)")
@click.option("--branch", default="main", show_default=True,
              help="Branch name (only sent with --via rhg)")
@click.option("--model-provider", default=None, help="Override the LLM provider the agents use (ACE only)")
@click.option("--max-retries", type=int, default=None, help="Max remediation retries per finding (ACE only)")
@click.option("--confidence-threshold", type=float, default=None,
              help="Minimum agent confidence to patch without escalating (ACE only)")
@click.option("--block-on-severity", type=SEVERITY_CHOICE, default=None,
              help="Severity at/above which a finding blocks the release (ACE only)")
def agent(paths, env, output, fail_on, fail_on_escalation, profile, via, ace_url, rhg_url,
          backend_path, repo, branch, model_provider, max_retries,
          confidence_threshold, block_on_severity):
    """Scan artifacts and run the agentic remediation loop."""
    from ace_compliance.cli import _iter_artifacts, _make_artifact

    if not paths:
        paths = (".",)

    artifacts: list[dict] = []
    for path_str in paths:
        p = Path(path_str)
        if p.is_dir():
            artifacts.extend(_make_artifact(f) for f in _iter_artifacts(p))
        else:
            artifacts.append(_make_artifact(p))

    if not artifacts:
        click.echo("No supported artifacts found.", err=True)
        raise SystemExit(1)

    backend_source = _collect_backend(backend_path)

    try:
        base_url = resolve_rhg_url(profile, rhg_url) if via == "rhg" else resolve_ace_url(profile, ace_url)
    except EndpointError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(2)

    if via == "rhg":
        if any(v is not None for v in (model_provider, max_retries, confidence_threshold, block_on_severity)):
            click.echo(
                "Warning: --model-provider/--max-retries/--confidence-threshold/--block-on-severity "
                "are ignored with --via rhg.",
                err=True,
            )
        payload = {
            "pipeline_id": "cli-agent",
            "repo": repo,
            "branch": branch,
            "environment": env,
            "artifacts": artifacts,
            "backend_source": backend_source,
        }
        endpoint = "/rhg/agentic-submit"
    else:
        payload = {
            "pipeline_id": "cli-agent",
            "environment": env,
            "artifacts": artifacts,
            "backend_source": backend_source,
        }
        if model_provider:
            payload["model_provider"] = model_provider
        if max_retries is not None:
            payload["max_retries"] = max_retries
        if confidence_threshold is not None:
            payload["confidence_threshold"] = confidence_threshold
        if block_on_severity:
            payload["block_on_severity"] = block_on_severity
        endpoint = "/ace/agent"

    asyncio.run(
        _run_agent(base_url, endpoint, payload, output, fail_on, fail_on_escalation)
    )


def _collect_backend(paths) -> list[dict]:
    files: list[Path] = []
    for path_str in paths:
        p = Path(path_str)
        if p.is_dir():
            for f in p.rglob("*"):
                if any(part in _IGNORE_DIRS for part in f.parts):
                    continue
                if f.is_file() and f.suffix in LANGUAGE_BY_SUFFIX:
                    files.append(f)
        elif p.is_file() and p.suffix in LANGUAGE_BY_SUFFIX:
            files.append(p)
    return [_make_backend_file(f) for f in sorted(set(files))]


def _make_backend_file(path: Path) -> dict:
    return {
        "language": LANGUAGE_BY_SUFFIX.get(path.suffix, "unknown"),
        "filename": path.name,
        "content": base64.b64encode(path.read_bytes()).decode(),
    }


async def _run_agent(base_url, endpoint, payload, output, fail_on, fail_on_escalation):
    url = f"{base_url}{endpoint}"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, timeout=300.0)
            resp.raise_for_status()
            result = resp.json()
        except httpx.HTTPStatusError as e:
            click.echo(f"Error: agent request to {url} failed (HTTP {e.response.status_code})", err=True)
            click.echo(e.response.text, err=True)
            if e.response.status_code == 404:
                click.echo(
                    "  Hint: this deployment has no /ace/agent route — it may predate the "
                    "agentic endpoint. Run locally (--profile local) or use --via rhg.",
                    err=True,
                )
            raise SystemExit(1) from e
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            click.echo(f"Error: Cannot connect to agent service at {url}", err=True)
            click.echo("", err=True)
            click.echo("  Make sure the services are running:", err=True)
            click.echo("    docker-compose up -d          # start full stack", err=True)
            click.echo(f"    curl {base_url}/health         # verify it's up", err=True)
            click.echo("", err=True)
            raise SystemExit(1) from e

    if output == "json":
        click.echo(json.dumps(result, indent=2))
    else:
        _print_agent_report(result)

    _enforce(result, fail_on, fail_on_escalation)


def _enforce(result: dict, fail_on: str, fail_on_escalation: bool) -> None:
    blocked = result.get("decision") == "BLOCK"
    if fail_on_escalation and result.get("escalated"):
        raise SystemExit(1)
    if blocked:
        raise SystemExit(1)
    overall = result.get("overall_severity")
    if overall is None:
        severities = [
            f.get("severity", "INFO")
            for f in (result.get("blocked_findings") or result.get("blocking_findings") or [])
        ]
        overall = max(severities, key=lambda s: SEVERITY_ORDER.get(s, 0), default="INFO")
    if SEVERITY_ORDER.get(overall, 0) >= SEVERITY_ORDER.get(fail_on, 0):
        raise SystemExit(1)


def _print_agent_report(result: dict) -> None:
    decision = result.get("decision", "?")
    color = {"ALLOW": "green", "PATCHED": "yellow", "BLOCK": "red"}.get(decision, "white")
    click.echo("")
    click.echo("=" * 60)
    click.echo(f"  Decision:      {click.style(decision, fg=color, bold=True)}")
    if "risk_score" in result:
        click.echo(f"  Risk Score:    {result.get('risk_score')}/10")
    if "overall_severity" in result:
        click.echo(f"  Severity:      {result.get('overall_severity')}")
    click.echo(f"  Mutations:     {result.get('mutations_applied', 0)} applied")
    click.echo(f"  Compatibility: {result.get('compatibility_verdict', '?')}")
    click.echo(f"  Escalated:     {'Yes' if result.get('escalated') else 'No'}")
    click.echo("=" * 60)
    if result.get("escalation_reason"):
        click.echo(f"  ! {result['escalation_reason']}")
    blocked = result.get("blocked_findings") or result.get("blocking_findings") or []
    if blocked:
        click.echo("  Blocking findings:")
        for f in blocked:
            click.echo(f"    [{f.get('severity', '?')}] {f.get('rule_id', '?')}  {f.get('message', '')}")
    resolved = result.get("resolved_findings") or []
    if resolved:
        click.echo(f"  Resolved findings: {len(resolved)}")
    click.echo("")
    if result.get("report_url"):
        click.echo(f"  Report: {result['report_url']}")
    click.echo("")
