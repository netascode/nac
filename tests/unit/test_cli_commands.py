# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""Unit tests for the CLI orchestration logic in init/validate/plan/apply/test.

These cover the wiring each subcommand does around `resolve_engine_or_exit`,
`runner.run_streaming`, and `nac.terraform`'s argv builders -- previously
only exercised indirectly by integration tests that need a real
terraform/tofu binary.
"""

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nac.cli.main import app
from nac.terraform import DEFAULT_PLAN_FILE

cli = CliRunner()


def _write_config(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "nac.yaml"
    path.write_text(content)
    return path


def _which(mapping: dict[str, str | None]) -> Callable[[str], str | None]:
    return lambda name: mapping.get(name)


@pytest.fixture
def _tofu_on_path(mocker):
    """Make `tofu` resolve as the engine everywhere via a shared shutil.which."""
    mocker.patch(
        "shutil.which",
        side_effect=_which({"tofu": "/usr/bin/tofu", "terraform": None}),
    )


# ---------------------------------------------------------------------------
# nac init
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_init_streams_init_argv_and_propagates_exit_code(
    tmp_path, mocker, _tofu_on_path
):
    config_path = _write_config(tmp_path, "")
    run_streaming_mock = mocker.patch(
        "nac.cli.init.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "init"])

    assert result.exit_code == 0
    argv, kwargs = run_streaming_mock.call_args
    assert argv[0] == ["/usr/bin/tofu", "init"]
    assert kwargs["cwd"] == tmp_path
    assert kwargs.get("log_path") is None


@pytest.mark.unit
def test_init_with_artifacts_writes_init_txt(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(tmp_path, "")
    run_streaming_mock = mocker.patch(
        "nac.cli.init.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "init", "--artifacts"])

    assert result.exit_code == 0
    assert run_streaming_mock.call_args.kwargs["log_path"] == tmp_path / "init.txt"


@pytest.mark.unit
def test_init_honors_global_no_color_flag(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(tmp_path, "")
    run_streaming_mock = mocker.patch(
        "nac.cli.init.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--no-color", "--config", str(config_path), "init"])

    assert result.exit_code == 0
    argv = run_streaming_mock.call_args_list[0].args[0]
    assert argv == ["/usr/bin/tofu", "init", "-no-color"]


@pytest.mark.unit
def test_init_propagates_nonzero_exit_code(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(tmp_path, "")
    mocker.patch("nac.cli.init.runner.run_streaming", return_value=2)

    result = cli.invoke(app, ["--config", str(config_path), "init"])

    assert result.exit_code == 2


@pytest.mark.unit
def test_init_fails_cleanly_when_no_engine_available(tmp_path, mocker):
    config_path = _write_config(tmp_path, "")
    mocker.patch("shutil.which", return_value=None)
    run_streaming_mock = mocker.patch("nac.cli.init.runner.run_streaming")

    result = cli.invoke(app, ["--config", str(config_path), "init"])

    assert result.exit_code != 0
    run_streaming_mock.assert_not_called()


# ---------------------------------------------------------------------------
# nac validate
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_validate_without_render_target_skips_render_step(tmp_path, mocker):
    config_path = _write_config(tmp_path, "")
    mocker.patch("shutil.which", return_value=None)
    run_streaming_mock = mocker.patch(
        "nac.cli.validate.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "validate"])

    assert result.exit_code == 0
    assert run_streaming_mock.call_count == 1
    argv = run_streaming_mock.call_args_list[0].args[0]
    assert argv[0] == "uvx"
    assert "nac-validate" in argv


@pytest.mark.unit
def test_validate_with_render_target_runs_render_then_validate(
    tmp_path, mocker, _tofu_on_path
):
    config_path = _write_config(
        tmp_path,
        "render:\n  target: module.example\n  output: rendered/\n",
    )
    run_streaming_mock = mocker.patch(
        "nac.cli.validate.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "validate"])

    assert result.exit_code == 0
    assert run_streaming_mock.call_count == 2
    render_argv = run_streaming_mock.call_args_list[0].args[0]
    validate_argv = run_streaming_mock.call_args_list[1].args[0]
    assert render_argv == [
        "/usr/bin/tofu",
        "apply",
        "-target=module.example",
        "-auto-approve",
    ]
    assert run_streaming_mock.call_args_list[0].kwargs.get("quiet") is True
    assert "rendered/" in validate_argv
    assert "Render Summary" in result.output
    assert "✓ Render: OK (module.example)" in result.output
    assert "─" * 80 in result.output


@pytest.mark.unit
@pytest.mark.parametrize("verbosity", ["INFO", "DEBUG"])
def test_validate_render_step_streams_live_at_info_verbosity_or_above(
    tmp_path, mocker, _tofu_on_path, verbosity
):
    config_path = _write_config(
        tmp_path,
        "render:\n  target: module.example\n  output: rendered/\n",
    )
    run_streaming_mock = mocker.patch(
        "nac.cli.validate.runner.run_streaming", return_value=0
    )

    result = cli.invoke(
        app, ["--verbosity", verbosity, "--config", str(config_path), "validate"]
    )

    assert result.exit_code == 0
    assert run_streaming_mock.call_args_list[0].kwargs.get("quiet") is False
    assert "Render Summary" not in result.output


@pytest.mark.unit
def test_validate_honors_global_no_color_flag(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(
        tmp_path,
        "render:\n  target: module.example\n  output: rendered/\n",
    )
    run_streaming_mock = mocker.patch(
        "nac.cli.validate.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--no-color", "--config", str(config_path), "validate"])

    assert result.exit_code == 0
    render_argv = run_streaming_mock.call_args_list[0].args[0]
    assert render_argv == [
        "/usr/bin/tofu",
        "apply",
        "-target=module.example",
        "-auto-approve",
        "-no-color",
    ]
    validate_env = run_streaming_mock.call_args_list[1].kwargs["env"]
    assert validate_env["NO_COLOR"] == "1"
    assert "Render: OK (module.example)" in result.output


@pytest.mark.unit
def test_validate_aborts_when_render_step_fails(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(
        tmp_path,
        "render:\n  target: module.example\n  output: rendered/\n",
    )
    run_streaming_mock = mocker.patch(
        "nac.cli.validate.runner.run_streaming", return_value=1
    )

    result = cli.invoke(app, ["--config", str(config_path), "validate"])

    assert result.exit_code == 1
    assert run_streaming_mock.call_count == 1


@pytest.mark.unit
def test_validate_without_artifacts_passes_no_log_path(tmp_path, mocker):
    config_path = _write_config(tmp_path, "")
    run_streaming_mock = mocker.patch(
        "nac.cli.validate.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "validate"])

    assert result.exit_code == 0
    assert run_streaming_mock.call_args.kwargs.get("log_path") is None


@pytest.mark.unit
def test_validate_with_artifacts_without_render_writes_validate_txt(tmp_path, mocker):
    config_path = _write_config(tmp_path, "")
    run_streaming_mock = mocker.patch(
        "nac.cli.validate.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "validate", "--artifacts"])

    assert result.exit_code == 0
    assert run_streaming_mock.call_count == 1
    call = run_streaming_mock.call_args_list[0]
    assert call.kwargs["log_path"] == tmp_path / "validate.txt"
    assert not call.kwargs.get("append")


@pytest.mark.unit
def test_validate_with_artifacts_and_render_appends_second_call(
    tmp_path, mocker, _tofu_on_path
):
    config_path = _write_config(
        tmp_path,
        "render:\n  target: module.example\n  output: rendered/\n",
    )
    run_streaming_mock = mocker.patch(
        "nac.cli.validate.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "validate", "--artifacts"])

    assert result.exit_code == 0
    assert run_streaming_mock.call_count == 2
    render_call, validate_call = run_streaming_mock.call_args_list
    assert render_call.kwargs["log_path"] == tmp_path / "validate.txt"
    assert not render_call.kwargs.get("append")
    assert validate_call.kwargs["log_path"] == tmp_path / "validate.txt"
    assert validate_call.kwargs["append"] is True


@pytest.mark.unit
def test_validate_with_artifacts_render_failure_only_logs_render_call(
    tmp_path, mocker, _tofu_on_path
):
    config_path = _write_config(
        tmp_path,
        "render:\n  target: module.example\n  output: rendered/\n",
    )
    run_streaming_mock = mocker.patch(
        "nac.cli.validate.runner.run_streaming", return_value=1
    )

    result = cli.invoke(app, ["--config", str(config_path), "validate", "--artifacts"])

    assert result.exit_code == 1
    assert run_streaming_mock.call_count == 1
    assert run_streaming_mock.call_args.kwargs["log_path"] == tmp_path / "validate.txt"


# ---------------------------------------------------------------------------
# nac plan
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_plan_without_artifacts_runs_plan_only(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(tmp_path, "")
    run_streaming_mock = mocker.patch(
        "nac.cli.plan.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "plan"])

    assert result.exit_code == 0
    assert run_streaming_mock.call_count == 1
    argv = run_streaming_mock.call_args_list[0].args[0]
    assert argv == ["/usr/bin/tofu", "plan", f"-out={DEFAULT_PLAN_FILE}"]


@pytest.mark.unit
def test_plan_with_artifacts_runs_plan_then_both_show_commands(
    tmp_path, mocker, _tofu_on_path
):
    config_path = _write_config(tmp_path, "")
    run_streaming_mock = mocker.patch(
        "nac.cli.plan.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "plan", "--artifacts"])

    assert result.exit_code == 0
    assert run_streaming_mock.call_count == 3
    text_call, json_call = (
        run_streaming_mock.call_args_list[1],
        run_streaming_mock.call_args_list[2],
    )
    assert text_call.kwargs["log_path"] == tmp_path / "plan.txt"
    assert json_call.kwargs["log_path"] == tmp_path / "plan.json"
    assert "-json" in json_call.args[0]


@pytest.mark.unit
def test_plan_aborts_before_artifacts_when_plan_step_fails(
    tmp_path, mocker, _tofu_on_path
):
    config_path = _write_config(tmp_path, "")
    run_streaming_mock = mocker.patch(
        "nac.cli.plan.runner.run_streaming", return_value=1
    )

    result = cli.invoke(app, ["--config", str(config_path), "plan", "--artifacts"])

    assert result.exit_code == 1
    assert run_streaming_mock.call_count == 1


@pytest.mark.unit
def test_plan_aborts_before_json_show_when_text_show_fails(
    tmp_path, mocker, _tofu_on_path
):
    config_path = _write_config(tmp_path, "")
    run_streaming_mock = mocker.patch(
        "nac.cli.plan.runner.run_streaming", side_effect=[0, 1]
    )

    result = cli.invoke(app, ["--config", str(config_path), "plan", "--artifacts"])

    assert result.exit_code == 1
    assert run_streaming_mock.call_count == 2


# ---------------------------------------------------------------------------
# nac apply
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_apply_uses_saved_plan_file_when_present(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(tmp_path, "")
    (tmp_path / DEFAULT_PLAN_FILE).write_text("fake plan")
    run_streaming_mock = mocker.patch(
        "nac.cli.apply.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "apply"])

    assert result.exit_code == 0
    argv = run_streaming_mock.call_args_list[0].args[0]
    assert argv == ["/usr/bin/tofu", "apply", DEFAULT_PLAN_FILE]
    assert run_streaming_mock.call_args_list[0].kwargs.get("log_path") is None


@pytest.mark.unit
def test_apply_with_artifacts_writes_apply_txt(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(tmp_path, "")
    run_streaming_mock = mocker.patch(
        "nac.cli.apply.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "apply", "--artifacts"])

    assert result.exit_code == 0
    assert run_streaming_mock.call_args.kwargs["log_path"] == tmp_path / "apply.txt"


@pytest.mark.unit
def test_apply_honors_global_no_color_flag(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(tmp_path, "")
    (tmp_path / DEFAULT_PLAN_FILE).write_text("fake plan")
    run_streaming_mock = mocker.patch(
        "nac.cli.apply.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--no-color", "--config", str(config_path), "apply"])

    assert result.exit_code == 0
    argv = run_streaming_mock.call_args_list[0].args[0]
    assert argv == ["/usr/bin/tofu", "apply", "-no-color", DEFAULT_PLAN_FILE]


@pytest.mark.unit
def test_apply_without_saved_plan_runs_interactively(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(tmp_path, "")
    run_streaming_mock = mocker.patch(
        "nac.cli.apply.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "apply"])

    assert result.exit_code == 0
    argv = run_streaming_mock.call_args_list[0].args[0]
    assert argv == ["/usr/bin/tofu", "apply"]


@pytest.mark.unit
def test_apply_without_saved_plan_honors_auto_approve(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(tmp_path, "")
    run_streaming_mock = mocker.patch(
        "nac.cli.apply.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "apply", "--auto-approve"])

    assert result.exit_code == 0
    argv = run_streaming_mock.call_args_list[0].args[0]
    assert argv == ["/usr/bin/tofu", "apply", "-auto-approve"]


@pytest.mark.unit
def test_apply_ignores_auto_approve_when_saved_plan_present(
    tmp_path, mocker, _tofu_on_path
):
    config_path = _write_config(tmp_path, "")
    (tmp_path / DEFAULT_PLAN_FILE).write_text("fake plan")
    run_streaming_mock = mocker.patch(
        "nac.cli.apply.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "apply", "--auto-approve"])

    assert result.exit_code == 0
    argv = run_streaming_mock.call_args_list[0].args[0]
    assert argv == ["/usr/bin/tofu", "apply", DEFAULT_PLAN_FILE]


@pytest.mark.unit
def test_apply_deletes_saved_plan_file_on_success(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(tmp_path, "")
    plan_path = tmp_path / DEFAULT_PLAN_FILE
    plan_path.write_text("fake plan")
    mocker.patch("nac.cli.apply.runner.run_streaming", return_value=0)

    result = cli.invoke(app, ["--config", str(config_path), "apply"])

    assert result.exit_code == 0
    assert not plan_path.exists()


@pytest.mark.unit
def test_apply_keeps_saved_plan_file_on_failure(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(tmp_path, "")
    plan_path = tmp_path / DEFAULT_PLAN_FILE
    plan_path.write_text("fake plan")
    mocker.patch("nac.cli.apply.runner.run_streaming", return_value=1)

    result = cli.invoke(app, ["--config", str(config_path), "apply"])

    assert result.exit_code == 1
    assert plan_path.exists()


# ---------------------------------------------------------------------------
# nac destroy
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_destroy_streams_destroy_argv_and_propagates_exit_code(
    tmp_path, mocker, _tofu_on_path
):
    config_path = _write_config(tmp_path, "")
    run_streaming_mock = mocker.patch(
        "nac.cli.destroy.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "destroy"])

    assert result.exit_code == 0
    argv = run_streaming_mock.call_args_list[0].args[0]
    assert argv == ["/usr/bin/tofu", "destroy"]
    assert run_streaming_mock.call_args_list[0].kwargs.get("log_path") is None


@pytest.mark.unit
def test_destroy_with_artifacts_writes_destroy_txt(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(tmp_path, "")
    run_streaming_mock = mocker.patch(
        "nac.cli.destroy.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "destroy", "--artifacts"])

    assert result.exit_code == 0
    assert run_streaming_mock.call_args.kwargs["log_path"] == tmp_path / "destroy.txt"


@pytest.mark.unit
def test_destroy_honors_auto_approve(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(tmp_path, "")
    run_streaming_mock = mocker.patch(
        "nac.cli.destroy.runner.run_streaming", return_value=0
    )

    result = cli.invoke(
        app, ["--config", str(config_path), "destroy", "--auto-approve"]
    )

    assert result.exit_code == 0
    argv = run_streaming_mock.call_args_list[0].args[0]
    assert argv == ["/usr/bin/tofu", "destroy", "-auto-approve"]


@pytest.mark.unit
def test_destroy_honors_global_no_color_flag(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(tmp_path, "")
    run_streaming_mock = mocker.patch(
        "nac.cli.destroy.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--no-color", "--config", str(config_path), "destroy"])

    assert result.exit_code == 0
    argv = run_streaming_mock.call_args_list[0].args[0]
    assert argv == ["/usr/bin/tofu", "destroy", "-no-color"]


@pytest.mark.unit
def test_destroy_propagates_nonzero_exit_code(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(tmp_path, "")
    mocker.patch("nac.cli.destroy.runner.run_streaming", return_value=2)

    result = cli.invoke(app, ["--config", str(config_path), "destroy"])

    assert result.exit_code == 2


@pytest.mark.unit
def test_destroy_fails_cleanly_when_no_engine_available(tmp_path, mocker):
    config_path = _write_config(tmp_path, "")
    mocker.patch("shutil.which", return_value=None)
    run_streaming_mock = mocker.patch("nac.cli.destroy.runner.run_streaming")

    result = cli.invoke(app, ["--config", str(config_path), "destroy"])

    assert result.exit_code != 0
    run_streaming_mock.assert_not_called()


# ---------------------------------------------------------------------------
# nac test
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_test_streams_test_argv_and_propagates_exit_code(tmp_path, mocker):
    config_path = _write_config(tmp_path, "")
    mocker.patch("shutil.which", return_value=None)
    run_streaming_mock = mocker.patch(
        "nac.cli.test.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "test"])

    assert result.exit_code == 0
    argv = run_streaming_mock.call_args_list[0].args[0]
    assert argv[0] == "uvx"
    assert "nac-test" in argv
    assert run_streaming_mock.call_args_list[0].kwargs.get("log_path") is None


@pytest.mark.unit
def test_test_with_artifacts_writes_test_txt(tmp_path, mocker):
    config_path = _write_config(tmp_path, "")
    run_streaming_mock = mocker.patch(
        "nac.cli.test.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "test", "--artifacts"])

    assert result.exit_code == 0
    assert run_streaming_mock.call_args.kwargs["log_path"] == tmp_path / "test.txt"


@pytest.mark.unit
def test_test_propagates_nonzero_exit_code(tmp_path, mocker):
    config_path = _write_config(tmp_path, "")
    mocker.patch("nac.cli.test.runner.run_streaming", return_value=5)

    result = cli.invoke(app, ["--config", str(config_path), "test"])

    assert result.exit_code == 5


# ---------------------------------------------------------------------------
# passthrough args + --help delegation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_validate_extra_args_are_appended(tmp_path, mocker):
    config_path = _write_config(tmp_path, "validate:\n  rules:\n    - cfg-rule\n")
    run_streaming_mock = mocker.patch(
        "nac.cli.validate.runner.run_streaming", return_value=0
    )

    result = cli.invoke(
        app, ["--config", str(config_path), "validate", "-r", "extra-rule"]
    )

    assert result.exit_code == 0
    argv = run_streaming_mock.call_args_list[0].args[0]
    r_indices = [i for i, a in enumerate(argv) if a == "-r"]
    assert [argv[i + 1] for i in r_indices] == ["cfg-rule", "extra-rule"]


@pytest.mark.unit
def test_validate_help_shows_own_and_tool_help(tmp_path, mocker):
    config_path = _write_config(tmp_path, "")
    mocker.patch("shutil.which", return_value=None)
    run_mock = mocker.patch(
        "nac.cli.passthrough.subprocess.run",
        return_value=subprocess.CompletedProcess(
            [],
            0,
            stdout=(
                " Usage: nac-validate [OPTIONS] [PATHS]...\n\n A tool.\n\n"
                "╭─ Options ─╮\n│ --schema │\n╰───────────╯\n"
            ),
        ),
    )

    result = cli.invoke(app, ["--config", str(config_path), "validate", "--help"])

    assert result.exit_code == 0
    assert "validate [OPTIONS] [PASSTHROUGH-ARGS]..." in result.output
    assert "Passed through to nac-validate" in result.output
    assert "--schema" in result.output
    assert "A tool." not in result.output
    assert "Usage: nac-validate" not in result.output
    assert "[PATHS]" not in result.output
    argv = run_mock.call_args.args[0]
    assert argv[0] == "uvx"
    assert "nac-validate" in argv
    assert argv[-1] == "--help"


@pytest.mark.unit
def test_plan_help_drops_terraform_usage_and_description(
    tmp_path, mocker, _tofu_on_path
):
    config_path = _write_config(tmp_path, "")
    mocker.patch(
        "nac.cli.passthrough.subprocess.run",
        return_value=subprocess.CompletedProcess(
            [],
            0,
            stdout=(
                "Usage: tofu [global options] plan [options]\n\n"
                "  Generates a plan.\n\n"
                "Plan Customization Options:\n\n  -destroy  Destroy mode.\n"
            ),
        ),
    )

    result = cli.invoke(app, ["--config", str(config_path), "plan", "--help"])

    assert result.exit_code == 0
    assert "Usage: tofu" not in result.output
    assert "Generates a plan." not in result.output
    assert "Plan Customization Options:" in result.output
    assert "-destroy" in result.output


@pytest.mark.unit
def test_plan_help_rewrites_usage_line_when_no_options_heading(
    tmp_path, mocker, _tofu_on_path
):
    config_path = _write_config(tmp_path, "")
    mocker.patch(
        "nac.cli.passthrough.subprocess.run",
        return_value=subprocess.CompletedProcess(
            [], 0, stdout="Usage: tofu [global options] plan [options]\n"
        ),
    )

    result = cli.invoke(app, ["--config", str(config_path), "plan", "--help"])

    assert result.exit_code == 0
    assert "Usage: nac plan [options]" in result.output
    assert "Usage: tofu" not in result.output


@pytest.mark.unit
def test_test_extra_args_are_appended(tmp_path, mocker):
    config_path = _write_config(tmp_path, "")
    run_streaming_mock = mocker.patch(
        "nac.cli.test.runner.run_streaming", return_value=0
    )

    result = cli.invoke(
        app, ["--config", str(config_path), "test", "--tests", "sometest"]
    )

    assert result.exit_code == 0
    argv = run_streaming_mock.call_args_list[0].args[0]
    assert argv[-2:] == ["--tests", "sometest"]


@pytest.mark.unit
def test_test_help_shows_own_and_tool_help(tmp_path, mocker):
    config_path = _write_config(tmp_path, "")
    mocker.patch("shutil.which", return_value=None)
    run_mock = mocker.patch(
        "nac.cli.passthrough.subprocess.run",
        return_value=subprocess.CompletedProcess(
            [], 0, stdout=" Usage: nac-validate [OPTIONS]\n"
        ),
    )

    result = cli.invoke(app, ["--config", str(config_path), "test", "-h"])

    assert result.exit_code == 0
    assert "Usage:" in result.output
    argv = run_mock.call_args.args[0]
    assert argv[0] == "uvx"
    assert "nac-test" in argv
    assert argv[-1] == "--help"


@pytest.mark.unit
def test_init_extra_args_are_appended(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(tmp_path, "")
    run_streaming_mock = mocker.patch(
        "nac.cli.init.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "init", "-upgrade"])

    assert result.exit_code == 0
    argv = run_streaming_mock.call_args_list[0].args[0]
    assert argv == ["/usr/bin/tofu", "init", "-upgrade"]


@pytest.mark.unit
def test_init_help_shows_own_and_tool_help(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(tmp_path, "")
    run_mock = mocker.patch(
        "nac.cli.passthrough.subprocess.run",
        return_value=subprocess.CompletedProcess(
            [], 0, stdout=" Usage: nac-validate [OPTIONS]\n"
        ),
    )

    result = cli.invoke(app, ["--config", str(config_path), "init", "--help"])

    assert result.exit_code == 0
    assert "Usage:" in result.output
    argv = run_mock.call_args.args[0]
    assert argv == ["/usr/bin/tofu", "init", "--help"]


@pytest.mark.unit
def test_plan_extra_args_appended_only_to_plan_call(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(tmp_path, "")
    run_streaming_mock = mocker.patch(
        "nac.cli.plan.runner.run_streaming", return_value=0
    )

    result = cli.invoke(
        app, ["--config", str(config_path), "plan", "--artifacts", "-lock=false"]
    )

    assert result.exit_code == 0
    plan_argv = run_streaming_mock.call_args_list[0].args[0]
    text_argv = run_streaming_mock.call_args_list[1].args[0]
    assert plan_argv == [
        "/usr/bin/tofu",
        "plan",
        f"-out={DEFAULT_PLAN_FILE}",
        "-lock=false",
    ]
    assert "-lock=false" not in text_argv


@pytest.mark.unit
def test_plan_help_shows_own_and_tool_help(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(tmp_path, "")
    run_mock = mocker.patch(
        "nac.cli.passthrough.subprocess.run",
        return_value=subprocess.CompletedProcess(
            [], 0, stdout=" Usage: nac-validate [OPTIONS]\n"
        ),
    )

    result = cli.invoke(app, ["--config", str(config_path), "plan", "--help"])

    assert result.exit_code == 0
    assert "Usage:" in result.output
    argv = run_mock.call_args.args[0]
    assert argv == ["/usr/bin/tofu", "plan", "--help"]


@pytest.mark.unit
def test_apply_extra_args_are_appended(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(tmp_path, "")
    run_streaming_mock = mocker.patch(
        "nac.cli.apply.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "apply", "-lock=false"])

    assert result.exit_code == 0
    argv = run_streaming_mock.call_args_list[0].args[0]
    assert argv == ["/usr/bin/tofu", "apply", "-lock=false"]


@pytest.mark.unit
def test_apply_help_shows_own_and_tool_help(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(tmp_path, "")
    run_mock = mocker.patch(
        "nac.cli.passthrough.subprocess.run",
        return_value=subprocess.CompletedProcess(
            [], 0, stdout=" Usage: nac-validate [OPTIONS]\n"
        ),
    )

    result = cli.invoke(app, ["--config", str(config_path), "apply", "--help"])

    assert result.exit_code == 0
    assert "Usage:" in result.output
    argv = run_mock.call_args.args[0]
    assert argv == ["/usr/bin/tofu", "apply", "--help"]


@pytest.mark.unit
def test_destroy_extra_args_are_appended(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(tmp_path, "")
    run_streaming_mock = mocker.patch(
        "nac.cli.destroy.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "destroy", "-lock=false"])

    assert result.exit_code == 0
    argv = run_streaming_mock.call_args_list[0].args[0]
    assert argv == ["/usr/bin/tofu", "destroy", "-lock=false"]


@pytest.mark.unit
def test_destroy_help_shows_own_and_tool_help(tmp_path, mocker, _tofu_on_path):
    config_path = _write_config(tmp_path, "")
    run_mock = mocker.patch(
        "nac.cli.passthrough.subprocess.run",
        return_value=subprocess.CompletedProcess(
            [], 0, stdout=" Usage: nac-validate [OPTIONS]\n"
        ),
    )

    result = cli.invoke(app, ["--config", str(config_path), "destroy", "--help"])

    assert result.exit_code == 0
    assert "Usage:" in result.output
    argv = run_mock.call_args.args[0]
    assert argv == ["/usr/bin/tofu", "destroy", "--help"]
