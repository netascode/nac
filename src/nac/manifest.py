# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""Tested-versions manifest shipped with a Network-as-Code Terraform module.

A module may ship a `nac/manifest.yaml` (next to the rest of its nac-specific
content: schema, rules, test templates) listing the nac-validate/nac-test
versions it was tested with. terraform/tofu and provider versions are not
part of it: the module's `versions.tf` already constrains those, and
Terraform enforces them itself. After `terraform init`, `nac` finds it via
`.terraform/modules/modules.json` and uses it purely as a hint: versions
outside the tested, semver-compatible range produce a warning, never an
error. A missing or unreadable manifest is silently ignored.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pydantic
import ruamel.yaml
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

MANIFEST_FILE = "nac/manifest.yaml"
MODULES_JSON = Path(".terraform") / "modules" / "modules.json"
_REGISTRY_HOSTS = ("registry.terraform.io/", "registry.opentofu.org/")


class _ManifestFile(BaseModel):
    # Unknown keys are ignored so newer manifests keep working with older nac.
    model_config = ConfigDict(extra="ignore", coerce_numbers_to_str=True)

    schema_version: Literal[1] = pydantic.Field(alias="schema")
    tools: dict[str, str] = {}


@dataclass(frozen=True)
class Manifest:
    """Tested versions for one module, keyed by tool name.

    `module` is a human-readable label for messages, e.g.
    `netascode/nac-nxos/nxos 0.3.0`.
    """

    module: str
    tools: dict[str, str] = field(default_factory=dict)

    def check_tool(self, name: str, actual: str | None) -> str | None:
        """Warning message if `actual` is outside the tested range, else None."""
        tested = self.tools.get(name)
        if actual is None or tested is None:
            return None
        status = classify(actual, tested)
        if status == "compatible":
            logger.info(
                "%s %s is newer than the version tested with %s (%s) but "
                "semver-compatible",
                name,
                actual,
                self.module,
                tested,
            )
        if status != "untested":
            return None
        return (
            f"{name} {actual} is outside the range tested with {self.module} "
            f"(tested: {tested}, compatible: {compatible_range(tested)})"
        )


def compatible_range(tested: str) -> str | None:
    """Semver-compatible range starting at `tested`.

    Upward-only, up to the next major -- or the next minor for 0.x, where
    a minor bump may be breaking. None if `tested` isn't a valid version.
    """
    try:
        version = Version(tested)
    except InvalidVersion:
        return None
    upper = f"{version.major + 1}" if version.major > 0 else f"0.{version.minor + 1}"
    return f">={version},<{upper}"


def classify(
    actual: str, tested: str
) -> Literal["tested", "compatible", "untested"] | None:
    """How `actual` relates to `tested`; None if either isn't a valid version."""
    spec = compatible_range(tested)
    try:
        actual_version = Version(actual)
    except InvalidVersion:
        return None
    if spec is None:
        return None
    if actual_version == Version(tested):
        return "tested"
    if SpecifierSet(spec).contains(actual_version, prereleases=True):
        return "compatible"
    return "untested"


def load_manifest(working_dir: Path) -> Manifest | None:
    """Find and parse the manifest of an initialized module in working_dir.

    Considers every module in `.terraform/modules/modules.json` that ships
    a manifest, preferring the shallowest (so a local wrapper module around
    a netascode module still works). Returns None if there is none or it
    can't be read -- the manifest is only ever a hint.
    """
    try:
        raw = json.loads((working_dir / MODULES_JSON).read_text(encoding="utf-8"))
        modules = raw["Modules"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(modules, list):
        return None

    candidates = [
        m for m in modules if isinstance(m, dict) and m.get("Key") and m.get("Dir")
    ]
    candidates.sort(key=lambda m: str(m["Key"]).count("."))
    for module in candidates:
        path = working_dir / str(module["Dir"]) / MANIFEST_FILE
        if path.is_file():
            manifest = _parse_manifest(path, _module_label(module))
            if manifest is not None:
                return manifest
    return None


def _module_label(module: dict[str, object]) -> str:
    source = str(module.get("Source") or "")
    version = str(module.get("Version") or "")
    for host in _REGISTRY_HOSTS:
        if source.startswith(host):
            return f"{source[len(host) :]} {version}".strip()
    return f"module.{module['Key']}"


def _parse_manifest(path: Path, label: str) -> Manifest | None:
    yaml = ruamel.yaml.YAML(typ="safe")
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = _ManifestFile.model_validate(yaml.load(fh))
    except (OSError, ruamel.yaml.YAMLError, pydantic.ValidationError) as exc:
        logger.debug("Ignoring unreadable manifest %s: %s", path, exc)
        return None
    return Manifest(module=label, tools=dict(data.tools))
