# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""`nac test` -- streams nac-test built from config."""

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
from .versions import emit_warnings, get_manifest, note_on_failure, tool_warnings


@app.command(
    name="test",
    context_settings=PASSTHROUGH_CONTEXT_SETTINGS,
    options_metavar=PASSTHROUGH_OPTIONS_METAVAR,
)
def test_(ctx: typer.Context, artifacts: Artifacts = False) -> None:
    """Run nac-test against the configured data/templates/filters/output.

    Extra arguments are passed through to `nac-test`.
    """
    cfg = get_config(ctx)
    no_color = get_no_color(ctx)
    log_path = cfg.working_dir / "test.txt" if artifacts else None
    manifest = get_manifest(ctx, cfg)

    try:
        tool_argv = (
            tools.build_help_argv(
                "nac-test",
                tools.tool_constraint("nac-test", cfg.tools.nac_test, manifest),
            )
            if wants_help(ctx)
            else tools.build_test_argv(cfg, manifest) + ctx.args
        )
    except UvNotFoundError as exc:
        fail(str(exc))

    if wants_help(ctx):
        show_help_and_exit(
            ctx,
            tool_argv,
            cwd=cfg.working_dir,
            env=tools.build_tool_env("nac-test", no_color=no_color),
            no_color=no_color,
            tool_label="nac-test",
            usage_as="nac test",
        )

    warnings = tool_warnings(manifest, "nac-test", cfg.tools.nac_test)
    log_written = emit_warnings(warnings, no_color=no_color, log_path=log_path)

    code = runner.run_streaming(
        tool_argv,
        cwd=cfg.working_dir,
        env=tools.build_tool_env("nac-test", no_color=no_color),
        log_path=log_path,
        append=log_written,
        no_color=no_color,
    )
    note_on_failure("test", code, warnings, no_color=no_color, log_path=log_path)
    raise typer.Exit(code=code)
