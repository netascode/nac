# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Literal

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from nac.config import NacConfig, resolve_test_data, resolve_validate_data

_SPECIFIER_PREFIXES = ("==", "!=", ">=", "<=", "~=", ">", "<")
_VERSION_RE = re.compile(r"\d+(?:\.\d+)+(?:[a-zA-Z0-9.\-+]*)?")


def _pin_suffix(version: str) -> str:
    v = version.strip()
    return v if v.startswith(_SPECIFIER_PREFIXES) else f"=={v}"


@dataclass(frozen=True)
class ToolSource:
    """Where a wrapped tool (`nac-validate`/`nac-test`) will be run from.

    `version` is populated whenever a local binary was found, even if it
    didn't satisfy `constraint` (mode is then "uvx") -- so callers can
    explain *why* uvx was used instead of the local install.
    """

    mode: Literal["local", "uvx"]
    path: str | None
    version: str | None


def _local_tool_version(binary: str) -> str | None:
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return None
    text = (result.stdout or "") + (result.stderr or "")
    match = _VERSION_RE.search(text)
    return match.group(0) if match else None


def _satisfies(version: str, constraint: str) -> bool:
    try:
        spec = SpecifierSet(_pin_suffix(constraint))
        return spec.contains(Version(version), prereleases=True)
    except (InvalidSpecifier, InvalidVersion):
        return False


def resolve_tool_source(
    tool: Literal["nac-validate", "nac-test"], constraint: str | None
) -> ToolSource:
    """Prefer a local install that satisfies `constraint`; else fall back to uvx.

    Mirrors the PATH-first resolution `nac.terraform.resolve_engine_binary`
    does for terraform/tofu, adapted for the fact that there's no external
    version manager here -- `nac` itself checks the constraint.
    """
    path = shutil.which(tool)
    if path is None:
        return ToolSource(mode="uvx", path=None, version=None)

    version = _local_tool_version(path)
    if constraint is None or (version is not None and _satisfies(version, constraint)):
        return ToolSource(mode="local", path=path, version=version)
    return ToolSource(mode="uvx", path=None, version=version)


def _tool_prefix(
    tool: Literal["nac-validate", "nac-test"], constraint: str | None
) -> list[str]:
    source = resolve_tool_source(tool, constraint)
    if source.mode == "local":
        assert source.path is not None
        return [source.path]
    argv = ["uvx"]
    if constraint is not None:
        argv += ["--from", f"{tool}{_pin_suffix(constraint)}"]
    return argv + [tool]


def build_validate_argv(cfg: NacConfig) -> list[str]:
    data = resolve_validate_data(cfg)
    argv = _tool_prefix("nac-validate", cfg.tools.nac_validate)
    argv += data
    if cfg.validate.schema is not None:
        argv += ["-s", cfg.validate.schema]
    for rule in cfg.validate.rules or []:
        argv += ["-r", rule]
    return argv


def build_test_argv(cfg: NacConfig) -> list[str]:
    data = resolve_test_data(cfg)
    argv = _tool_prefix("nac-test", cfg.tools.nac_test)
    for d in data:
        argv += ["-d", d]
    argv += ["-t", cfg.test.templates]
    if cfg.test.filters is not None:
        argv += ["-f", cfg.test.filters]
    argv += ["-o", cfg.test.output]
    return argv


def build_prewarm_argv(
    tool: Literal["nac-validate", "nac-test"], version: str | None
) -> list[str]:
    name = f"{tool}{_pin_suffix(version)}" if version is not None else tool
    return ["uv", "tool", "install", "--from", name, tool]


def build_help_argv(
    tool: Literal["nac-validate", "nac-test"], version: str | None
) -> list[str]:
    return _tool_prefix(tool, version) + ["--help"]
