package custom.example

# Template policy — a harmless placeholder that keeps `opa test policies/` green.
#
# This package is NOT referenced by POLICY_MAP, so ACE never evaluates it. To add
# a real custom policy:
#   1. Copy this file and rename the `package` to e.g. `custom.teamname`.
#   2. Implement your `deny` (and optional patch) rules against the normalized
#      artifact `input` — see the CIS bundles for the expected finding shape.
#   3. Register the new package in POLICY_MAP (services/ace/api/routes.py).
#
# The guard below is intentionally impossible to trigger.

deny[msg] {
    input.kind == "__CUSTOM_RESOURCE_PLACEHOLDER__"
    msg := {
        "rule_id": "CUSTOM-000",
        "message": "Placeholder rule; replace with your own logic",
        "severity": "LOW",
        "patchable": false,
    }
}
