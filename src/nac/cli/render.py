# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""Targeted render step shared by `nac validate` and `nac test`."""

import logging
from pathlib import Path

import typer

from nac import runner, terraform
from nac.config import NacConfig
from nac.output import GREEN, color, echo_summary

from .main import fail, resolve_engine_or_exit


def render_enabled(cfg: NacConfig) -> bool:
    """Whether a render step (`render.target`) is configured."""
    return cfg.render is not None and cfg.render.target is not None


def run_render(
    cfg: NacConfig,
    *,
    no_color: bool,
    log_path: Path | None,
    append: bool,
    engine_hint: str | None = None,
) -> bool:
    """Run `<engine> apply -target=<render.target>` to (re)write `render.output`.

    Does nothing if no `render.target` is configured. The targeted apply is
    idempotent: if the rendered file is up to date the engine changes
    nothing, and if it's missing or stale it's rewritten. Exits with the
    engine's exit code if the render fails, and fails cleanly if it didn't
    write `render.output`. Below INFO verbosity, the engine output is only
    shown on failure and a Render Summary is printed instead.

    `append` says whether `log_path` was already written to; the return value
    is the same flag after the render step, to pass on as the next `append`.
    `engine_hint` is added to the error if no terraform/tofu is found.
    """
    if cfg.render is None or cfg.render.target is None:
        return append
    target, output = cfg.render.target, cfg.render.output
    engine, binary = resolve_engine_or_exit(cfg, hint=engine_hint)
    env = terraform.build_engine_env(engine, cfg.tools.terraform.version)
    quiet = not logging.getLogger().isEnabledFor(logging.INFO)
    code = runner.run_streaming(
        terraform.build_render_apply_argv(binary, target, no_color=no_color),
        cwd=cfg.working_dir,
        env=env,
        quiet=quiet,
        log_path=log_path,
        append=append,
        no_color=no_color,
    )
    if code != 0:
        raise typer.Exit(code=code)
    if output is not None and not (cfg.working_dir / output).exists():
        fail(
            f"Render step `{target}` did not write `{output}`. "
            "Check that `render.output` matches the file written by the "
            "render target (for Network-as-Code modules: `write_model_file`)."
        )
    if quiet:
        echo_summary(
            "Render Summary",
            [f"Render: {color(GREEN, 'OK', no_color=no_color)} ({target} -> {output})"],
            no_color=no_color,
        )
    return True
