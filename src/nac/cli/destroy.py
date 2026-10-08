# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""`nac destroy` -- streams `terraform destroy`."""

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
def destroy(
    ctx: typer.Context,
    auto_approve: AutoApprove = False,
    artifacts: Artifacts = False,
) -> None:
    """Destroy the managed infrastructure (interactive unless --auto-approve).

    Extra arguments are passed through to `terraform`/`tofu`.
    """
    cfg = get_config(ctx)
    engine, binary = resolve_engine_or_exit(cfg)
    env = terraform.build_engine_env(engine, cfg.tools.terraform.version)
    no_color = get_no_color(ctx)

    if wants_help(ctx):
        show_help_and_exit(
            ctx,
            [binary, "destroy", "--help"],
            cwd=cfg.working_dir,
            env=env,
            no_color=get_no_color(ctx),
            tool_label=f"{engine} destroy",
            usage_as="nac destroy",
        )

    argv = terraform.build_destroy_argv(
        binary, auto_approve=auto_approve, no_color=no_color
    )

    code = runner.run_streaming(
        argv + ctx.args,
        cwd=cfg.working_dir,
        env=env,
        log_path=cfg.working_dir / "destroy.txt" if artifacts else None,
        no_color=no_color,
    )
    raise typer.Exit(code=code)
