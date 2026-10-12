# CLAUDE.md — ACE+RHG Architecture & Contributor Reference

> Machine-facing architecture reference for agents and contributors. For the
> user-facing overview see `README.md`; for phase/build history see
> `DEVELOPMENT.md`.

## What this is

**ACE** (AI Compliance Engine) scans infrastructure-as-code artifacts, evaluates
them against Rego policies in **OPA**, scores risk, and — in its agentic mode —
reasons about and remediates violations. **RHG** (Release Hardening Gate) wraps
ACE into a deploy/no-deploy decision. A Click **CLI** (`ace`) drives both.

The non-negotiable rule: **OPA is the sole policy authority.** LLM agents only
*propose*; `PatchEngine` is the only thing that mutates an artifact; the gate
decision is deterministic.

```
                        /ace/scan  /ace/mutate  /ace/scan-and-mutate
                 ┌────────────┐ ─────────────────────────────────────┐
   CLI (ace) ────┤  ACE :8000 │                                      ▼
     │  --via ace └────────────┘                                 ┌────────┐
     │                │  /ace/agent (v3 LangGraph loop)          │  OPA   │
     │                └─────────────────────────────────────────▶│ :8181  │
     │  --via rhg                                                └────────┘
     └───────────▶ ┌────────────┐  /rhg/submit  /rhg/agentic-submit
                   │  RHG :8001 │────────▶ ACE ── scan → mutate → re-scan → gate
                   └────────────┘
                        │  Redis Pub/Sub  ──▶  WebSocket /ws/events
                        │  Prometheus metrics (scraped from :9090 / :9091)
                        │  Alerts: Slack (Block Kit) + AWS SQS
```

## Components

| Component | Path | Responsibility |
|---|---|---|
| ACE API | `services/ace/api/routes.py` | `/ace/scan`, `/ace/mutate`, `/ace/scan-and-mutate`, `/ace/notify-mutation`, `/health`, `/metrics` |
| ACE agent API | `services/ace/api/agent_routes.py` | `/ace/agent` — runs the v3 LangGraph release loop |
| RHG API | `services/rhg/api/routes.py` | `/rhg/submit` — v2 scan→mutate→gate pipeline |
| RHG agent proxy | `services/rhg/api/agentic_routes.py` | `/rhg/agentic-submit` — proxies `/ace/agent`, then dispatches the gate alert |
| Parsers | `services/ace/parsers/` | Normalize k8s / terraform / dockerfile / helm / github-actions into a common `NormalizedArtifact` |
| Rule engine | `services/ace/engine/` | `opa_client.py`, `rule_engine.py`, `artifact_codec.py` (decode/encode per type) |
| Mutator | `services/ace/mutator/patch_engine.py` | RFC 6902 JSON Patch apply/diff. Canonical location; `services/rhg/mutator/patch_engine.py` is a re-export shim |
| Scorer | `services/ace/scoring/risk_scorer.py` | Weighted risk score (env multipliers, capped at 10) |
| Agents | `services/ace/agents/` | `graph.py` (LangGraph), `state.py`, context/remediation/verification agents |
| LLM | `services/ace/llm/` | `LLMProvider` ABC + factory (`provider.py`); only `nebius` is registered |
| Alerts | `services/ace/alerts/` | `router.AlertRouter`, `channels/slack.py`, `channels/sqs.py` |
| Metrics | `services/ace/metrics/prometheus.py` | Counters/histograms/gauges + `start_metrics_server` |
| WebSocket | `services/ace/api/websocket.py` | Redis Pub/Sub → `/ws/events` |
| Gate | `services/rhg/gate/evaluator.py` | ALLOW / PATCHED / BLOCK from findings + severity threshold |
| CLI | `cli/ace_compliance/` | `ace scan`, `ace agent`, profile resolution |
| Plugins | `plugins/` | `github-actions/` (npm action), `gitlab/`, `jenkins/`, `argocd/` |

## Request flows

**`POST /ace/scan`** — parse each artifact → OPA evaluate via `POLICY_MAP` →
score → persist nothing (stateless) → respond with findings + risk. Publishes a
`scan.completed` event to Redis and updates metrics.

**`POST /ace/mutate`** — apply a supplied patch set with `PatchEngine`.

**`POST /rhg/submit`** (v2) — scan → mutate → re-scan → `GateEvaluator` →
`SubmitResponse`; dispatches a `gate.decision` alert in a background task.

**`POST /ace/agent`** (v3, `--via ace`) — LangGraph loop:

```
analyzing → reasoning → plan_remediation → mutating
          → compatibility_check → verification → (retry | next_finding) → gate
```

**`POST /rhg/agentic-submit`** (v3, `--via rhg`) — same loop, proxied through
RHG, which additionally fires the gate alert.

## Policy model

- Bundles live in `policies/<bundle>/main.rego` (`cis-kubernetes`,
  `cis-docker`, `nist-800-53`, `github-actions`, plus the `custom/` template).
- `POLICY_MAP` in `services/ace/api/routes.py` maps artifact type → Rego package
  (e.g. `data.cis_docker`). A policy must expose a `deny` set (and optionally
  patch rules) with the finding shape used by the CIS bundles.
- OPA loads `policies/` **once at startup** — restart OPA after editing Rego
  (`docker compose restart opa`). Validate locally with `opa test policies/ -v`.
- `.env` files are **always** excluded from backend/source scans.

## Agentic safety invariants (enforced in code)

- An `INCOMPATIBLE` compatibility verdict escalates even if the verification
  agent says otherwise.
- A `PATCH` plan with an empty patch list is downgraded to `ESCALATE`.
- `SKIP` bypasses the mutator (never applies an empty patch).
- Low confidence, `requires_human_review`, unsafe/out-of-budget retries, missing
  or undecodable artifacts, malformed JSON pointers, and OPA outages all fail
  **closed** to `BLOCK`.
- Without `NEBIUS_API_KEY`, agentic runs fail closed to `BLOCK`.

## Configuration

See `.env.example` for the full list. Highlights:

| Variable | Purpose |
|---|---|
| `MODEL_PROVIDER`, `NEBIUS_API_KEY`, `NEBIUS_BASE_URL`, `NEMOTRON_MODEL` | v3 reasoning backend |
| `AGENT_CONFIDENCE_THRESHOLD`, `AGENT_MAX_RETRIES` | agent loop limits |
| `OPA_URL`, `REDIS_URL` | engine + event bus |
| `BLOCK_ON_SEVERITY`, `MAX_MUTATION_RETRIES` | RHG gate |
| `DASHBOARD_URL` | base URL for report/alerts links (points at Grafana) |
| `SLACK_WEBHOOK_URL`, `SQS_ALERT_QUEUE_URL` | alert channels |

### Deployment profiles (CLI)

`ace scan` / `ace agent` take `--profile [local|cloud|auto]`:

- `local` — force `http://localhost:8000` (ACE) / `http://localhost:8001` (RHG);
  ignores a stray `ACE_URL`.
- `cloud` — require `ACE_URL` / `RHG_URL`.
- `auto` (default) — use `ACE_URL` / `RHG_URL` **if set**, else localhost.

> Gotcha: an exported `ACE_URL` silently redirects a bare `ace scan` to the
> cloud. When debugging a local stack, pass `--profile local` or `unset ACE_URL`.

## Local development

```bash
make install              # deps + editable CLI
make up                   # docker compose: opa, redis, ace, rhg, prometheus, grafana
ace scan samples/ --profile local --fail-on HIGH
make test                 # pytest services/ cli/
make lint                 # ruff
make test-opa             # opa test policies/
make down
```

Ports: ACE `8000` (metrics `9090`), RHG `8001` (metrics `9091`), OPA `8181`,
Redis `6390`, Prometheus `9090`, Grafana `3000`.

**Container notes**
- ACE and RHG build from the same image. Only `services/rhg` is volume-mounted
  into the RHG container; ACE code changes require
  `docker compose up -d --build ace rhg`.
- The RHG container imports the `ace` package, so after editing anything under
  `services/ace/`, rebuild **both** services or RHG will import a stale copy.
- Metrics registry is shared: RHG imports `ace.metrics.prometheus`, so unlabeled
  ACE gauges also appear (at `0`) on the RHG scrape target.

## Testing

```bash
python -m pytest services/ cli/ -q        # full suite
opa test policies/ -v
```

- No `conftest.py` / pytest config. `services/__init__.py` intentionally does
  **not** exist (`services/ace/__init__.py` etc. do), so pytest puts `services/`
  on `sys.path`.
- Policy tests auto-skip when the `opa` binary is absent.
- Keep ruff clean: `ruff check services/ cli/`.

## Repo layout

```
services/ace/     AI Compliance Engine (API, agents, parsers, engine, alerts)
services/rhg/     Release Hardening Gate (gate, v2 pipeline, v3 proxy)
policies/         Rego bundles (cis-kubernetes, cis-docker, nist-800-53, github-actions, custom)
cli/              ace-compliance CLI package
plugins/          CI/CD integrations (github-actions, gitlab, jenkins, argocd)
infra/            observability (prometheus/grafana), docker, helm chart
samples/          Vulnerable example artifacts
```
