# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""`nac plan` -- saves a plan file and, optionally, plan.txt/plan.json."""

import typer

from nac import runner, terraform

from .main import app, get_config, get_no_color, resolve_engine_or_exit
from .options import Artifacts
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
def plan(ctx: typer.Context, artifacts: Artifacts = False) -> None:
    """Produce a saved plan file, optionally with plan.txt/plan.json artifacts.

    Extra arguments are passed through to `terraform`/`tofu` (only to the
    `plan` invocation itself, not to the `show` calls used for artifacts).
    """
    cfg = get_config(ctx)
    engine, binary = resolve_engine_or_exit(cfg)
    env = terraform.build_engine_env(engine, cfg.tools.terraform.version)
    no_color = get_no_color(ctx)

    if wants_help(ctx):
        show_help_and_exit(
            ctx,
            [binary, "plan", "--help"],
            cwd=cfg.working_dir,
            env=env,
            no_color=get_no_color(ctx),
            tool_label=f"{engine} plan",
            usage_as="nac plan",
        )

    code = runner.run_streaming(
        terraform.build_plan_argv(binary, no_color=no_color) + ctx.args,
        cwd=cfg.working_dir,
        env=env,
    )
    if code != 0:
        raise typer.Exit(code=code)

    if artifacts:
        code = runner.run_streaming(
            terraform.build_show_text_argv(binary, no_color=no_color),
            cwd=cfg.working_dir,
            env=env,
            log_path=cfg.working_dir / "plan.txt",
        )
        if code != 0:
            raise typer.Exit(code=code)

        code = runner.run_streaming(
            terraform.build_show_json_argv(binary),
            cwd=cfg.working_dir,
            env=env,
            log_path=cfg.working_dir / "plan.json",
        )
        if code != 0:
            raise typer.Exit(code=code)

    raise typer.Exit(code=0)
