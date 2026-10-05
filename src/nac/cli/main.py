# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""CLI entry point for nac: global options, config loading, shared helpers."""

import logging
import os
import sys
from pathlib import Path
from typing import NoReturn, cast

import typer

from nac import terraform
from nac.config import DEFAULT_CONFIG_PATH, NacConfig, load_config
from nac.exceptions import ConfigError, EngineNotFoundError, NoEngineAvailableError
from nac.output import ensure_utf8_streams

from .options import ConfigPath, NoColor, Verbosity, VerbosityLevel

app = typer.Typer(
    add_completion=False,
    help="An umbrella CLI wrapping terraform/tofu, nac-validate, and nac-test.",
)


def configure_logging(level: VerbosityLevel) -> None:
    logging.basicConfig(
        level=getattr(logging, level.value),
        format="%(levelname)s - %(message)s",
        stream=sys.stdout,
        force=True,
    )


def fail(message: str, code: int = 1) -> NoReturn:
    """Print a clean error message to stderr and exit with a non-zero code."""
    typer.echo(message, err=True)
    raise typer.Exit(code=code)


def get_config(ctx: typer.Context) -> NacConfig:
    """Load (once, lazily) and return the NacConfig for this invocation.

    Deferred until a subcommand actually needs it -- rather than in the
    app callback -- so `nac <subcommand> --help` works without a config
    file present. `ctx.obj` starts out holding the raw --config path and
    is replaced with the resolved NacConfig on first call, so repeated
    calls within the same invocation don't re-read the file.
    """
    if isinstance(ctx.obj, NacConfig):
        return ctx.obj
    try:
        cfg = load_config(cast(Path, ctx.obj))
    except ConfigError as exc:
        fail(str(exc))
    ctx.obj = cfg
    return cfg


def resolve_engine_or_exit(cfg: NacConfig) -> tuple[str, str]:
    """Resolve the terraform/tofu binary, failing cleanly on any error.

    Used by init/validate/plan/apply, none of which perform the
    interactive FR-12 bootstrap prompt -- that is `nac setup`'s job.
    """
    try:
        return terraform.resolve_engine_binary(cfg.tools.terraform)
    except (EngineNotFoundError, NoEngineAvailableError) as exc:
        fail(str(exc))


def get_no_color(ctx: typer.Context) -> bool:
    """Whether colored output should be suppressed for this invocation.

    Resolved once by the app callback from the `--no-color` flag / NO_COLOR
    env var and stashed on `ctx.meta` (Click's per-invocation scratch dict),
    so it doesn't collide with `ctx.obj`'s lazy NacConfig loading above.
    """
    return bool(ctx.meta.get("no_color", False))


@app.callback()
def main(
    ctx: typer.Context,
    config: ConfigPath = DEFAULT_CONFIG_PATH,
    verbosity: Verbosity = VerbosityLevel.WARNING,
    no_color: NoColor = False,
) -> None:
    """An umbrella CLI wrapping terraform/tofu, nac-validate, and nac-test."""
    ensure_utf8_streams()
    configure_logging(verbosity)
    ctx.meta["no_color"] = no_color or "NO_COLOR" in os.environ
    ctx.obj = config
