"""Regression tests for the CIS-DL-1.1 ``image_pinned`` helper.

These evaluate the real Rego policy through the ``opa`` binary, so they are
skipped when ``opa`` is not on PATH (as in CI, which runs the Python suite
without an OPA install).
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
POLICY_DIR = REPO_ROOT / "policies" / "cis-docker"

pytestmark = pytest.mark.skipif(
    shutil.which("opa") is None, reason="opa binary not installed"
)


def _image_pinned(image: str) -> bool:
    proc = subprocess.run(
        [
            "opa",
            "eval",
            "-d",
            str(POLICY_DIR),
            "--format",
            "json",
            "--stdin-input",
            "data.ace.cis.docker.image_pinned(input)",
        ],
        input=json.dumps(image),
        text=True,
        capture_output=True,
        check=True,
    )
    result = json.loads(proc.stdout).get("result") or []
    if not result:
        return False
    return bool(result[0]["expressions"][0].get("value"))


@pytest.mark.parametrize(
    ("image", "pinned"),
    [
        ("python:3.13-slim@sha256:" + "0" * 64, True),
        ("ghcr.io/org/app@sha256:abc123", True),
        ("python:3.13-slim", True),
        ("localhost:5000/img:1.0", True),
        ("python:latest", False),
        ("python", False),
        ("localhost:5000/img", False),
    ],
)
def test_image_pinned(image: str, pinned: bool) -> None:
    assert _image_pinned(image) is pinned
