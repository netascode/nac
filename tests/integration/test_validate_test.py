# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""Integration tests: real `nac validate`/`nac test` against the real,
published `uvx nac-validate`/`uvx nac-test` tools (no mocking of the
underlying tools), using a minimal fixture under
`tests/integration/fixtures/validate_test/`.

These tests shell out (via uvx) to PyPI-published packages and therefore
require network access, so they are excluded from the default run via the
`integration` marker.
"""

import shutil
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nac.cli.main import app

pytestmark = pytest.mark.integration

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "validate_test"


def _make_config(tmp_path: Path) -> Path:
    """Copy the fixture (schema/data/templates) into tmp_path and write a
    nac.yaml alongside it with unpinned nac-validate/nac-test tool versions
    (so uvx resolves the latest published release from PyPI).
    """
    shutil.copytree(FIXTURES_DIR, tmp_path, dirs_exist_ok=True)

    cfg_path = tmp_path / "nac.yaml"
    cfg_path.write_text(
        """\
data:
  paths:
    - data/
validate:
  schema: .schema.yaml
test:
  templates: templates
  output: output
"""
    )
    return cfg_path


@pytest.mark.integration
def test_validate_real_tool(tmp_path: Path) -> None:
    """`nac validate` runs the real `uvx nac-validate` against the fixture
    data/schema and exits 0."""
    cfg_path = _make_config(tmp_path)

    runner = CliRunner()
    result = runner.invoke(app, ["--config", str(cfg_path), "validate"])

    assert result.exit_code == 0, (
        f"nac validate failed (exit={result.exit_code}):\n{result.output}"
    )


@pytest.mark.integration
def test_test_real_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`nac test` runs the real `uvx nac-test` against the fixture
    data/templates and exits 0."""
    if sys.platform == "darwin" and sys.version_info < (3, 12):
        # nac-test refuses to run on macOS with Python < 3.12, and uvx would
        # otherwise pick up the interpreter running this test.
        monkeypatch.setenv("UV_PYTHON", "3.12")

    cfg_path = _make_config(tmp_path)

    runner = CliRunner()
    result = runner.invoke(app, ["--config", str(cfg_path), "test"])

    assert result.exit_code == 0, (
        f"nac test failed (exit={result.exit_code}):\n{result.output}"
    )
