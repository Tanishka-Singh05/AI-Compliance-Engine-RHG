import re

import yaml

from .base import BaseParser, NormalizedArtifact
from .kubernetes import KubernetesParser


class HelmParser(BaseParser):
    """Helm templates are Kubernetes manifests with ``{{ }}`` placeholders.

    They are normalized exactly like raw K8s for the OPA input (containers live
    under ``spec.template.spec``), after the template expressions are quoted so
    the YAML parser accepts the file.
    """

    _TEMPLATE_EXPR = re.compile(r"\{\{.*?\}\}")

    def supports(self, filename: str) -> bool:
        base = filename.rsplit("/", 1)[-1]
        return base.endswith((".yaml", ".yml")) and "templates" in filename

    def parse(self, content: str, name: str) -> NormalizedArtifact:
        sanitized = self._TEMPLATE_EXPR.sub("tpl", content)
        try:
            normalized = KubernetesParser().parse(sanitized, name)
        except yaml.YAMLError:
            normalized = None
        raw = normalized.raw if normalized and isinstance(normalized.raw, dict) else {}
        helm_variables = self._extract_template_variables(content)
        kind = normalized.metadata.get("kind", "") if normalized else ""
        return NormalizedArtifact(
            artifact_type="helm",
            name=name,
            raw=raw,
            metadata={
                "api_version": raw.get("apiVersion", ""),
                "kind": kind,
                "template_variables": helm_variables,
                "has_template_expressions": len(helm_variables) > 0,
            },
        )

    def _extract_template_variables(self, content: str) -> list[str]:
        return list(set(re.findall(r'\{\{\s*\.Values\.([\w.]+)\s*\}\}', content)))
