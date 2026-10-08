# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""Unit tests for the advisory tested-versions checks in each subcommand."""

from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nac.cli.main import app

cli = CliRunner()


def _write_config(tmp_path: Path, content: str = "") -> Path:
    path = tmp_path / "nac.yaml"
    path.write_text(content)
    return path


def _which(mapping: dict[str, str | None]) -> Callable[[str], str | None]:
    return lambda name: mapping.get(name)


@pytest.fixture
def tofu_version(mocker):
    """Make `nac setup`'s `tofu version` probe report the given version."""

    def _set(version: str = "1.12.1"):
        return mocker.patch(
            "nac.cli.setup.subprocess.run",
            return_value=mocker.Mock(stdout=f"OpenTofu v{version}\n", stderr=""),
        )

    return _set


@pytest.fixture
def _tofu_on_path(mocker):
    mocker.patch(
        "shutil.which",
        side_effect=_which({"tofu": "/usr/bin/tofu", "uv": "/usr/bin/uv"}),
    )


# ---------------------------------------------------------------------------
# no manifest
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_no_manifest_no_warnings_and_unconstrained_tools(tmp_path, mocker):
    config_path = _write_config(tmp_path, "tools:\n  nac_validate: 1.2.0\n")
    mocker.patch("shutil.which", return_value=None)
    run_streaming_mock = mocker.patch(
        "nac.cli.validate.runner.run_streaming", return_value=1
    )

    result = cli.invoke(app, ["--config", str(config_path), "validate"])

    assert result.exit_code == 1
    assert "Warning" not in result.output
    assert "Note" not in result.output
    argv = run_streaming_mock.call_args.args[0]
    assert argv[:3] == ["uvx", "--from", "nac-validate==1.2.0"]


# ---------------------------------------------------------------------------
# nac validate / nac test
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_validate_defaults_to_latest_compatible_without_warning(
    tmp_path, mocker, write_module
):
    write_module(tmp_path)
    config_path = _write_config(tmp_path)
    mocker.patch("shutil.which", return_value=None)
    run_streaming_mock = mocker.patch(
        "nac.cli.validate.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "validate"])

    assert result.exit_code == 0
    assert "Warning" not in result.output
    argv = run_streaming_mock.call_args.args[0]
    assert argv[:4] == ["uvx", "--from", "nac-validate>=2.0.0,<3", "nac-validate"]


@pytest.mark.unit
def test_validate_warns_on_untested_pin_and_notes_failure(
    tmp_path, mocker, write_module
):
    write_module(tmp_path)
    config_path = _write_config(tmp_path, "tools:\n  nac_validate: 1.2.0\n")
    mocker.patch("shutil.which", return_value=None)
    mocker.patch("nac.cli.validate.runner.run_streaming", return_value=1)

    result = cli.invoke(app, ["--config", str(config_path), "validate"])

    assert result.exit_code == 1
    assert (
        "Warning: nac-validate 1.2.0 is outside the range tested with "
        "netascode/nac-nxos/nxos 0.3.0 (tested: 2.0.0, compatible: >=2.0.0,<3)"
    ) in result.output
    assert "Note: `nac validate` failed" in result.output


@pytest.mark.unit
def test_validate_warning_without_note_on_success(tmp_path, mocker, write_module):
    write_module(tmp_path)
    config_path = _write_config(tmp_path, "tools:\n  nac_validate: 1.2.0\n")
    mocker.patch("shutil.which", return_value=None)
    mocker.patch("nac.cli.validate.runner.run_streaming", return_value=0)

    result = cli.invoke(app, ["--config", str(config_path), "validate"])

    assert result.exit_code == 0
    assert "Warning: nac-validate 1.2.0" in result.output
    assert "Note" not in result.output


@pytest.mark.unit
def test_validate_range_pin_resolved_by_uvx_is_not_checked(
    tmp_path, mocker, write_module
):
    write_module(tmp_path)
    config_path = _write_config(tmp_path, 'tools:\n  nac_validate: ">=1.0"\n')
    mocker.patch("shutil.which", return_value=None)
    mocker.patch("nac.cli.validate.runner.run_streaming", return_value=0)

    result = cli.invoke(app, ["--config", str(config_path), "validate"])

    assert "Warning" not in result.output


@pytest.mark.unit
def test_validate_checks_local_install_version(tmp_path, mocker, write_module):
    write_module(tmp_path)
    config_path = _write_config(tmp_path, 'tools:\n  nac_validate: ">=1.0"\n')
    mocker.patch(
        "shutil.which",
        side_effect=_which({"nac-validate": "/usr/bin/nac-validate"}),
    )
    mocker.patch("nac.tools._local_tool_version", return_value="1.5.0")
    mocker.patch("nac.cli.validate.runner.run_streaming", return_value=0)

    result = cli.invoke(app, ["--config", str(config_path), "validate"])

    assert "Warning: nac-validate 1.5.0 is outside the range" in result.output


@pytest.mark.unit
def test_validate_artifacts_include_warnings(tmp_path, mocker, write_module):
    write_module(tmp_path)
    config_path = _write_config(tmp_path, "tools:\n  nac_validate: 1.2.0\n")
    mocker.patch("shutil.which", return_value=None)
    run_streaming_mock = mocker.patch(
        "nac.cli.validate.runner.run_streaming", return_value=1
    )

    cli.invoke(app, ["--config", str(config_path), "validate", "--artifacts"])

    assert run_streaming_mock.call_args.kwargs["append"] is True
    lines = (tmp_path / "validate.txt").read_text().splitlines()
    assert lines[0].startswith("Warning: nac-validate 1.2.0")
    assert lines[-1].startswith("Note: `nac validate` failed")


@pytest.mark.unit
def test_validate_with_render_artifacts_keep_warnings_first(
    tmp_path, mocker, write_module, _tofu_on_path
):
    """The warnings open validate.txt; the render step and nac-validate
    then both append to it."""
    write_module(tmp_path)
    config_path = _write_config(
        tmp_path,
        "render:\n  target: module.nxos.model\n  output: model.yaml\n"
        "tools:\n  nac_validate: 1.2.0\n",
    )
    run_streaming_mock = mocker.patch(
        "nac.cli.validate.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "validate", "--artifacts"])

    assert result.exit_code == 0
    render_call, validate_call = run_streaming_mock.call_args_list
    assert render_call.args[0][:2] == ["/usr/bin/tofu", "apply"]
    assert render_call.kwargs["append"] is True
    assert validate_call.kwargs["append"] is True
    assert (
        (tmp_path / "validate.txt")
        .read_text()
        .startswith("Warning: nac-validate 1.2.0")
    )


@pytest.mark.unit
def test_test_defaults_to_latest_compatible(tmp_path, mocker, write_module):
    write_module(tmp_path)
    config_path = _write_config(tmp_path)
    mocker.patch("shutil.which", return_value=None)
    run_streaming_mock = mocker.patch(
        "nac.cli.test.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "test"])

    assert result.exit_code == 0
    argv = run_streaming_mock.call_args.args[0]
    assert argv[:4] == ["uvx", "--from", "nac-test>=2.0.0,<3", "nac-test"]


@pytest.mark.unit
def test_test_warns_on_untested_pin_and_preserves_exit_code(
    tmp_path, mocker, write_module
):
    write_module(tmp_path)
    config_path = _write_config(tmp_path, "tools:\n  nac_test: 3.0.0\n")
    mocker.patch("shutil.which", return_value=None)
    mocker.patch("nac.cli.test.runner.run_streaming", return_value=4)

    result = cli.invoke(app, ["--config", str(config_path), "test"])

    assert result.exit_code == 4
    assert "Warning: nac-test 3.0.0 is outside the range" in result.output
    assert "Note: `nac test` failed" in result.output


# ---------------------------------------------------------------------------
# nac setup
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_setup_reports_manifest_and_latest_compatible(
    tmp_path, mocker, write_module, _tofu_on_path, tofu_version
):
    write_module(tmp_path)
    config_path = _write_config(tmp_path)
    tofu_version()

    result = cli.invoke(app, ["--config", str(config_path), "setup"])

    assert result.exit_code == 0
    assert (
        "tested versions: netascode/nac-nxos/nxos 0.3.0 (nac/manifest.yaml)"
        in result.output
    )
    assert (
        "nac-validate: >=2.0.0,<3, latest compatible with "
        "netascode/nac-nxos/nxos 0.3.0 (uvx)"
    ) in result.output
    assert "Warning" not in result.output


@pytest.mark.unit
def test_setup_warns_but_succeeds(
    tmp_path, mocker, write_module, _tofu_on_path, tofu_version
):
    write_module(tmp_path)
    config_path = _write_config(tmp_path, "tools:\n  nac_test: 1.0.0\n")
    tofu_version()

    result = cli.invoke(app, ["--config", str(config_path), "setup"])

    assert result.exit_code == 0
    assert result.output.count("Warning:") == 1
    assert "Warning: nac-test 1.0.0" in result.output
    assert "nac-test: 1.0.0 (uvx)" in result.output


@pytest.mark.unit
def test_setup_prewarms_latest_compatible(
    tmp_path, mocker, write_module, _tofu_on_path, tofu_version
):
    write_module(tmp_path)
    config_path = _write_config(tmp_path)
    tofu_version()
    run_streaming_mock = mocker.patch(
        "nac.cli.setup.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "setup", "--prewarm"])

    assert result.exit_code == 0
    argvs = [c.args[0] for c in run_streaming_mock.call_args_list]
    assert argvs == [
        ["uv", "tool", "install", "--from", "nac-validate>=2.0.0,<3", "nac-validate"],
        ["uv", "tool", "install", "--from", "nac-test>=2.0.0,<3", "nac-test"],
    ]
