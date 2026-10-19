import json
import re

from .base import BaseParser, NormalizedArtifact

_RESOURCE_START = re.compile(r'resource\s+"([^"]+)"\s+"([^"]+)"\s*\{')
_BLOCK_HEADER = re.compile(r'^([A-Za-z_][\w-]*)\s*\{\s*$')
_ATTR = re.compile(r'^([A-Za-z_][\w-]*)\s*=\s*(.+)$')
_LIST_SCALAR = re.compile(r'^"([^"]*)"$|^(-?\d+(?:\.\d+)?)$|^(true|false)$')


def _blank_noise(text: str) -> str:
    """Blank out string literals and comments so brace matching ignores them."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == '"':
                    break
                j += 1
            for k in range(i, min(j + 1, n)):
                out[k] = " "
            i = j + 1
        elif c == "#" or (c == "/" and i + 1 < n and text[i + 1] == "/"):
            while i < n and text[i] != "\n":
                out[i] = " "
                i += 1
        else:
            i += 1
    return "".join(out)


def _block_body(content: str, blanked: str, open_pos: int) -> tuple[str, int]:
    """Return the body of the block whose ``{`` is at ``open_pos`` (and its end)."""
    depth = 0
    for i in range(open_pos, len(blanked)):
        c = blanked[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return content[open_pos + 1:i], i
    return content[open_pos + 1:], len(content)


def _parse_scalar(raw: str):
    value = raw.strip().rstrip(",")
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value in ("true", "false"):
        return value == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    if value.startswith("[") and value.endswith("]"):
        items = []
        for part in value[1:-1].split(","):
            part = part.strip()
            if not part:
                continue
            m = _LIST_SCALAR.match(part)
            items.append(_parse_scalar(part) if m else part.strip('"'))
        return items
    return value


def _parse_body(body: str) -> dict:
    """Parse a subset of HCL body syntax into a dict of attributes/blocks."""
    values: dict = {}
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        block = _BLOCK_HEADER.match(line)
        if block:
            key = block.group(1)
            collected: list[str] = []
            depth = 1
            while i < len(lines) and depth > 0:
                stripped = lines[i].strip()
                i += 1
                if stripped == "}":
                    depth -= 1
                    if depth == 0:
                        break
                if _BLOCK_HEADER.match(stripped):
                    depth += 1
                collected.append(lines[i - 1])
            values.setdefault(key, [])
            values[key].append(_parse_body("\n".join(collected)))
            continue
        attr = _ATTR.match(line)
        if not attr:
            continue
        key, val = attr.group(1), attr.group(2).strip()
        while val.endswith("[") and val.count("[") > val.count("]"):
            if i >= len(lines):
                break
            val += " " + lines[i].strip()
            i += 1
        values[key] = _parse_scalar(val)
    return values


class TerraformParser(BaseParser):
    """Understands both ``terraform show -json`` plans and raw HCL ``.tf`` files.

    The CIS Terraform bundle reads ``input.metadata.resources``. The scan route
    forwards ``normalized.raw`` to OPA, so the extracted resources are published
    under ``raw.metadata.resources`` — otherwise every rule silently matches
    nothing and Terraform scans report a clean pass.
    """

    def supports(self, filename: str) -> bool:
        return filename.endswith((".tf", ".tf.json", "tfplan.json"))

    def parse(self, content: str, name: str) -> NormalizedArtifact:
        try:
            plan = json.loads(content)
        except json.JSONDecodeError:
            plan = self._hcl_to_plan(content)
        resources = self._extract_resources(plan)
        for index, resource in enumerate(resources):
            resource["_index"] = index
        types = list({r["type"] for r in resources})
        return NormalizedArtifact(
            artifact_type="terraform",
            name=name,
            raw={
                "metadata": {"resources": resources, "resource_types": types},
                "resource_changes": plan.get("resource_changes", []),
            },
            metadata={
                "resources": resources,
                "resource_types": types,
                "provider": plan.get("configuration", {}).get("provider_config", {}),
            },
        )

    @staticmethod
    def _hcl_to_plan(content: str) -> dict:
        """Convert ``resource "type" "name" { ... }`` blocks into a plan-like dict."""
        blanked = _blank_noise(content)
        changes = []
        # Resource headers are matched against the original text (the blanked copy
        # has the quoted type/name erased); brace matching uses the blanked copy.
        for match in _RESOURCE_START.finditer(content):
            # Skip matches erased by _blank_noise (i.e. inside comments/strings).
            if not blanked[match.start():match.start() + 8].strip():
                continue
            rtype, rname = match.group(1), match.group(2)
            open_pos = match.end() - 1
            body, _ = _block_body(content, blanked, open_pos)
            changes.append({
                "address": f"{rtype}.{rname}",
                "type": rtype,
                "change": {"actions": ["create"], "after": _parse_body(body)},
            })
        return {"resource_changes": changes}

    def _extract_resources(self, plan: dict) -> list[dict]:
        changes = plan.get("resource_changes", [])
        return [
            {
                "address": c["address"],
                "type": c["type"],
                "change_action": c["change"]["actions"],
                "values": c["change"].get("after", {}),
            }
            for c in changes
            if c.get("change", {}).get("actions") != ["no-op"]
        ]
