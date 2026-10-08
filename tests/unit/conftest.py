# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

import json
from collections.abc import Callable
from pathlib import Path

import pytest

DEFAULT_MANIFEST = """\
schema: 1
tools:
  nac-validate: 2.0.0
  nac-test: 2.0.0
"""

WriteModule = Callable[..., Path]


@pytest.fixture
def write_module() -> WriteModule:
    """Factory faking an initialized module (as `terraform init` leaves it)
    that ships a nac/manifest.yaml, under `<root>/.terraform/modules/`."""

    def _write(
        root: Path,
        manifest: str | None = DEFAULT_MANIFEST,
        *,
        key: str = "nxos",
        source: str = "registry.terraform.io/netascode/nac-nxos/nxos",
        version: str = "0.3.0",
    ) -> Path:
        modules_dir = root / ".terraform" / "modules"
        module_dir = modules_dir / key
        module_dir.mkdir(parents=True, exist_ok=True)
        if manifest is not None:
            (module_dir / "nac").mkdir(exist_ok=True)
            (module_dir / "nac" / "manifest.yaml").write_text(manifest)
        modules_json = modules_dir / "modules.json"
        entries = (
            json.loads(modules_json.read_text())["Modules"]
            if modules_json.is_file()
            else [{"Key": "", "Source": "", "Dir": "."}]
        )
        entries.append(
            {
                "Key": key,
                "Source": source,
                "Version": version,
                "Dir": f".terraform/modules/{key}",
            }
        )
        modules_json.write_text(json.dumps({"Modules": entries}))
        return module_dir

    return _write
