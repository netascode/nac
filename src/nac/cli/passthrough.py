# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""Shared plumbing for forwarding extra CLI args to a wrapped tool and for
delegating `--help`/`-h` to that tool's own help output.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

import typer

from nac.output import BOLD, color, utf8_env

# `options_metavar` replaces the bare `[OPTIONS]` in nac's own usage line so it
# is clear that unrecognised arguments are forwarded to the wrapped tool.
PASSTHROUGH_OPTIONS_METAVAR = "[OPTIONS] [PASSTHROUGH-ARGS]..."

_ANSI = r"(?:\x1b\[[0-9;]*m|\s)*"
# First Rich panel border (`╭─ Arguments ─╮` / `╭─ Options ─╮`), possibly
# preceded by ANSI styling.
_FIRST_PANEL_RE = re.compile(r"^(?:\x1b\[[0-9;]*m)*╭", re.MULTILINE)
# First options section heading in terraform/tofu help (`Options:`,
# `Plan Customization Options:`, ...).
_FIRST_OPTIONS_HEADING_RE = re.compile(r"^[A-Za-z ]*Options:$", re.MULTILINE)
_USAGE_PROG_RE = re.compile(
    rf"(Usage:{_ANSI})(?:nac-validate|nac-test|terraform|tofu)(?: \[global options\](?: [a-z]+)?)?"
)

PASSTHROUGH_CONTEXT_SETTINGS = {
    "allow_extra_args": True,
    "ignore_unknown_options": True,
    "help_option_names": [],
}


def wants_help(ctx: typer.Context) -> bool:
    """Whether the leftover passthrough args include a help flag.

    Safe to check anywhere in `ctx.args` (not just the first token) since
    `ignore_unknown_options` guarantees nothing else has been pre-interpreted,
    and none of the wrapped tools (nac-validate, nac-test, terraform/tofu)
    have an unrelated `-h` short flag that could collide.
    """
    return "--help" in ctx.args or "-h" in ctx.args


def _tool_help_body(text: str, usage_as: str) -> str:
    """Reduce the wrapped tool's help to what nac's own help doesn't cover.

    Rich-based tools (nac-validate, nac-test) print a usage line and a
    description before their Arguments/Options panels, and terraform/tofu
    print theirs before the first `... Options:` heading; both are dropped,
    as nac already printed its own usage and description. If neither marker
    is found, the full text is kept with its usage line rewritten to the
    `nac <command>` form the user actually types.
    """
    start = _FIRST_PANEL_RE.search(text) or _FIRST_OPTIONS_HEADING_RE.search(text)
    if start:
        return text[start.start() :]
    return _USAGE_PROG_RE.sub(lambda m: m.group(1) + usage_as, text, count=1)


def show_help_and_exit(
    ctx: typer.Context,
    tool_argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    no_color: bool,
    tool_label: str,
    usage_as: str,
) -> NoReturn:
    """Print nac's own help for this subcommand, then the wrapped tool's
    own `--help` output below a labeled separator, and exit with that
    tool's code.

    The tool's output is captured (its stdout is not a TTY) so that:
    - color and terminal width are forced on for it when nac's own stdout is
      a TTY (and color is not disabled), matching nac's own help rendering;
    - its own usage/description header is dropped (see `_tool_help_body`),
      since nac already printed its own, leaving just the options.
    """
    typer.echo(ctx.get_help())

    child_env = utf8_env(env)
    if sys.stdout.isatty():
        child_env["COLUMNS"] = str(shutil.get_terminal_size().columns)
        if not no_color:
            child_env["FORCE_COLOR"] = "1"

    proc = subprocess.run(
        tool_argv,
        cwd=cwd,
        env=child_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    text = _tool_help_body(proc.stdout, usage_as)

    rule = f"── Passed through to {tool_label} "
    rule += "─" * max(0, shutil.get_terminal_size().columns - len(rule))
    typer.echo(color(BOLD, rule, no_color=no_color))
    typer.echo()
    typer.echo(text, nl=False)
    raise typer.Exit(code=proc.returncode)
