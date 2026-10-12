const core = require("@actions/core");
const github = require("@actions/github");
const axios = require("axios");

const {
  discoverArtifacts,
  discoverBackendSource,
  formatPRComment,
  selectEndpoint,
} = require("./lib");

async function run() {
  const aceUrl = core.getInput("ace-url", { required: true });
  const environment = core.getInput("environment") || "production";
  const agentic = (core.getInput("agentic") || "false").toLowerCase() === "true";
  const artifactsPath = core.getInput("artifacts-path") || "./k8s";
  const backendPath = core.getInput("backend-path") || "./src";
  const token = core.getInput("github-token") || process.env.GITHUB_TOKEN;
  const octokit = github.getOctokit(token);
  const ctx = github.context;

  const artifacts = discoverArtifacts(artifactsPath);
  core.info(`ACE: found ${artifacts.length} artifacts`);

  const backendSource = discoverBackendSource(backendPath);
  core.info(`ACE: found ${backendSource.length} backend source files (.env always excluded)`);

  let result;
  try {
    const endpoint = selectEndpoint(agentic);
    const resp = await axios.post(`${aceUrl}${endpoint}`, {
      pipeline_id: ctx.runId.toString(),
      repo: `${ctx.repo.owner}/${ctx.repo.repo}`,
      branch: ctx.ref.replace("refs/heads/", ""),
      environment,
      artifacts,
      backend_source: backendSource,
    }, { timeout: 120000 });
    result = resp.data;
  } catch (err) {
    core.setFailed(`ACE gate request failed: ${err.message}`);
    return;
  }

  const outcomeHeader = agentic ? "Escalated" : "OPS Notified";
  const outcomeValue = agentic
    ? (result.escalated ? "Yes" : "No")
    : (result.ops_notified ? "Yes" : "No");
  await core.summary
    .addHeading(`ACE+RHG Compliance Gate (${agentic ? "v3 agentic" : "v2"})`)
    .addTable([
      ["Decision", "Mutations", "Compatibility", outcomeHeader],
      [result.decision, (result.mutations_applied ?? 0).toString(),
       result.compatibility_verdict, outcomeValue],
    ])
    .addLink("Full report", result.report_url)
    .write();

  if (ctx.eventName === "pull_request") {
    try {
      await octokit.rest.issues.createComment({
        ...ctx.repo,
        issue_number: ctx.payload.pull_request.number,
        body: formatPRComment(result, agentic),
      });
    } catch (e) {
      core.warning(`Could not post PR comment: ${e.message}`);
    }
  }

  const state = result.decision === "BLOCK" ? "failure" : "success";
  await octokit.rest.repos.createCommitStatus({
    ...ctx.repo,
    sha: ctx.sha,
    state,
    target_url: result.report_url,
    description: `ACE gate: ${result.decision} — ${result.mutations_applied} auto-patches`,
    context: "ace-rhg/compliance-gate",
  });

  if (result.decision === "BLOCK") {
    core.setFailed(
      `ACE gate: BLOCK — ${result.blocking_findings.length} unresolvable violations. See ${result.report_url}`
    );
  } else {
    core.info(`ACE gate: ${result.decision}`);
  }
}

if (require.main === module) {
  run().catch(core.setFailed);
}

module.exports = { run };
