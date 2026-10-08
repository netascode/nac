# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""Advisory checks of nac-validate/nac-test against the module's tested versions.

`validate`/`test` check the tool they run (and `setup` both) and print a
warning for versions outside the tested, semver-compatible range -- before
the tool runs, plus a short note afterwards if it failed. Never changes
exit codes.
"""

from pathlib import Path
from typing import Literal, cast

import typer

from nac import tools
from nac.config import NacConfig
from nac.manifest import Manifest, load_manifest
from nac.output import YELLOW, color

_MANIFEST_KEY = "manifest"


def get_manifest(ctx: typer.Context, cfg: NacConfig) -> Manifest | None:
    """Load (once per invocation) the manifest of the initialized module."""
    if _MANIFEST_KEY not in ctx.meta:
        ctx.meta[_MANIFEST_KEY] = load_manifest(cfg.working_dir)
    return cast("Manifest | None", ctx.meta[_MANIFEST_KEY])


def tool_warnings(
    manifest: Manifest | None,
    tool: Literal["nac-validate", "nac-test"],
    explicit: str | None,
) -> list[str]:
    """Warnings for nac-validate/nac-test.

    Without an explicit `tools.*` constraint the tool is resolved to the
    latest compatible release (see `tools.tool_constraint`), so there is
    nothing to warn about. With one, the version is known only for a local
    install or an exact pin -- a range resolved by uvx isn't checked.
    """
    if manifest is None or explicit is None or tool not in manifest.tools:
        return []
    source = tools.resolve_tool_source(tool, explicit)
    version = source.version if source.mode == "local" else tools.exact_pin(explicit)
    warning = manifest.check_tool(tool, version)
    return [warning] if warning is not None else []


def emit_warnings(
    warnings: list[str],
    *,
    no_color: bool,
    log_path: Path | None = None,
    append: bool = False,
) -> bool:
    """Print warnings to stderr and, if given, write them to log_path.

    Returns whether log_path was written, i.e. whether the next
    `run_streaming` call for the same artifact must append to it.
    """
    for warning in warnings:
        typer.echo(color(YELLOW, f"Warning: {warning}", no_color=no_color), err=True)
    if not warnings or log_path is None:
        return False
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a" if append else "w", encoding="utf-8") as fh:
        fh.writelines(f"Warning: {warning}\n" for warning in warnings)
    return True


def note_on_failure(
    command: str,
    code: int,
    warnings: list[str],
    *,
    no_color: bool,
    log_path: Path | None = None,
) -> None:
    """After a failed run, point back at the version warnings printed earlier."""
    if code == 0 or not warnings:
        return
    note = (
        f"Note: `nac {command}` failed while using versions outside the tested "
        "range (see warnings above); this may be related."
    )
    typer.echo(color(YELLOW, note, no_color=no_color), err=True)
    if log_path is not None and log_path.is_file():
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"{note}\n")
