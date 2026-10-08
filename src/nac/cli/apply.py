# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""`nac apply` -- applies a saved plan if present, else runs interactively."""

import typer

from nac import runner, terraform

from .main import app, get_config, get_no_color, resolve_engine_or_exit
from .options import Artifacts, AutoApprove
from .passthrough import (
    PASSTHROUGH_CONTEXT_SETTINGS,
    PASSTHROUGH_OPTIONS_METAVAR,
    show_help_and_exit,
    wants_help,
)


@app.command(
    context_settings=PASSTHROUGH_CONTEXT_SETTINGS,
    options_metavar=PASSTHROUGH_OPTIONS_METAVAR,
)
def apply(
    ctx: typer.Context,
    auto_approve: AutoApprove = False,
    artifacts: Artifacts = False,
) -> None:
    """Apply a saved plan file if present, otherwise apply interactively.

    Extra arguments are passed through to `terraform`/`tofu`.
    """
    cfg = get_config(ctx)
    engine, binary = resolve_engine_or_exit(cfg)
    env = terraform.build_engine_env(engine, cfg.tools.terraform.version)
    no_color = get_no_color(ctx)

    if wants_help(ctx):
        show_help_and_exit(
            ctx,
            [binary, "apply", "--help"],
            cwd=cfg.working_dir,
            env=env,
            no_color=get_no_color(ctx),
            tool_label=f"{engine} apply",
            usage_as="nac apply",
        )

    plan_file = cfg.working_dir / terraform.DEFAULT_PLAN_FILE
    used_plan_file = plan_file.is_file()
    if used_plan_file:
        argv = terraform.build_apply_argv(
            binary, plan_file=terraform.DEFAULT_PLAN_FILE, no_color=no_color
        )
    else:
        argv = terraform.build_apply_argv(
            binary, auto_approve=auto_approve, no_color=no_color
        )

    code = runner.run_streaming(
        argv + ctx.args,
        cwd=cfg.working_dir,
        env=env,
        log_path=cfg.working_dir / "apply.txt" if artifacts else None,
        no_color=no_color,
    )
    if used_plan_file and code == 0:
        plan_file.unlink()
    raise typer.Exit(code=code)
