# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""Unit tests for `nac setup` (SPEC.md FR-2 verification matrix, T18)."""

from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nac.cli.main import app
from nac.cli.setup import MANUAL_INSTALL_MESSAGE, TENV_NOT_FOUND

cli = CliRunner()


def _write_config(tmp_path: Path, content: str) -> Path:
    """Write `content` to a nac.yaml under tmp_path and return its path."""
    path = tmp_path / "nac.yaml"
    path.write_text(content)
    return path


def _which(mapping: dict[str, str | None]) -> Callable[[str], str | None]:
    """Build a `shutil.which` side_effect from a {binary: path-or-None} map.

    `shutil` is a single shared module object, so patching `shutil.which`
    once (rather than separately for `nac.cli.setup` and `nac.terraform`)
    is sufficient -- both modules call the same attribute at run time.
    """
    return lambda name: mapping.get(name)


@pytest.fixture(autouse=True)
def _stub_binary_version(mocker):
    """Stub the `subprocess.run` call inside `setup._binary_version()`.

    Every test gets a fake `terraform/tofu version` output so no real
    engine binary needs to exist on PATH.
    """
    result = mocker.Mock()
    result.stdout = "v1.0.0\n"
    result.stderr = ""
    return mocker.patch("nac.cli.setup.subprocess.run", return_value=result)


@pytest.mark.unit
def test_missing_required_env_var_fails_without_leaking_values(
    tmp_path, mocker, monkeypatch
):
    """(a) missing required env var -> non-zero exit, no leaked values."""
    monkeypatch.setenv("SOME_OTHER_VAR", "supersecret123")
    monkeypatch.delenv("SOME_VAR", raising=False)
    config_path = _write_config(
        tmp_path,
        "env:\n  required:\n    - SOME_VAR\n",
    )
    mocker.patch(
        "shutil.which",
        side_effect=_which({"uv": "/usr/bin/uv", "tofu": "/usr/bin/tofu"}),
    )

    result = cli.invoke(app, ["--config", str(config_path), "setup"])

    assert result.exit_code != 0
    assert "Missing required environment variable(s): SOME_VAR" in result.output
    assert "supersecret123" not in result.output


@pytest.mark.unit
def test_no_version_no_tenv_still_succeeds_with_resolved_engine(tmp_path, mocker):
    """(b) no tools.terraform.version, no tenv -> still succeeds if engine resolves."""
    config_path = _write_config(
        tmp_path,
        "tools:\n  terraform:\n    engine: terraform\n",
    )
    mocker.patch(
        "shutil.which",
        side_effect=_which(
            {"uv": "/usr/bin/uv", "tenv": None, "terraform": "/usr/bin/terraform"}
        ),
    )

    result = cli.invoke(app, ["--config", str(config_path), "setup"])

    assert result.exit_code == 0
    assert "terraform: v1.0.0 (explicit)" in result.output


@pytest.mark.unit
def test_version_set_no_tenv_fails(tmp_path, mocker):
    """(c) tools.terraform.version set, no tenv -> fails pointing at tenv."""
    config_path = _write_config(
        tmp_path,
        'tools:\n  terraform:\n    version: "1.7.0"\n',
    )
    mocker.patch("shutil.which", side_effect=_which({"uv": "/usr/bin/uv"}))

    result = cli.invoke(app, ["--config", str(config_path), "setup"])

    assert result.exit_code != 0
    assert TENV_NOT_FOUND in result.output


@pytest.mark.unit
def test_no_engine_configured_terraform_only_resolves_terraform(tmp_path, mocker):
    """(d) no engine configured, only terraform on PATH -> resolves terraform."""
    config_path = _write_config(tmp_path, "")
    mocker.patch(
        "shutil.which",
        side_effect=_which(
            {"uv": "/usr/bin/uv", "tofu": None, "terraform": "/usr/bin/terraform"}
        ),
    )

    result = cli.invoke(app, ["--config", str(config_path), "setup"])

    assert result.exit_code == 0
    assert "terraform: v1.0.0 (auto-detected)" in result.output
    assert "tofu" not in result.output


@pytest.mark.unit
def test_no_engine_configured_both_present_prefers_tofu(tmp_path, mocker):
    """(e) no engine configured, both present -> resolves tofu (default preference)."""
    config_path = _write_config(tmp_path, "")
    mocker.patch(
        "shutil.which",
        side_effect=_which(
            {
                "uv": "/usr/bin/uv",
                "tofu": "/usr/bin/tofu",
                "terraform": "/usr/bin/terraform",
            }
        ),
    )

    result = cli.invoke(app, ["--config", str(config_path), "setup"])

    assert result.exit_code == 0
    assert "tofu: v1.0.0 (auto-detected)" in result.output


@pytest.mark.unit
def test_no_engine_neither_present_noninteractive_no_yes_fails(tmp_path, mocker):
    """(f) neither engine present, non-interactive, no --yes -> fails, no bootstrap."""
    config_path = _write_config(tmp_path, "")
    mocker.patch(
        "shutil.which",
        side_effect=_which({"uv": "/usr/bin/uv", "tofu": None, "terraform": None}),
    )
    mocker.patch("nac.cli.setup._is_interactive", return_value=False)
    install_mock = mocker.patch("nac.cli.setup.bootstrap.install")

    result = cli.invoke(app, ["--config", str(config_path), "setup"])

    assert result.exit_code != 0
    assert MANUAL_INSTALL_MESSAGE in result.output
    install_mock.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize("flag", ["--yes", "--install"])
def test_yes_or_install_flag_bypasses_prompt_and_bootstraps(tmp_path, mocker, flag):
    """`--yes`/`--install` skip the TTY/confirm check and call bootstrap.install."""
    config_path = _write_config(tmp_path, "")
    mocker.patch(
        "shutil.which",
        side_effect=_which({"uv": "/usr/bin/uv", "tofu": None, "terraform": None}),
    )
    is_interactive_mock = mocker.patch("nac.cli.setup._is_interactive")
    confirm_mock = mocker.patch("nac.cli.setup.typer.confirm")
    install_mock = mocker.patch(
        "nac.cli.setup.bootstrap.install", return_value=Path("/fake/cache/tofu")
    )

    result = cli.invoke(app, ["--config", str(config_path), "setup", flag])

    assert result.exit_code == 0
    install_mock.assert_called_once_with(confirmed=True)
    is_interactive_mock.assert_not_called()
    confirm_mock.assert_not_called()
    assert "tofu: v1.0.0 (bootstrap-installed)" in result.output


@pytest.mark.unit
def test_interactive_decline_fails_without_bootstrapping(tmp_path, mocker):
    """Interactive prompt declined -> fails, bootstrap.install never called."""
    config_path = _write_config(tmp_path, "")
    mocker.patch(
        "shutil.which",
        side_effect=_which({"uv": "/usr/bin/uv", "tofu": None, "terraform": None}),
    )
    mocker.patch("nac.cli.setup._is_interactive", return_value=True)
    mocker.patch("nac.cli.setup.typer.confirm", return_value=False)
    install_mock = mocker.patch("nac.cli.setup.bootstrap.install")

    result = cli.invoke(app, ["--config", str(config_path), "setup"])

    assert result.exit_code != 0
    assert MANUAL_INSTALL_MESSAGE in result.output
    install_mock.assert_not_called()


@pytest.mark.unit
def test_neither_on_path_but_cached_reuses_cache_without_prompting(tmp_path, mocker):
    """FR-12: a `tofu` cached by a prior `nac setup` run is reused silently on
    a later `nac setup` run -- reported as bootstrap-installed, not
    auto-detected, and `bootstrap.install` is never invoked again."""
    config_path = _write_config(tmp_path, "")
    cache_root = tmp_path / "cache"
    cached_binary = cache_root / "bin" / "tofu" / "1.9.5" / "tofu"
    cached_binary.parent.mkdir(parents=True)
    cached_binary.write_text("fake")
    mocker.patch("nac.cli.setup.bootstrap.cache_dir", return_value=cache_root)
    mocker.patch(
        "nac.terraform.bootstrap.find_cached_binary", return_value=cached_binary
    )
    mocker.patch(
        "shutil.which",
        side_effect=_which({"uv": "/usr/bin/uv", "tofu": None, "terraform": None}),
    )
    install_mock = mocker.patch("nac.cli.setup.bootstrap.install")

    result = cli.invoke(app, ["--config", str(config_path), "setup"])

    assert result.exit_code == 0
    assert "tofu: v1.0.0 (bootstrap-installed)" in result.output
    install_mock.assert_not_called()


@pytest.mark.unit
def test_prewarm_runs_both_prewarm_commands(tmp_path, mocker):
    """`--prewarm` streams both the nac-validate and nac-test prewarm argvs."""
    config_path = _write_config(tmp_path, "")
    mocker.patch(
        "shutil.which",
        side_effect=_which({"uv": "/usr/bin/uv", "tofu": "/usr/bin/tofu"}),
    )
    run_streaming_mock = mocker.patch(
        "nac.cli.setup.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "setup", "--prewarm"])

    assert result.exit_code == 0
    assert run_streaming_mock.call_count == 2


@pytest.mark.unit
def test_prewarm_aborts_after_first_failure(tmp_path, mocker):
    """A failing first prewarm call aborts before the second and exits non-zero."""
    config_path = _write_config(tmp_path, "")
    mocker.patch(
        "shutil.which",
        side_effect=_which({"uv": "/usr/bin/uv", "tofu": "/usr/bin/tofu"}),
    )
    run_streaming_mock = mocker.patch(
        "nac.cli.setup.runner.run_streaming", return_value=1
    )

    result = cli.invoke(app, ["--config", str(config_path), "setup", "--prewarm"])

    assert result.exit_code != 0
    assert run_streaming_mock.call_count == 1


@pytest.mark.unit
def test_local_nac_validate_reported_when_it_satisfies_constraint(tmp_path, mocker):
    """A local nac-validate satisfying the pinned constraint is reported as
    "(local)" instead of being routed through uvx."""
    config_path = _write_config(
        tmp_path,
        'tools:\n  nac_validate: ">=0.9,<1.0"\n',
    )
    mocker.patch(
        "shutil.which",
        side_effect=_which(
            {
                "uv": "/usr/bin/uv",
                "tofu": "/usr/bin/tofu",
                "nac-validate": "/usr/bin/nac-validate",
            }
        ),
    )
    mocker.patch("nac.tools._local_tool_version", return_value="0.9.5")

    result = cli.invoke(app, ["--config", str(config_path), "setup"])

    assert result.exit_code == 0
    assert "nac-validate: v0.9.5 (local)" in result.output


@pytest.mark.unit
def test_local_nac_test_mismatch_falls_back_to_uvx_with_note(tmp_path, mocker):
    """A local nac-test that doesn't satisfy the pinned constraint falls back
    to uvx, and the summary explains why."""
    config_path = _write_config(
        tmp_path,
        'tools:\n  nac_test: ">=0.9,<1.0"\n',
    )
    mocker.patch(
        "shutil.which",
        side_effect=_which(
            {
                "uv": "/usr/bin/uv",
                "tofu": "/usr/bin/tofu",
                "nac-test": "/usr/bin/nac-test",
            }
        ),
    )
    mocker.patch("nac.tools._local_tool_version", return_value="1.0.0")

    result = cli.invoke(app, ["--config", str(config_path), "setup"])

    assert result.exit_code == 0
    assert (
        "nac-test: >=0.9,<1.0 (uvx -- local v1.0.0 does not satisfy)" in result.output
    )


@pytest.mark.unit
def test_prewarm_skips_locally_satisfied_tool(tmp_path, mocker):
    """`--prewarm` only streams a prewarm command for the tool that's still
    resolved to uvx -- a locally-satisfied tool has nothing to warm."""
    config_path = _write_config(tmp_path, "")
    mocker.patch(
        "shutil.which",
        side_effect=_which(
            {
                "uv": "/usr/bin/uv",
                "tofu": "/usr/bin/tofu",
                "nac-validate": "/usr/bin/nac-validate",
            }
        ),
    )
    mocker.patch("nac.tools._local_tool_version", return_value="1.2.3")
    run_streaming_mock = mocker.patch(
        "nac.cli.setup.runner.run_streaming", return_value=0
    )

    result = cli.invoke(app, ["--config", str(config_path), "setup", "--prewarm"])

    assert result.exit_code == 0
    assert "nac-validate: v1.2.3 (local)" in result.output
    run_streaming_mock.assert_called_once()
    (argv,), _kwargs = run_streaming_mock.call_args
    assert argv[0:5] == ["uv", "tool", "install", "--from", "nac-test"]
