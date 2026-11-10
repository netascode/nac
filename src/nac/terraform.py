# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

import os
import shutil
import subprocess
from collections.abc import Mapping

from nac import bootstrap
from nac.config import TerraformToolConfig
from nac.exceptions import EngineNotFoundError, NoEngineAvailableError

TOFU_VERSION_ENV = "TOFUENV_TOFU_VERSION"
TOFU_AUTO_INSTALL_ENV = "TOFUENV_AUTO_INSTALL"
TERRAFORM_VERSION_ENV = "TFENV_TERRAFORM_VERSION"
TERRAFORM_AUTO_INSTALL_ENV = "TFENV_AUTO_INSTALL"

# Disables auto-install of version-manager shims (tenv, tofuenv, tfenv) and
# Terraform's update check while probing whether a binary is usable.
PROBE_ENV = {
    "TENV_AUTO_INSTALL": "false",
    TOFU_AUTO_INSTALL_ENV: "false",
    TERRAFORM_AUTO_INSTALL_ENV: "false",
    "CHECKPOINT_DISABLE": "1",
}
PROBE_TIMEOUT_SECONDS = 30

DEFAULT_PLAN_FILE = "plan.tfplan"
DEFAULT_PLAN_TEXT_FILE = "plan.txt"
DEFAULT_PLAN_JSON_FILE = "plan.json"


def resolve_engine_binary(cfg: TerraformToolConfig) -> tuple[str, str]:
    """Resolve which terraform/tofu binary to use.

    Returns (engine_name, resolved_absolute_path). An explicit
    `cfg.engine` is a hard requirement — it never falls back to the
    other binary. When unset, `tofu` is tried before `terraform` (skipping
    a binary that fails to run, unless a version is pinned), then
    a previously bootstrap-installed `tofu` in the cache dir (FR-12),
    so a machine set up via `nac setup` keeps working on subsequent
    commands without re-prompting.
    """
    if cfg.engine is not None:
        path = shutil.which(cfg.engine)
        if path is None:
            raise EngineNotFoundError(
                f"`{cfg.engine}` not found on PATH — install it, or set "
                f"`tools.terraform.version` to have `nac` manage it via `tenv`."
            )
        return cfg.engine, path

    # Without a pinned version, a binary on PATH must also run: a
    # version-manager shim (e.g. tenv's) stays on PATH after its last version
    # is uninstalled and then fails on every call. With a pinned version the
    # shim is expected to install that version on first use, so it isn't
    # probed.
    unusable: list[str] = []
    for engine in ("tofu", "terraform"):
        path = shutil.which(engine)
        if path is None:
            continue
        if cfg.version is None and not _engine_usable(path):
            unusable.append(f"`{engine}` ({path})")
            continue
        return engine, path

    cached = bootstrap.find_cached_binary()
    if cached is not None:
        return "tofu", str(cached)

    message = "Neither `tofu` nor `terraform` was found on PATH."
    if unusable:
        message += (
            f" Found {' and '.join(unusable)}, but `version` failed; a version"
            " manager shim without an installed version?"
        )
    raise NoEngineAvailableError(message)


def _engine_usable(path: str) -> bool:
    """Whether `<path> version` succeeds, without installing anything."""
    try:
        result = subprocess.run(
            [path, "version"],
            env={**os.environ, **PROBE_ENV},
            capture_output=True,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def build_engine_env(
    engine: str,
    version: str | None,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build the subprocess environment for the resolved engine.

    Returns a new dict (never mutates base_env). Only when `version` is
    set does it add the matching tenv version-pin + auto-install vars.
    """
    env = dict(base_env if base_env is not None else os.environ)
    if version is not None:
        if engine == "tofu":
            env[TOFU_VERSION_ENV] = version
            env[TOFU_AUTO_INSTALL_ENV] = "true"
        elif engine == "terraform":
            env[TERRAFORM_VERSION_ENV] = version
            env[TERRAFORM_AUTO_INSTALL_ENV] = "true"
    return env


def build_init_argv(binary: str, *, no_color: bool = False) -> list[str]:
    argv = [binary, "init"]
    if no_color:
        argv.append("-no-color")
    return argv


def build_render_apply_argv(
    binary: str, target: str, *, no_color: bool = False
) -> list[str]:
    argv = [binary, "apply", f"-target={target}", "-auto-approve"]
    if no_color:
        argv.append("-no-color")
    return argv


def build_plan_argv(
    binary: str, out_file: str = DEFAULT_PLAN_FILE, *, no_color: bool = False
) -> list[str]:
    argv = [binary, "plan", f"-out={out_file}"]
    if no_color:
        argv.append("-no-color")
    return argv


def build_show_text_argv(
    binary: str, plan_file: str = DEFAULT_PLAN_FILE, *, no_color: bool = False
) -> list[str]:
    argv = [binary, "show"]
    if no_color:
        argv.append("-no-color")
    argv.append(plan_file)
    return argv


def build_show_json_argv(binary: str, plan_file: str = DEFAULT_PLAN_FILE) -> list[str]:
    return [binary, "show", "-json", plan_file]


def build_apply_argv(
    binary: str,
    *,
    plan_file: str | None = None,
    auto_approve: bool = False,
    no_color: bool = False,
) -> list[str]:
    argv = [binary, "apply"]
    if no_color:
        argv.append("-no-color")
    if plan_file is not None:
        argv.append(plan_file)
        return argv
    if auto_approve:
        argv.append("-auto-approve")
    return argv


def build_destroy_argv(
    binary: str,
    *,
    auto_approve: bool = False,
    no_color: bool = False,
) -> list[str]:
    argv = [binary, "destroy"]
    if no_color:
        argv.append("-no-color")
    if auto_approve:
        argv.append("-auto-approve")
    return argv
