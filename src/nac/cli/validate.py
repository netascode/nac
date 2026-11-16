# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""`nac validate` -- optional targeted render, then nac-validate."""

import typer

from nac import runner, tools
from nac.exceptions import UvNotFoundError

from .main import app, fail, get_config, get_no_color
from .options import Artifacts
from .passthrough import (
    PASSTHROUGH_CONTEXT_SETTINGS,
    PASSTHROUGH_OPTIONS_METAVAR,
    show_help_and_exit,
    wants_help,
)
from .render import run_render
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

    try:
        tool_argv = (
            tools.build_help_argv("nac-validate", constraint)
            if wants_help(ctx)
            else tools.build_validate_argv(cfg, manifest) + ctx.args
        )
    except UvNotFoundError as exc:
        fail(str(exc))

    if wants_help(ctx):
        show_help_and_exit(
            ctx,
            tool_argv,
            cwd=cfg.working_dir,
            env=tools.build_tool_env("nac-validate", no_color=no_color),
            no_color=no_color,
            tool_label="nac-validate",
            usage_as="nac validate",
        )

    warnings = tool_warnings(manifest, "nac-validate", cfg.tools.nac_validate)
    log_written = emit_warnings(warnings, no_color=no_color, log_path=log_path)

    log_written = run_render(
        cfg, no_color=no_color, log_path=log_path, append=log_written
    )

    code = runner.run_streaming(
        tool_argv,
        cwd=cfg.working_dir,
        env=tools.build_tool_env("nac-validate", no_color=no_color),
        log_path=log_path,
        append=log_written,
        no_color=no_color,
    )
    note_on_failure("validate", code, warnings, no_color=no_color, log_path=log_path)
    raise typer.Exit(code=code)
