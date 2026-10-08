# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""Shared terminal output formatting, matching nac-validate's own summary
box style (80-char `-` rule, bold header, green checkmarks) so a `nac`
invocation reads as one coherent report.

Color is on by default (matching a plain `terraform apply`); callers pass
an explicit `no_color` bool -- resolved once per invocation from the
`--no-color` flag / `NO_COLOR` env var in `nac.cli.main.get_no_color` --
rather than this module re-reading the environment itself."""

import os
import re
import shlex
import subprocess
import sys
from collections.abc import Mapping, Sequence

import typer

SEP_WIDTH = 80
BOLD = "\033[1m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
DIM = "\033[2m"
_RESET = "\033[0m"

_ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def color(code: str, text: str, *, no_color: bool = False) -> str:
    """Wrap text in an ANSI color code, unless no_color is set.

    Click strips these automatically when stdout isn't a TTY, so this
    only needs to handle the explicit opt-out.
    """
    if no_color:
        return text
    return f"{code}{text}{_RESET}"


def echo_summary(title: str, lines: list[str], *, no_color: bool = False) -> None:
    """Print a status box: bold title between `-` rules, one
    green-checkmarked line per entry in `lines`."""
    sep = "─" * SEP_WIDTH
    typer.echo(f"\n{color(BOLD, sep, no_color=no_color)}")
    typer.echo(color(BOLD, title, no_color=no_color))
    typer.echo(sep)
    for line in lines:
        typer.echo(f"  {color(GREEN, '✓', no_color=no_color)} {line}")
    typer.echo(f"{sep}\n")


def format_command(argv: Sequence[str]) -> str:
    """Render argv as a single copy-pasteable command line, quoted for the
    current platform's shell (POSIX sh, or cmd.exe-style on Windows)."""
    if sys.platform == "win32":
        return subprocess.list2cmdline(argv)
    return shlex.join(argv)


def echo_command(argv: Sequence[str], *, no_color: bool = False) -> None:
    """Print the exact command nac is about to run, as a dim `$ ...` line.

    Goes to stderr so it never mixes into a wrapped tool's stdout when that
    is piped or redirected. stdout is flushed first so the line still lands
    in order relative to output nac has already written there.
    """
    sys.stdout.flush()
    typer.echo(color(DIM, f"$ {format_command(argv)}", no_color=no_color), err=True)


def utf8_env(base_env: Mapping[str, str]) -> dict[str, str]:
    """Copy of base_env that makes Python child processes (nac-validate,
    nac-test) emit UTF-8 when piped; on Windows they would otherwise use the
    ANSI code page and crash on characters like box-drawing glyphs."""
    env = dict(base_env)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def ensure_utf8_streams() -> None:
    """Make our own stdout/stderr able to print the glyphs nac emits (─, ✓)
    even when redirected on Windows, where the default is the ANSI code page."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def strip_ansi(text: str) -> str:
    """Strip ANSI escape sequences, e.g. before writing subprocess output
    to a log file artifact (plan.txt) so it stays clean, human-diffable
    text even when the same output was streamed to the terminal in color."""
    return _ANSI_ESCAPE_RE.sub("", text)


def apply_no_color_env(
    no_color: bool, base_env: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Build a subprocess env dict, adding NO_COLOR when no_color is set.

    Terraform/OpenTofu only ever look at the literal `-no-color` CLI flag
    (never the NO_COLOR env var), so this is for forwarding the setting to
    subprocesses that *do* honor the NO_COLOR convention -- nac-validate
    and nac-test.
    """
    env = dict(base_env if base_env is not None else os.environ)
    if no_color:
        env["NO_COLOR"] = "1"
    return env
