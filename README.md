<div align="center">

<svg viewBox="0 0 680 340" width="340" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <clipPath id="sc">
      <path d="M340 52 L440 90 L440 198 Q440 252 340 280 Q240 252 240 198 L240 90 Z"/>
    </clipPath>
  </defs>
  <path d="M340 48 L444 88 L444 200 Q444 258 340 286 Q236 258 236 200 L236 88 Z" fill="none" stroke="#534AB7" stroke-width="2.5"/>
  <path d="M340 52 L440 90 L440 198 Q440 252 340 280 Q240 252 240 198 L240 90 Z" fill="#EEEDFE"/>
  <g clip-path="url(#sc)" stroke="#AFA9EC" stroke-width="1" fill="none">
    <line x1="240" y1="130" x2="440" y2="130"/>
    <line x1="240" y1="168" x2="440" y2="168"/>
    <line x1="250" y1="208" x2="430" y2="208"/>
    <line x1="290" y1="88" x2="290" y2="280"/>
    <line x1="340" y1="52" x2="340" y2="286"/>
    <line x1="390" y1="88" x2="390" y2="280"/>
    <circle cx="290" cy="130" r="4" fill="#7F77DD" stroke="none"/>
    <circle cx="340" cy="130" r="4" fill="#7F77DD" stroke="none"/>
    <circle cx="390" cy="130" r="4" fill="#7F77DD" stroke="none"/>
    <circle cx="290" cy="168" r="4" fill="#1D9E75" stroke="none"/>
    <circle cx="340" cy="168" r="4" fill="#1D9E75" stroke="none"/>
    <circle cx="390" cy="168" r="4" fill="#1D9E75" stroke="none"/>
    <circle cx="290" cy="208" r="4" fill="#D85A30" stroke="none"/>
    <circle cx="340" cy="208" r="4" fill="#D85A30" stroke="none"/>
    <circle cx="390" cy="208" r="4" fill="#D85A30" stroke="none"/>
  </g>
  <rect x="323" y="152" width="34" height="28" rx="4" fill="#534AB7"/>
  <path d="M329 152 L329 143 Q329 133 340 133 Q351 133 351 143 L351 152" fill="none" stroke="#534AB7" stroke-width="3" stroke-linecap="round"/>
  <circle cx="340" cy="164" r="4" fill="#EEEDFE"/>
  <rect x="338" y="164" width="4" height="7" rx="1" fill="#EEEDFE"/>
  <text x="340" y="316" text-anchor="middle" font-family="system-ui,sans-serif" font-size="22" font-weight="600" letter-spacing="6" fill="#3C3489">ACE+RHG</text>
  <text x="340" y="336" text-anchor="middle" font-family="system-ui,sans-serif" font-size="11" font-weight="400" letter-spacing="2" fill="#888780">AI COMPLIANCE ENGINE · RELEASE HARDENING GATE</text>
</svg>

# ACE + RHG

**Agentic AI Compliance Engine & Release Hardening Gate**

A production-grade DevSecOps platform that enforces security compliance inside CI/CD pipelines — before any artifact reaches production.

<br/>

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![OPA](https://img.shields.io/badge/OPA-0.63-7F77DD?style=flat-square&logo=openpolicyagent&logoColor=white)](https://openpolicyagent.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-agentic-1D9E75?style=flat-square)](https://langchain-ai.github.io/langgraph/)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-EKS-326CE5?style=flat-square&logo=kubernetes&logoColor=white)](https://kubernetes.io)
[![AWS Lambda](https://img.shields.io/badge/AWS-Lambda-FF9900?style=flat-square&logo=awslambda&logoColor=white)](https://aws.amazon.com/lambda/)
[![License](https://img.shields.io/badge/License-MIT-6B7280?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-pytest-0F6E56?style=flat-square&logo=pytest&logoColor=white)](https://pytest.org)

<br/>

[Overview](#-overview) · [Quick start](#-quick-start) · [CLI reference](#-cli-reference) · [Cloud deployment](#-cloud-deployment) · [Supported artifacts](#-supported-artifacts) · [Compliance standards](#-compliance-standards) · [Tech stack](#-tech-stack) · [Contributing](#-contributing)

</div>

---

## Overview

Modern engineering teams ship fast — but speed creates blind spots. Misconfigured Kubernetes pods, over-permissive IAM roles, secrets in environment variables, and container images with critical CVEs routinely make it to production because traditional compliance checks happen *after* deployment.

**ACE+RHG flips that model entirely.**

Every time a developer pushes code, the system submits all deployment artifacts to a two-component enforcement engine:

- **ACE (AI Compliance Engine)** — scans artifacts using OPA/Rego policy bundles against CIS, NIST, and ISO standards, then enriches findings with a LangGraph multi-agent system that reasons about context, cross-artifact risk, and CVE data.
- **RHG (Release Hardening Gate)** — acts as the enforcement layer, deciding whether a release proceeds. For patchable violations, it invokes OPA's mutation engine to auto-fix the artifact and re-scan. For unresolvable findings, it blocks the pipeline and routes to a human review queue.

```
git push  →  CI/CD  →  RHG  →  ACE (OPA + Agents)  →  ALLOW / PATCH / BLOCK
```

---

## Quick start

The CLI talks to either a **local** stack or a **deployed** backend. Which one is
an explicit choice via `--profile` (or the `ACE_PROFILE` environment variable):

| `--profile` | ACE target | RHG target |
|---|---|---|
| `local` | `http://localhost:8000` | `http://localhost:8001` |
| `cloud` | `$ACE_URL` (required) | `$RHG_URL` (required) |
| `auto` (default) | `$ACE_URL` if set, else localhost | `$RHG_URL` if set, else localhost |

An explicit `--ace-url` / `--rhg-url` always overrides the profile.

### Option 1: Cloud

The v2 backend is deployed on AWS. Install the CLI and point it at the API:

```bash
pip install ace-compliance

# Pick the cloud explicitly (recommended) ...
ace scan ./k8s/ --profile cloud   # requires ACE_URL in the environment

# ... or set it once; the default `auto` profile will then prefer it
export ACE_URL=https://fw6mh9jzpc.execute-api.ap-south-1.amazonaws.com
ace scan ./k8s/
```

> A globally exported `ACE_URL` (e.g. added to `~/.zshrc`) is inherited by every
> run, so it will silently shadow a local stack. Use `--profile local` while
> working against Docker Compose, or keep the cloud URL out of your shell profile.

> The current `ace-scan-dev` deployment predates the v3 agentic endpoints, so
> `ace agent` returns 404 there. Run the loop locally (below) or redeploy the v3
> image.

### Option 2: Local development (Docker Compose)

```bash
git clone https://github.com/omkarP-bit/ace-rhg
cd ace-rhg

docker-compose up -d

# Services:
# ACE API    →  http://localhost:8000
# RHG API    →  http://localhost:8001
# OPA        →  http://localhost:8181
# Redis      →  localhost:6390

# Scan and run the agentic loop against the local stack
ace scan  --profile local samples/
ace agent --profile local samples/

# Tear down
docker-compose down
```

---

## CLI reference

### `ace scan` — scan artifacts for compliance violations

```
ace scan <paths...> [options]
```

**Options:**

| Option | Default | Description |
|---|---|---|
| `--env` | `production` | Target environment (`production`, `staging`, `development`) |
| `--output` | `text` | Output format: `text` or `json` |
| `--fail-on` | `HIGH` | Exit 1 if severity >= this level (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`) |
| `--profile` | `auto` | Deployment profile: `local`, `cloud`, or `auto` (or set `ACE_PROFILE`) |
| `--ace-url` | *(profile)* | Override the ACE service URL (wins over the profile) |

**Examples:**

```bash
# Scan a single file
ace scan deploy.yaml

# Scan multiple files
ace scan deploy.yaml Dockerfile main.tf

# Scan a directory recursively (finds .yaml, .yml, .tf, Dockerfile*)
ace scan ./k8s/ ./terraform/

# Scan with staging environment, fail on MEDIUM+
ace scan ./artifacts/ --env staging --fail-on MEDIUM

# JSON output for CI/CD pipelines
ace scan ./artifacts/ --output json

# Pipe to jq for filtering
ace scan ./artifacts/ --output json | jq '.findings[] | select(.severity == "CRITICAL")'

# Override URL inline
ace scan --ace-url https://my-api.example.com ./deploy.yaml

# Force the local Docker Compose stack (ignores an exported ACE_URL)
ace scan --profile local ./k8s/
```

**Text output:**

```
============================================================
  Risk Score:  8.25/10
  Severity:    HIGH
  Findings:    7
============================================================
  [HIGH] CIS-K8S-5.2.2  vulnerable-deploy.yaml
       Container runs as root (UID 0): app
  [MEDIUM] CIS-K8S-5.4.1  vulnerable-deploy.yaml
       No CPU limit on container: app
  [HIGH] CIS-K8S-5.2.1  vulnerable-deploy.yaml
       Privileged container: app
```

**JSON output:**

```json
{
  "scan_id": "aed62885-d061-4554-96be-5fbfe56823cc",
  "pipeline_id": "cli-scan",
  "risk_score": 8.25,
  "overall_severity": "HIGH",
  "findings": [
    {
      "severity": "HIGH",
      "rule_id": "CIS-K8S-5.2.2",
      "message": "Container runs as root (UID 0): app",
      "artifact": "vulnerable-deploy.yaml",
      "patchable": true,
      "reference": "https://kubernetes.io/docs/tasks/configure-pod-container/security-context/"
    }
  ]
}
```

### `ace agent` — run the agentic release loop

```
ace agent <paths...> [options]
```

Scans the artifacts exactly like `ace scan`, then drives the v3 LangGraph loop
(reason → remediate → compatibility gate) and exits non-zero on `BLOCK`, on a
residual severity at/above `--fail-on`, or on escalation with
`--fail-on-escalation`.

**Options:**

| Option | Default | Description |
|---|---|---|
| `--env` | `production` | Target environment |
| `--output` | `text` | Output format: `text` or `json` |
| `--fail-on` | `HIGH` | Exit 1 if residual severity >= this level |
| `--fail-on-escalation` | off | Exit 1 when the loop escalates to a human |
| `--via` | `ace` | `ace` → `POST /ace/agent`; `rhg` → `POST /rhg/agentic-submit` |
| `--profile` | `auto` | Deployment profile: `local`, `cloud`, or `auto` |
| `--ace-url` | *(profile)* | ACE service URL override (`--via ace`) |
| `--rhg-url` | *(profile)* | RHG service URL override (`--via rhg`) |
| `--backend-path` | *(none)* | Backend source file/dir to analyze (repeatable; `.env` is never sent) |
| `--repo` | `unknown/repo` | Repository slug (`--via rhg`) |
| `--branch` | `main` | Branch name (`--via rhg`) |
| `--model-provider` | `$MODEL_PROVIDER` | LLM provider override (ACE only) |
| `--max-retries` | `$AGENT_MAX_RETRIES` | Retries per finding (ACE only) |
| `--confidence-threshold` | `$AGENT_CONFIDENCE_THRESHOLD` | Below this, escalate to a human (ACE only) |
| `--block-on-severity` | `HIGH` | Severity at/above which a finding blocks (ACE only) |

**Examples:**

```bash
# Local agentic run against Docker Compose
ace agent ./k8s/ --profile local

# Include backend source for agent context
ace agent ./k8s/ --backend-path ./src --output json

# Route through RHG (records the gate metric and dispatches the gate alert)
ace agent ./k8s/ --via rhg --profile local

# Fail the pipeline if the loop had to escalate
ace agent ./k8s/ --fail-on-escalation
```

### Choosing local vs cloud

The CLI resolves its target in this order (highest priority first):

1. `--ace-url` / `--rhg-url` (explicit flag)
2. `--profile` / `ACE_PROFILE` → `local` (localhost), `cloud` (`$ACE_URL`/`$RHG_URL`), or `auto`
3. `ACE_URL` / `RHG_URL` when the profile is `auto`
4. `http://localhost:8000` / `http://localhost:8001`

```bash
# Force the local stack, ignoring any exported ACE_URL
ace scan  ./k8s/ --profile local
ace agent ./k8s/ --profile local

# Force cloud (requires ACE_URL; add RHG_URL for --via rhg)
ACE_URL=https://fw6mh9jzpc.execute-api.ap-south-1.amazonaws.com \
  ace agent ./k8s/ --profile cloud

# Set the profile once for the session
export ACE_PROFILE=local

# One-off override, beats everything
ace scan ./k8s/ --ace-url http://localhost:8000
```

### Exit codes

The exit code makes CI/CD gating easy:

```bash
# Block deployment on HIGH or above (default)
ace scan ./k8s/ && echo "Deploy allowed" || echo "Blocked"

# Block only on CRITICAL
ace scan ./k8s/ --fail-on CRITICAL && echo "Deploy allowed" || echo "Blocked"
```

| Severity | Exit 1 with `--fail-on` |
|---|---|
| `CRITICAL` | `--fail-on CRITICAL` |
| `HIGH` | `--fail-on HIGH` (default) |
| `MEDIUM` | `--fail-on MEDIUM` |
| `LOW` | `--fail-on LOW` |
| `INFO` | never |

---

## Cloud deployment

The backend runs fully managed on AWS. No infrastructure to manage.

```
CLI (your machine)
  │
  │  HTTPS (managed TLS)
  ▼
API Gateway v2 (HTTP API)
  │
  │  Lambda Proxy
  ▼
Lambda: ace-scan-dev (FastAPI + Mangum)
  │
  │  OPA_URL (remote)
  ▼
OPA Policy Engine (shared/remote service)
```

**AWS Resources:**

| Resource | Endpoint / ARN |
|---|---|
| API Gateway | `https://fw6mh9jzpc.execute-api.ap-south-1.amazonaws.com` |
| Scan Lambda | `arn:aws:lambda:ap-south-1:574772738717:function:ace-scan-dev` |
| Dispatcher Lambda | `arn:aws:lambda:ap-south-1:574772738717:function:ace-dispatcher-dev` |
| Alerts queue | `arn:aws:sqs:ap-south-1:574772738717:ace-alerts-dev.fifo` |
| ECR | `574772738717.dkr.ecr.ap-south-1.amazonaws.com/ace-rhg-dev:latest` |
| OPA | ECS Fargate service `ace-opa-dev` (public IP) — via `OPA_URL` |

**Deploy / update:**

The scan and dispatcher Lambdas are built from `infra/docker/Dockerfile.lambda`
and pushed to ECR `ace-rhg-dev:latest`. OPA runs as a standalone ECS Fargate
service (`ace-opa-dev`, 0.25 vCPU / 512 MB, public subnet + public IP, no ALB/NAT)
provisioned with the AWS CLI; its image (OPA + the repo's Rego bundles) lives in
ECR `ace-opa-dev:latest`. The scan Lambda calls OPA over the network via its
`OPA_URL` env var — no OPA runs inside the Lambda.

Because the Fargate task has no load balancer, its public IP is ephemeral; after a
task restart, read the new IP (`aws ecs describe-tasks` →
`aws ec2 describe-network-interfaces`) and update `ace-scan-dev`'s `OPA_URL`. The
dispatcher overrides `ImageConfig.Command` to
`handlers.alert_dispatcher_handler.handler` and consumes `ace-alerts-dev.fifo`.
See `infra/docker/Dockerfile.*` and `infra/aws_lambda/`.

**API Endpoints:**

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/ace/scan` | Scan artifacts for violations |
| POST | `/ace/mutate` | Generate patches for findings |
| POST | `/ace/scan-and-mutate` | Scan + auto-generate patches |

> **v3 agentic routes are not deployed here.** The `ace-scan-dev` stack exposes
> only the v2 routes above. The v3 endpoints — `POST /ace/agent` (ACE) and
> `POST /rhg/agentic-submit` (RHG) — require redeploying the v3 image; until
> then `ace agent` returns HTTP 404 against this URL. Run the loop locally with
> `ace agent ./k8s/ --profile local`.

**Direct API usage:**

```bash
# Health check
curl https://fw6mh9jzpc.execute-api.ap-south-1.amazonaws.com/health

# Scan via API
curl -X POST https://fw6mh9jzpc.execute-api.ap-south-1.amazonaws.com/ace/scan \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline_id": "my-pipeline-001",
    "environment": "production",
    "artifacts": [{
      "type": "kubernetes",
      "name": "deployment.yaml",
      "content": "'$(base64 -w0 ./k8s/deployment.yaml)'"
    }]
  }'
```

HTTPS is provided automatically by AWS — no certificate setup needed for `*.execute-api.*.amazonaws.com`.

---

## Supported artifacts

| Artifact type | Extensions | Policy bundle | Auto-mutation |
|---|---|---|---|
| Kubernetes manifests | `.yaml`, `.yml` | `cis-kubernetes@v1.8` | Yes |
| Terraform plans | `.tf`, `.tf.json` | `cis-terraform@v1.4` | Yes |
| Helm charts | `.yaml` (templates) | `cis-kubernetes@v1.8` | Yes |
| Dockerfiles | `Dockerfile`, `*.dockerfile` | `cis-docker@v1.6` | Yes |
| GitHub Actions | `.yaml` (workflows) | `gha-security` | Yes |

When scanning a directory, the CLI recursively finds all supported files.

---

## Compliance standards

| Standard | Coverage |
|---|---|
| CIS Kubernetes Benchmark v1.8 | Privileged containers, root user, CPU/memory limits, privilege escalation, host network |
| CIS Docker Benchmark v1.6 | Root user, missing HEALTHCHECK |
| NIST SP 800-53 Rev 5 | AC-6 least privilege, CM-2 baseline config, SI-7 integrity |
| GitHub Actions Security | Write-all permissions, mutable tags, pull_request_target, script injection |

---

## CI/CD integration

### GitHub Actions

```yaml
- name: ACE Compliance Scan
  run: |
    pip install ace-compliance
    ace scan ./k8s/ ./terraform/ --output json --fail-on HIGH
  env:
    ACE_URL: https://fw6mh9jzpc.execute-api.ap-south-1.amazonaws.com
```

### GitLab CI

```yaml
ace-scan:
  image: python:3.12-slim
  script:
    - pip install ace-compliance
    - ace scan ./k8s/ --output json --fail-on HIGH
  variables:
    ACE_URL: https://fw6mh9jzpc.execute-api.ap-south-1.amazonaws.com
```

### Pre-commit hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: ace-scan
        name: ACE Compliance Scan
        entry: bash -c 'pip install ace-compliance && ace scan . --fail-on HIGH'
        language: system
        files: \.(yaml|yml|tf|dockerfile)$
```

---

## Tech stack

```
Backend          FastAPI 0.111 · Python 3.12 · Pydantic v2
Policy engine    Open Policy Agent 0.63 · Rego
Agent layer      LangGraph · NVIDIA Nemotron (Nebius Token Factory) · Groq Llama 3.3 70B
LLM access       ace.llm.LLMProvider — one ABC, providers behind a factory
Orchestration    MCP (Model Context Protocol) server
Event bus        Redis Pub/Sub → WebSocket (FastAPI)
Observability    Prometheus · Grafana · structlog
Alerting         Slack Block Kit · AWS SQS
Infrastructure   Docker · AWS Lambda · API Gateway v2 · ECR
CLI              Click · httpx · PyYAML (pip install ace-compliance)
```

### Agentic release loop (v3)

Beyond the scan/mutate/gate pipeline, ACE ships a LangGraph loop that reasons
about each finding, proposes a remediation, applies it, re-scans, and routes to
ALLOW / PATCHED / BLOCK:

```
analyzing → reasoning → plan_remediation → mutating
          → compatibility_check → verification → (retry | next_finding)
          → gate
```

Configure the reasoning backend:

| Variable | Default | Purpose |
|---|---|---|
| `MODEL_PROVIDER` | `nebius` | Which registered `LLMProvider` to use |
| `NEBIUS_API_KEY` | *(empty)* | Nebius Token Factory key |
| `NEBIUS_BASE_URL` | `https://api.studio.nebius.ai/v1` | Override for a gateway |
| `NEMOTRON_MODEL` | `nvidia/nemotron-3-super-120b-a12b` | Model id |
| `AGENT_CONFIDENCE_THRESHOLD` | `0.85` | Below this, escalate to a human |
| `AGENT_MAX_RETRIES` | `3` | Retries per finding, on top of the first attempt |

The agents reason; they never decide. OPA is the sole policy authority, only
`PatchEngine` mutates, and an `INCOMPATIBLE` compatibility verdict cannot be
overridden by the model. With no `NEBIUS_API_KEY` set, agentic runs **fail
closed** to `BLOCK` rather than shipping unreviewed patches — the rest of ACE
keeps working normally.

---

## Repository structure

```
ace-rhg/
├── README.md
├── CLAUDE.md                ← Architecture & contributor reference
├── DEVELOPMENT.md           ← Phase/build status report
├── LICENSE                  ← MIT
├── Makefile                 ← install / test / lint / build / up / helm targets
├── Dockerfile               ← Lambda container image (FastAPI + Mangum)
├── docker-compose.yml       ← Local dev stack (ace, rhg, opa, redis, prometheus, grafana)
├── .pre-commit-config.yaml  ← ruff, yaml/json checks, OPA + ACE hooks
├── requirements-dev.txt     ← Dev + service dependencies
│
├── services/
│   ├── ace/                 ← AI Compliance Engine
│   │   ├── api/             ← REST + WebSocket routes
│   │   ├── agents/          ← LangGraph release loop + context/remediation/verification agents
│   │   ├── llm/             ← LLMProvider ABC, Nebius/Nemotron backend, factory
│   │   ├── parsers/         ← K8s / Terraform / Dockerfile / Helm / GHA parsers
│   │   ├── engine/          ← OPA client, rule engine, artifact codec
│   │   ├── mutator/         ← JSON Patch engine (canonical location)
│   │   ├── scoring/         ← Risk scorer
│   │   ├── alerts/          ← Slack, SQS, alert router
│   │   ├── mcp/             ← MCP server and tool registry
│   │   └── tests/           ← 245 tests
│   │
│   └── rhg/                 ← Release Hardening Gate
│       ├── api/
│       ├── gate/            ← Policy evaluator
│       ├── mutator/         ← Re-export shim → ace.mutator.patch_engine
│       └── tests/           ← 50 tests
│
├── policies/                ← OPA Rego bundles
│   ├── cis-kubernetes/
│   ├── cis-docker/
│   ├── cis-docker-compose/
│   ├── cis-terraform/
│   ├── nist-800-53/
│   ├── github-actions/
│   └── custom/              ← Custom-policy template (wire into POLICY_MAP)
│
├── cli/                     ← ace-compliance CLI package
│   ├── ace_compliance/
│   └── pyproject.toml
│
├── plugins/                 ← CI/CD integrations
│   ├── github-actions/      ← npm action
│   ├── gitlab/
│   ├── jenkins/
│   └── argocd/              ← Application + PreSync gate
│
├── infra/                   ← Deployment & observability
│   ├── helm/ace-rhg/        ← Helm chart (ACE, RHG, OPA, Redis)
│   ├── docker/              ← Combined ACE+RHG service image
│   └── observability/       ← Prometheus + Grafana provisioning
│
└── samples/                 ← Example vulnerable artifacts
```

---

## Testing

```bash
# Run all tests
pytest services/ cli/ -v --cov=services --cov-report=term-missing

# Run OPA policy tests
opa test policies/ -v

# Specific suites
pytest services/ace/tests/test_parsers.py -v      # Parsers
pytest services/ace/tests/test_scan_api.py -v     # Scan API
pytest services/ace/tests/test_llm_provider.py -v # LLM provider abstraction
pytest services/ace/tests/test_agents_v3.py -v    # Agents + state contract
pytest services/ace/tests/test_release_graph.py -v # LangGraph release loop
pytest services/rhg/tests/ -v                     # RHG gate + mutator
pytest cli/tests/ -v                              # CLI
```

**326 tests passing** (ACE 245 · RHG 50 · CLI 29 · Lambda handlers 2)

---

## Contributing

```bash
git clone https://github.com/omkarP-bit/ace-rhg
cd ace-rhg
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
```

**Areas for contribution:**
- New Rego policies (CloudFormation, Ansible, GitHub Actions)
- Additional parser implementations
- Agent specializations (PR review, dependency audit)
- GCP / Azure provider support

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

Built with by [Omkar](https://github.com/omkarP-bit)

*Shift security left. Ship with confidence.*

</div>
