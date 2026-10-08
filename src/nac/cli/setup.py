# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""`nac setup` -- verify prerequisites and report resolved tool versions."""

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal

import typer

from nac import bootstrap, runner, terraform, tools
from nac.exceptions import BootstrapError, EngineNotFoundError, NoEngineAvailableError
from nac.manifest import MANIFEST_FILE
from nac.output import apply_no_color_env, echo_summary, format_command
from nac.tools import ToolSource

from .main import app, fail, get_config, get_no_color
from .options import Prewarm, Yes
from .versions import emit_warnings, get_manifest, tool_warnings

logger = logging.getLogger(__name__)

UV_NOT_FOUND = (
    "`uv` not found on PATH -- install it: "
    "https://docs.astral.sh/uv/getting-started/installation/"
)
TENV_NOT_FOUND = (
    "`tenv` not found on PATH -- required because `tools.terraform.version` "
    "is set. Install tenv: https://github.com/tofuutils/tenv"
)
MANUAL_INSTALL_MESSAGE = (
    "Neither Terraform nor OpenTofu is installed. Install Terraform or "
    "OpenTofu: https://developer.hashicorp.com/terraform/install or "
    "https://opentofu.org/docs/intro/install/ -- or set "
    "`tools.terraform.version` to have `nac` manage it via `tenv`."
)


def _is_interactive() -> bool:
    return bool(sys.stdin.isatty())


def _confirm_bootstrap(yes: bool) -> bool:
    if yes:
        return True
    if not _is_interactive():
        return False
    return typer.confirm(
        "Neither Terraform nor OpenTofu is installed. Install OpenTofu now?",
        default=True,
    )


def _binary_version(binary: str, env: dict[str, str]) -> str:
    argv = [binary, "version"]
    logger.debug("Running %s", format_command(argv))
    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    for line in (result.stdout or result.stderr or "").splitlines():
        if line.strip():
            return line.strip()
    return "unknown"


def _is_cached_binary(binary: str) -> bool:
    """True if `binary` lives under nac's bootstrap cache dir rather than PATH."""
    try:
        Path(binary).resolve().relative_to(bootstrap.cache_dir().resolve())
    except ValueError:
        return False
    return True


@app.command()
def setup(ctx: typer.Context, yes: Yes = False, prewarm: Prewarm = False) -> None:
    """Verify prerequisites and report resolved tool versions."""
    cfg = get_config(ctx)
    no_color = get_no_color(ctx)

    if shutil.which("uv") is None:
        fail(UV_NOT_FOUND)
    lines: list[str] = ["uv: found"]

    if cfg.tools.terraform.version is not None and shutil.which("tenv") is None:
        fail(TENV_NOT_FOUND)

    try:
        engine, binary = terraform.resolve_engine_binary(cfg.tools.terraform)
        if cfg.tools.terraform.engine is not None:
            detection = "explicit"
        elif _is_cached_binary(binary):
            detection = "bootstrap-installed"
        else:
            detection = "auto-detected"
    except EngineNotFoundError as exc:
        fail(str(exc))
    except NoEngineAvailableError:
        if not _confirm_bootstrap(yes):
            fail(MANUAL_INSTALL_MESSAGE)
        try:
            binary_path = bootstrap.install(confirmed=True)
        except BootstrapError as exc:
            fail(str(exc))
        engine, binary, detection = "tofu", str(binary_path), "bootstrap-installed"

    env = terraform.build_engine_env(engine, cfg.tools.terraform.version)
    lines.append(f"{engine}: {_binary_version(binary, env)} ({detection})")

    manifest = get_manifest(ctx, cfg)
    if manifest is not None:
        lines.append(f"tested versions: {manifest.module} ({MANIFEST_FILE})")

    missing_env = [name for name in cfg.env.required if name not in os.environ]
    if missing_env:
        fail("Missing required environment variable(s): " + ", ".join(missing_env))
    if cfg.env.required:
        lines.append("env.required: all present (" + ", ".join(cfg.env.required) + ")")

    def _tool_summary_line(
        name: Literal["nac-validate", "nac-test"], explicit: str | None
    ) -> tuple[str, ToolSource, str | None]:
        constraint = tools.tool_constraint(name, explicit, manifest)
        source = tools.resolve_tool_source(name, constraint)
        if source.mode == "local":
            return f"{name}: v{source.version or 'unknown'} (local)", source, constraint
        pin = constraint or "latest/unpinned"
        if explicit is None and constraint is not None and manifest is not None:
            pin += f", latest compatible with {manifest.module}"
        suffix = (
            f" -- local v{source.version} does not satisfy" if source.version else ""
        )
        return f"{name}: {pin} (uvx{suffix})", source, constraint

    validate_line, validate_source, validate_constraint = _tool_summary_line(
        "nac-validate", cfg.tools.nac_validate
    )
    test_line, test_source, test_constraint = _tool_summary_line(
        "nac-test", cfg.tools.nac_test
    )
    lines.append(validate_line)
    lines.append(test_line)
    warnings = [
        *tool_warnings(manifest, "nac-validate", cfg.tools.nac_validate),
        *tool_warnings(manifest, "nac-test", cfg.tools.nac_test),
    ]

    if prewarm:
        base_env = apply_no_color_env(no_color)
        if validate_source.mode != "local":
            argv = tools.build_prewarm_argv("nac-validate", validate_constraint)
            code = runner.run_streaming(
                argv, cwd=cfg.working_dir, env=base_env, no_color=no_color
            )
            if code != 0:
                raise typer.Exit(code=code)
        if test_source.mode != "local":
            argv = tools.build_prewarm_argv("nac-test", test_constraint)
            code = runner.run_streaming(
                argv, cwd=cfg.working_dir, env=base_env, no_color=no_color
            )
            if code != 0:
                raise typer.Exit(code=code)

    echo_summary("Setup Summary", lines, no_color=no_color)
    emit_warnings(warnings, no_color=no_color)
