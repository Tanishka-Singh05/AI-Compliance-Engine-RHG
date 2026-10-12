# Argo CD integration

Gate an Argo CD sync on an ACE scan. The **PreSync hook** (`presync-scan.yaml`)
runs `ace scan` before Argo CD applies the Application's resources; a non-zero
exit code (a HIGH/CRITICAL finding, or `--fail-on`) aborts the sync.

## Files

| File | Purpose |
|---|---|
| `application.yaml` | Example Argo CD `Application` that deploys the Helm chart in `infra/helm/ace-rhg`. |
| `presync-scan.yaml` | `PreSync` Job that scans the manifests under review and fails the sync on a blocking finding. |

## Usage

1. Deploy ACE/RHG (see the Helm chart) and note the ACE service URL.
2. Provide the manifests to scan as a ConfigMap (one key per file):

   ```bash
   kubectl create configmap ace-presync-manifests \
     --from-file=deployment.yaml=./k8s/deployment.yaml \
     --from-file=service.yaml=./k8s/service.yaml
   ```

3. Apply the Application:

   ```bash
   kubectl apply -f application.yaml
   ```

4. To attach the gate to an Application you already manage, copy the hook
   annotations from `presync-scan.yaml` onto the Job and place it in the same
   source path. Argo CD discovers hooks by annotation, not by directory.

## Notes

- The hook installs the CLI on the fly (`pip install ace-compliance`). For
  air-gapped clusters, bake the CLI (or the `ace` package) into your own image
  and drop the `pip install` step.
- `--fail-on HIGH` blocks on HIGH and CRITICAL. Use `--fail-on-escalation` to
  also fail when the agentic loop escalates to a human.
- Point `ACE_URL` at your in-cluster ACE service (`http://<release>-ace:8000`).
