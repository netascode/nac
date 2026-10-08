# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""`nac init` -- streams terraform/tofu init in working_dir."""

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
def init(ctx: typer.Context, artifacts: Artifacts = False) -> None:
    """Initialize the Terraform/OpenTofu working directory.

    Extra arguments are passed through to `terraform`/`tofu`.
    """
    cfg = get_config(ctx)
    engine, binary = resolve_engine_or_exit(cfg)
    env = terraform.build_engine_env(engine, cfg.tools.terraform.version)
    no_color = get_no_color(ctx)

    if wants_help(ctx):
        show_help_and_exit(
            ctx,
            [binary, "init", "--help"],
            cwd=cfg.working_dir,
            env=env,
            no_color=no_color,
            tool_label=f"{engine} init",
            usage_as="nac init",
        )

    code = runner.run_streaming(
        terraform.build_init_argv(binary, no_color=no_color) + ctx.args,
        cwd=cfg.working_dir,
        env=env,
        log_path=cfg.working_dir / "init.txt" if artifacts else None,
        no_color=no_color,
    )
    raise typer.Exit(code=code)
