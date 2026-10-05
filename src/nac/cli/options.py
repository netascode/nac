# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""Annotated Typer option aliases shared across nac's subcommands."""

from enum import Enum
from pathlib import Path
from typing import Annotated

import typer


class VerbosityLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


ConfigPath = Annotated[
    Path,
    typer.Option(
        "--config",
        help="Path to the nac.yaml config file.",
        envvar="NAC_CONFIG",
    ),
]

Verbosity = Annotated[
    VerbosityLevel,
    typer.Option(
        "-v",
        "--verbosity",
        help="Verbosity level.",
        envvar="NAC_VERBOSITY",
        is_eager=True,
    ),
]

AutoApprove = Annotated[
    bool,
    typer.Option(
        "--auto-approve",
        help="Skip interactive approval (apply: only without a saved plan).",
    ),
]

Artifacts = Annotated[
    bool,
    typer.Option(
        "--artifacts",
        help=(
            "Also write the command's output to <command>.txt in the "
            "working dir (e.g. validate.txt, plan.txt/plan.json)."
        ),
    ),
]

Yes = Annotated[
    bool,
    typer.Option(
        "--yes",
        "--install",
        help="Assume yes for confirmation prompts (e.g. the OpenTofu bootstrap install).",
    ),
]

Prewarm = Annotated[
    bool,
    typer.Option(
        "--prewarm",
        help="Pre-warm the uvx cache for nac-validate/nac-test.",
    ),
]

NoColor = Annotated[
    bool,
    typer.Option(
        "--no-color",
        help="Disable colored output (also honored via the NO_COLOR env var).",
    ),
]

__all__ = [
    "AutoApprove",
    "Artifacts",
    "ConfigPath",
    "NoColor",
    "Prewarm",
    "Verbosity",
    "VerbosityLevel",
    "Yes",
]
