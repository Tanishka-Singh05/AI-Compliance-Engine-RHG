// Dependency-free helpers for the ACE+RHG GitHub Action.
//
// Kept separate from index.js so they can be unit-tested with `node --test`
// and no npm install: index.js pulls in @actions/* and axios, while everything
// here uses only the Node standard library.
//
// Artifact discovery uses a recursive fs walk rather than `glob`, so the action
// carries one less runtime dependency and the matching rules are explicit.

const fs = require("fs");
const path = require("path");

const ARTIFACT_IGNORE_DIRS = new Set([".git", "node_modules"]);
const BACKEND_IGNORE_DIRS = new Set([
  ".git",
  "node_modules",
  "__pycache__",
  "dist",
  "build",
  "test",
  "tests",
]);

const ARTIFACT_SUFFIXES = [".yaml", ".yml", ".tf", ".tf.json", ".dockerfile"];
const BACKEND_SUFFIXES = [".py", ".js", ".ts", ".go"];

function toPosix(relativePath) {
  return relativePath.split(path.sep).join("/");
}

function isEnvFile(name) {
  return name === ".env" || name.startsWith(".env.");
}

// Recursively list file paths under rootPath, skipping ignored directories and
// any file the ignoreFile predicate rejects. Unreadable directories are
// skipped rather than crashing the action.
function walkFiles(rootPath, { ignoreDirs = new Set(), ignoreFile = () => false } = {}) {
  const found = [];
  const visit = (dir) => {
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      if (entry.isDirectory()) {
        if (!ignoreDirs.has(entry.name)) visit(path.join(dir, entry.name));
      } else if (entry.isFile() && !ignoreFile(entry.name)) {
        found.push(path.join(dir, entry.name));
      }
    }
  };
  visit(rootPath);
  return found;
}

function isArtifactName(name) {
  return name === "Dockerfile" || ARTIFACT_SUFFIXES.some((suffix) => name.endsWith(suffix));
}

function discoverArtifacts(rootPath) {
  return walkFiles(rootPath, { ignoreDirs: ARTIFACT_IGNORE_DIRS, ignoreFile: isEnvFile })
    .filter((full) => isArtifactName(path.basename(full)))
    .map((full) => {
      const name = toPosix(path.relative(rootPath, full));
      return {
        type: inferType(name),
        name,
        content: fs.readFileSync(full).toString("base64"),
      };
    });
}

function discoverBackendSource(rootPath) {
  const ignored = (name) => isEnvFile(name) || name.endsWith(".min.js");
  return walkFiles(rootPath, { ignoreDirs: BACKEND_IGNORE_DIRS, ignoreFile: ignored })
    .filter((full) => BACKEND_SUFFIXES.some((suffix) => path.basename(full).endsWith(suffix)))
    .map((full) => {
      const filename = toPosix(path.relative(rootPath, full));
      return {
        language: inferLanguage(filename),
        filename,
        content: fs.readFileSync(full).toString("base64"),
      };
    });
}

function inferType(filename) {
  const normalized = toPosix(filename);
  if (normalized.includes(".github/workflows")) return "github_actions";
  if (normalized.endsWith(".tf") || normalized.endsWith(".tf.json")) return "terraform";
  if (normalized.includes("Dockerfile") || normalized.endsWith(".dockerfile")) {
    return "dockerfile";
  }
  return "kubernetes";
}

function inferLanguage(filename) {
  if (filename.endsWith(".py")) return "python";
  if (filename.endsWith(".go")) return "go";
  return "node";
}

function selectEndpoint(agentic) {
  return agentic ? "/rhg/agentic-submit" : "/rhg/submit";
}

function formatPRComment(result, agentic = false) {
  const icon = { ALLOW: ":white_check_mark:", BLOCK: ":x:", PATCHED: ":wrench:" }[result.decision] || ":grey_question:";
  let comment = `## ${icon} ACE+RHG Compliance Gate: **${result.decision}**\n\n`;
  comment += `| Metric | Value |\n|---|---|\n`;
  comment += `| Auto-mutations applied | ${result.mutations_applied ?? 0} |\n`;
  comment += `| Compatibility check | ${result.compatibility_verdict} |\n`;
  if (agentic) {
    comment += `| Escalated to human | ${result.escalated ? "Yes" : "No"} |\n\n`;
  } else {
    comment += `| OPS notified | ${result.ops_notified ? "Yes" : "No"} |\n\n`;
  }
  if (agentic && result.escalation_reason) {
    comment += `> Escalation reason: ${result.escalation_reason}\n\n`;
  }
  if (result.blocking_findings && result.blocking_findings.length) {
    comment += "### Blocking violations\n";
    for (const f of result.blocking_findings) {
      comment += `- **[${f.severity}]** \`${f.rule_id}\` — ${f.message}\n`;
    }
    comment += "\n";
  }
  comment += `[View full report](${result.report_url})`;
  return comment;
}

module.exports = {
  walkFiles,
  isEnvFile,
  isArtifactName,
  discoverArtifacts,
  discoverBackendSource,
  inferType,
  inferLanguage,
  selectEndpoint,
  formatPRComment,
};
