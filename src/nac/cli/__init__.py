# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

from typer.models import CommandInfo

from . import apply, destroy, init, plan, setup, test, validate  # noqa: F401
from .main import app

# Registration order above is alphabetical (required by import sorting), but
# the help output should mirror the setup -> init -> validate -> plan ->
# apply -> test workflow, so reorder registered_commands explicitly.
_WORKFLOW_ORDER = ("setup", "init", "validate", "plan", "apply", "test", "destroy")


def _workflow_index(command: CommandInfo) -> int:
    assert command.callback is not None
    module = command.callback.__module__.rsplit(".", 1)[-1]
    return _WORKFLOW_ORDER.index(module)


app.registered_commands.sort(key=_workflow_index)
