# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""`nac validate` -- optional targeted render, then nac-validate."""

import logging

import typer

from nac import runner, terraform, tools
from nac.output import GREEN, apply_no_color_env, color, echo_summary

from .main import app, get_config, get_no_color, resolve_engine_or_exit
from .options import Artifacts
from .passthrough import (
    PASSTHROUGH_CONTEXT_SETTINGS,
    PASSTHROUGH_OPTIONS_METAVAR,
    show_help_and_exit,
    wants_help,
)
from .versions import emit_warnings, get_manifest, note_on_failure, tool_warnings


@app.command(
    context_settings=PASSTHROUGH_CONTEXT_SETTINGS,
    options_metavar=PASSTHROUGH_OPTIONS_METAVAR,
)
def validate(ctx: typer.Context, artifacts: Artifacts = False) -> None:
    """Render (if configured) then validate the resolved data paths.

    Extra arguments are passed through to `nac-validate`.
    """
    cfg = get_config(ctx)
    no_color = get_no_color(ctx)
    log_path = cfg.working_dir / "validate.txt" if artifacts else None
    manifest = get_manifest(ctx, cfg)
    constraint = tools.tool_constraint("nac-validate", cfg.tools.nac_validate, manifest)

    if wants_help(ctx):
        show_help_and_exit(
            ctx,
            tools.build_help_argv("nac-validate", constraint),
            cwd=cfg.working_dir,
            env=apply_no_color_env(no_color),
            no_color=no_color,
            tool_label="nac-validate",
            usage_as="nac validate",
        )

    warnings = tool_warnings(manifest, "nac-validate", cfg.tools.nac_validate)
    log_written = emit_warnings(warnings, no_color=no_color, log_path=log_path)

    if cfg.render is not None and cfg.render.target is not None:
        engine, binary = resolve_engine_or_exit(cfg)
        env = terraform.build_engine_env(engine, cfg.tools.terraform.version)
        quiet = not logging.getLogger().isEnabledFor(logging.INFO)
        code = runner.run_streaming(
            terraform.build_render_apply_argv(
                binary, cfg.render.target, no_color=no_color
            ),
            cwd=cfg.working_dir,
            env=env,
            quiet=quiet,
            log_path=log_path,
            append=log_written,
            no_color=no_color,
        )
        log_written = True
        if code != 0:
            raise typer.Exit(code=code)
        if quiet:
            echo_summary(
                "Render Summary",
                [
                    f"Render: {color(GREEN, 'OK', no_color=no_color)} "
                    f"({cfg.render.target})"
                ],
                no_color=no_color,
            )

    code = runner.run_streaming(
        tools.build_validate_argv(cfg, manifest) + ctx.args,
        cwd=cfg.working_dir,
        env=apply_no_color_env(no_color),
        log_path=log_path,
        append=log_written,
        no_color=no_color,
    )
    note_on_failure("validate", code, warnings, no_color=no_color, log_path=log_path)
    raise typer.Exit(code=code)
