# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""Manifest shipped with a Network-as-Code Terraform module.

A module may ship a `nac/manifest.yaml` (next to the rest of its nac-specific
content: schema, rules, test templates) with:

- `tools`: the nac-validate/nac-test versions it was tested with.
  terraform/tofu and provider versions are not part of it: the module's
  `versions.tf` already constrains those, and Terraform enforces them
  itself. Versions outside the tested, semver-compatible range produce a
  warning, never an error.
- `config`: module-specific `nac.yaml` defaults (render target, required
  environment variables), so that projects using the module don't have to
  repeat them. The project's own `nac.yaml` always takes precedence.

After `terraform init`, `nac` finds it via `.terraform/modules/modules.json`.
A missing or unreadable manifest is silently ignored; an invalid `config`
section is ignored with a warning, keeping the rest of the manifest.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import pydantic
import ruamel.yaml
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

logger = logging.getLogger(__name__)

MANIFEST_FILE = "nac/manifest.yaml"
MODULES_JSON = Path(".terraform") / "modules" / "modules.json"
_REGISTRY_HOSTS = ("registry.terraform.io/", "registry.opentofu.org/")


class _ManifestFile(BaseModel):
    # Unknown keys are ignored so newer manifests keep working with older nac.
    model_config = ConfigDict(extra="ignore", coerce_numbers_to_str=True)

    schema_version: Literal[1] = pydantic.Field(alias="schema")
    tools: dict[str, str] = {}
    # Validated separately (_ManifestConfig) so that a broken `config`
    # section doesn't also discard the tested versions.
    config: object = None


class _RenderDefaults(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Resource address relative to the module, e.g.
    # `local_sensitive_file.model`; nac prefixes the module's own address.
    resource: str | None = None
    output: str | None = None

    @field_validator("resource")
    @classmethod
    def _relative_address(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or value.startswith("module.")):
            raise ValueError(
                "must be a resource address relative to the module, "
                "e.g. `local_sensitive_file.model`"
            )
        return value

    @model_validator(mode="after")
    def _resource_requires_output(self) -> "_RenderDefaults":
        if self.resource is not None and self.output is None:
            raise ValueError("render.output must be set when render.resource is set")
        return self


class _EnvDefaults(BaseModel):
    model_config = ConfigDict(extra="ignore")

    required: list[str] | None = None


class _ManifestConfig(BaseModel):
    """`nac.yaml` defaults a module may provide.

    Deliberately limited to module-specific settings; anything about the
    project's layout or toolchain (working_dir, data paths, terraform
    engine, ...) stays with the project's own `nac.yaml`.
    """

    model_config = ConfigDict(extra="ignore")

    render: _RenderDefaults | None = None
    env: _EnvDefaults | None = None


@dataclass(frozen=True)
class Manifest:
    """Tested versions for one module, keyed by tool name.

    `module` is a human-readable label for messages, e.g.
    `netascode/nac-nxos/nxos 0.3.0`.
    """

    module: str
    tools: dict[str, str] = field(default_factory=dict)
    # `nac.yaml`-shaped defaults (see config.merge_defaults), already
    # resolved against the module's address, e.g.
    # {"render": {"target": "module.nxos.local_sensitive_file.model", ...}}
    config: dict[str, Any] = field(default_factory=dict)

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
            manifest = _parse_manifest(
                path, _module_label(module), _module_address(str(module["Key"]))
            )
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


def _module_address(key: str) -> str:
    """Terraform address of a module from its modules.json key.

    `nxos` -> `module.nxos`, `wrapper.nxos` -> `module.wrapper.module.nxos`.
    """
    return ".".join(f"module.{part}" for part in key.split("."))


def _parse_manifest(path: Path, label: str, address: str) -> Manifest | None:
    yaml = ruamel.yaml.YAML(typ="safe")
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = _ManifestFile.model_validate(yaml.load(fh))
    except (OSError, ruamel.yaml.YAMLError, pydantic.ValidationError) as exc:
        logger.debug("Ignoring unreadable manifest %s: %s", path, exc)
        return None
    return Manifest(
        module=label,
        tools=dict(data.tools),
        config=_parse_config(data.config, path, address),
    )


def _parse_config(raw: object, path: Path, address: str) -> dict[str, Any]:
    """Translate the manifest's `config` into `nac.yaml`-shaped defaults."""
    if raw is None:
        return {}
    try:
        config = _ManifestConfig.model_validate(raw)
    except pydantic.ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
            for err in exc.errors()
        )
        logger.warning("Ignoring invalid `config` in %s: %s", path, details)
        return {}

    result: dict[str, Any] = {}
    if config.render is not None:
        render: dict[str, Any] = {}
        if config.render.resource is not None:
            render["target"] = f"{address}.{config.render.resource}"
        if config.render.output is not None:
            render["output"] = config.render.output
        if render:
            result["render"] = render
    if config.env is not None and config.env.required is not None:
        result["env"] = {"required": list(config.env.required)}
    return result
