# Custom policies

Drop your own Rego bundles here. This directory is a **template/placeholder** —
nothing in it is evaluated until you wire it into ACE.

## How ACE loads policies

ACE's policy map lives in `services/ace/api/routes.py` (`POLICY_MAP`). It maps a
normalized artifact type to a Rego package, for example:

```python
POLICY_MAP = {
    "kubernetes": "data.cis_kubernetes",
    "dockerfile": "data.cis_docker",
    ...
}
```

OPA is started with the entire `policies/` tree mounted, so **any** package you
add under this directory is available at `data.<package>`. To have ACE evaluate
it, add an entry to `POLICY_MAP` pointing at the new package and make sure the
parser that produces the artifact's normalized form is selected in `PARSERS`.

## Contract a policy must satisfy

For a given artifact type, ACE reads:

- `data.<pkg>.deny` — a set of finding objects (the violations).
- an optional patch rule per rule id (see the CIS bundles for the shape used by
  the `PatchEngine`).

A minimal deny rule looks like:

```rego
package custom.example

deny[msg] {
    input.kind == "CustomResource"
    not input.metadata.labels["owner"]
    msg := {
        "rule_id": "CUSTOM-001",
        "message": "CustomResource is missing an owner label",
        "severity": "MEDIUM",
        "patchable": false,
    }
}
```

## Testing

`example.rego` in this directory is a no-op template that keeps `opa test
policies/` green. Replace or delete it once you add real rules. Run:

```bash
opa test policies/ -v
```
