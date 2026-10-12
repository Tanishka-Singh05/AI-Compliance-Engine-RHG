"use strict";

const { test, describe } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  discoverArtifacts,
  discoverBackendSource,
  inferType,
  inferLanguage,
  selectEndpoint,
  formatPRComment,
} = require("../src/lib");

function makeTree(files) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "ace-lib-"));
  for (const [rel, content] of Object.entries(files)) {
    const full = path.join(root, rel);
    fs.mkdirSync(path.dirname(full), { recursive: true });
    fs.writeFileSync(full, content);
  }
  return root;
}

function withTree(t, files) {
  const root = makeTree(files);
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return root;
}

function byName(items, key) {
  return Object.fromEntries(items.map((item) => [item[key], item]));
}

describe("inferType", () => {
  const cases = [
    [".github/workflows/ci.yml", "github_actions"],
    [".github/workflows/release.yaml", "github_actions"],
    ["k8s/deploy.yaml", "kubernetes"],
    ["infra/main.tf", "terraform"],
    ["infra/main.tf.json", "terraform"],
    ["Dockerfile", "dockerfile"],
    ["build/Dockerfile", "dockerfile"],
    ["app.dockerfile", "dockerfile"],
  ];
  for (const [filename, expected] of cases) {
    test(`${filename} -> ${expected}`, () => {
      assert.equal(inferType(filename), expected);
    });
  }
});

describe("inferLanguage", () => {
  test("known extensions", () => {
    assert.equal(inferLanguage("src/app.py"), "python");
    assert.equal(inferLanguage("cmd/main.go"), "go");
    assert.equal(inferLanguage("src/web.ts"), "node");
    assert.equal(inferLanguage("src/util.js"), "node");
  });

  test("falls back to node", () => {
    assert.equal(inferLanguage("notes.txt"), "node");
  });
});

describe("selectEndpoint", () => {
  test("agentic routes to the v3 agentic endpoint", () => {
    assert.equal(selectEndpoint(true), "/rhg/agentic-submit");
  });

  test("non-agentic routes to the v2 endpoint", () => {
    assert.equal(selectEndpoint(false), "/rhg/submit");
    assert.equal(selectEndpoint(undefined), "/rhg/submit");
  });
});

describe("formatPRComment", () => {
  test("v2 reports OPS notification", () => {
    const comment = formatPRComment({
      decision: "ALLOW",
      mutations_applied: 0,
      compatibility_verdict: "COMPATIBLE",
      ops_notified: true,
      report_url: "http://report",
    });
    assert.match(comment, /ACE\+RHG Compliance Gate: \*\*ALLOW\*\*/);
    assert.match(comment, /OPS notified \| Yes/);
    assert.doesNotMatch(comment, /Escalated/);
    assert.match(comment, /\[View full report\]\(http:\/\/report\)/);
  });

  test("v3 reports escalation and reason", () => {
    const comment = formatPRComment({
      decision: "PATCHED",
      mutations_applied: 2,
      compatibility_verdict: "COMPATIBLE",
      escalated: true,
      escalation_reason: "low confidence",
      report_url: "http://report",
    }, true);
    assert.match(comment, /Escalated to human \| Yes/);
    assert.match(comment, /Escalation reason: low confidence/);
    assert.doesNotMatch(comment, /OPS notified/);
  });

  test("lists blocking violations", () => {
    const comment = formatPRComment({
      decision: "BLOCK",
      mutations_applied: 0,
      compatibility_verdict: "INCOMPATIBLE",
      ops_notified: false,
      blocking_findings: [
        { severity: "CRITICAL", rule_id: "K8S_PRIVILEGED", message: "privileged container" },
      ],
      report_url: "http://report",
    });
    assert.match(comment, /### Blocking violations/);
    assert.match(comment, /\*\*\[CRITICAL\]\*\* `K8S_PRIVILEGED` — privileged container/);
  });
});

describe("discoverArtifacts", () => {
  test("finds artifacts, tags types, skips secrets and vendored dirs", (t) => {
    const root = withTree(t, {
      "k8s/deploy.yaml": "kind: Deployment",
      ".github/workflows/ci.yml": "name: ci",
      "infra/main.tf": 'resource "aws_s3_bucket" "b" {}',
      Dockerfile: "FROM alpine",
      "app.dockerfile": "FROM node",
      ".env": "SECRET=1",
      "sub/.env.local": "SECRET=2",
      "node_modules/pkg/thing.yaml": "ignored: true",
      ".git/config": "[core]",
      "README.md": "# hi",
    });

    const artifacts = discoverArtifacts(root);
    const names = artifacts.map((a) => a.name).sort();
    assert.deepEqual(names, [
      ".github/workflows/ci.yml",
      "Dockerfile",
      "app.dockerfile",
      "infra/main.tf",
      "k8s/deploy.yaml",
    ]);

    const byNameMap = byName(artifacts, "name");
    assert.equal(byNameMap["k8s/deploy.yaml"].type, "kubernetes");
    assert.equal(byNameMap[".github/workflows/ci.yml"].type, "github_actions");
    assert.equal(byNameMap["infra/main.tf"].type, "terraform");
    assert.equal(byNameMap.Dockerfile.type, "dockerfile");
    assert.equal(byNameMap["app.dockerfile"].type, "dockerfile");

    assert.equal(
      Buffer.from(byNameMap["k8s/deploy.yaml"].content, "base64").toString("utf8"),
      "kind: Deployment"
    );
  });

  test("returns an empty list for a missing path", (t) => {
    const root = withTree(t, {});
    assert.deepEqual(discoverArtifacts(path.join(root, "does-not-exist")), []);
  });
});

describe("discoverBackendSource", () => {
  test("finds source files and excludes secrets, tests and build output", (t) => {
    const root = withTree(t, {
      "src/app.py": "print('hi')",
      "src/main.go": "package main",
      "src/web.ts": "export {}",
      "src/util.js": "module.exports = {}",
      ".env": "SECRET=1",
      "src/.env": "SECRET=2",
      "tests/test_app.py": "def test(): pass",
      "test/helper.py": "pass",
      "node_modules/dep/index.js": "module.exports = 1",
      "dist/bundle.js": "built",
      "build/out.js": "built",
      "src/vendor.min.js": "minified",
      "__pycache__/cached.py": "cached",
    });

    const sources = discoverBackendSource(root);
    const filenames = sources.map((s) => s.filename).sort();
    assert.deepEqual(filenames, [
      "src/app.py",
      "src/main.go",
      "src/util.js",
      "src/web.ts",
    ]);

    const byNameMap = byName(sources, "filename");
    assert.equal(byNameMap["src/app.py"].language, "python");
    assert.equal(byNameMap["src/main.go"].language, "go");
    assert.equal(byNameMap["src/web.ts"].language, "node");
    assert.equal(byNameMap["src/util.js"].language, "node");
    assert.equal(
      Buffer.from(byNameMap["src/app.py"].content, "base64").toString("utf8"),
      "print('hi')"
    );
  });
});
