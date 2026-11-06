# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

# ValidateConfig.schema / NacConfig.validate intentionally use the same
# names as nac.yaml's own keys; pydantic only warns because they shadow
# deprecated pydantic-v1 classmethods that this codebase never calls.
import warnings
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import pydantic
import ruamel.yaml
from pydantic import BaseModel, ConfigDict, model_validator

from nac.exceptions import ConfigError

warnings.filterwarnings(
    "ignore",
    message=r'Field name ".*" in ".*" shadows an attribute in parent "BaseModel"',
    category=UserWarning,
)

DEFAULT_CONFIG_PATH = Path("nac.yaml")


class DataConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paths: list[str] = ["data/"]
    defaults: str | None = None


class RenderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str | None = None
    output: str | None = None

    @model_validator(mode="after")
    def _target_requires_output(self) -> "RenderConfig":
        if self.target is not None and self.output is None:
            raise ValueError("render.output must be set when render.target is set")
        return self


class ValidateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: str | None = None  # ty: ignore[invalid-attribute-override]
    rules: list[str] | None = None


class TestConfig(BaseModel):
    # Tells pytest not to try collecting this as a test class -- it's a
    # config model that happens to be named after nac.yaml's `test:` key.
    __test__ = False

    model_config = ConfigDict(extra="forbid")

    templates: str | None = None
    filters: str | None = None
    output: str = "tests/results"


class TerraformToolConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: Literal["tofu", "terraform"] | None = None
    version: str | None = None


class ToolsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    terraform: TerraformToolConfig = TerraformToolConfig()
    nac_validate: str | None = None
    nac_test: str | None = None


class EnvConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required: list[str] = []


class NacConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    working_dir: Path = Path(".")
    data: DataConfig = DataConfig()
    render: RenderConfig | None = None
    validate: ValidateConfig = ValidateConfig()  # ty: ignore[invalid-attribute-override]
    test: TestConfig = TestConfig()
    tools: ToolsConfig = ToolsConfig()
    env: EnvConfig = EnvConfig()


def load_config(
    path: Path | str = DEFAULT_CONFIG_PATH,
    *,
    defaults: Mapping[str, Any] | None = None,
) -> NacConfig:
    """Load, validate, and resolve conventions for a nac.yaml file.

    A missing file is treated as an empty config -- every field defaults,
    so `nac` works with zero config present. `defaults` (a module's
    manifest `config`) fills in whatever the file doesn't set; see
    `merge_defaults`. Raises ConfigError (never a raw pydantic/ruamel
    traceback) on malformed YAML or a schema validation failure.
    """
    path = Path(path)
    raw = read_raw_config(path)
    if defaults is not None:
        raw, _ = merge_defaults(raw, defaults)
    return build_config(raw, path)


def read_raw_config(path: Path) -> dict[str, Any]:
    """The nac.yaml mapping as written, without validation or defaults."""
    raw: object = {}
    if path.is_file():
        yaml = ruamel.yaml.YAML(typ="safe")
        try:
            with path.open("r", encoding="utf-8") as fh:
                raw = yaml.load(fh)
        except ruamel.yaml.YAMLError as exc:
            raise ConfigError(f"Failed to parse {path}: {exc}") from exc

    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError(
            f"Config file {path} must contain a YAML mapping at the top level"
        )
    return raw


def build_config(raw: Mapping[str, Any], path: Path) -> NacConfig:
    """Validate a raw nac.yaml mapping and apply filesystem conventions."""
    try:
        cfg = NacConfig.model_validate(raw)
    except pydantic.ValidationError as exc:
        raise ConfigError(_format_validation_error(path, exc)) from exc

    return _apply_filesystem_defaults(cfg, path)


def merge_defaults(
    raw: Mapping[str, Any], defaults: Mapping[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Fill `raw` (nac.yaml as written) with `defaults` (from a manifest).

    Mappings are merged key by key; any other value set in `raw` -- lists
    and an explicit `null` included -- wins as a whole. So
    `render: {output: x.yaml}` keeps the module's render target, while
    `render: null` or `render: {target: null}` turns it off.

    Returns the merged mapping and the dotted keys taken from `defaults`.
    """
    merged = dict(raw)
    applied: list[str] = []
    for key, value in defaults.items():
        if key not in raw:
            merged[key] = value
            applied.extend(_leaf_keys(key, value))
        elif isinstance(raw[key], Mapping) and isinstance(value, Mapping):
            merged[key], nested = merge_defaults(raw[key], value)
            applied.extend(f"{key}.{leaf}" for leaf in nested)
    return merged, applied


def _leaf_keys(prefix: str, value: Any) -> list[str]:
    if isinstance(value, Mapping) and value:
        return [
            leaf
            for key, nested in value.items()
            for leaf in _leaf_keys(f"{prefix}.{key}", nested)
        ]
    return [prefix]


def _format_validation_error(path: Path, exc: pydantic.ValidationError) -> str:
    lines = [f"Invalid config file: {path}"]
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"]) or "<root>"
        lines.append(f"  {loc}: {err['msg']}")
    return "\n".join(lines)


def _apply_filesystem_defaults(cfg: NacConfig, config_path: Path) -> NacConfig:
    working_dir_abs = (config_path.parent / cfg.working_dir).resolve()

    data = cfg.data
    if data.defaults is None and (working_dir_abs / "defaults.yaml").is_file():
        data = data.model_copy(update={"defaults": "defaults.yaml"})

    test = cfg.test
    if test.templates is None and (working_dir_abs / "tests" / "templates").is_dir():
        test = test.model_copy(update={"templates": "tests/templates"})
    if test.filters is None and (working_dir_abs / "tests" / "filters").is_dir():
        test = test.model_copy(update={"filters": "tests/filters"})

    return cfg.model_copy(
        update={"working_dir": working_dir_abs, "data": data, "test": test}
    )


def resolve_validate_data(cfg: NacConfig) -> list[str]:
    """Data paths for `nac validate`.

    `render.output` if `render.target` is set, else `data.paths`.
    """
    if cfg.render is not None and cfg.render.target is not None:
        if cfg.render.output is None:
            raise ConfigError("render.output must be set when render.target is set")
        return [cfg.render.output]
    return list(cfg.data.paths)


def resolve_test_data(cfg: NacConfig) -> list[str]:
    """Data paths for `nac test`.

    (`render.output` if `render` is configured, else `data.paths`) with
    `data.defaults` appended whenever it's configured.
    """
    if cfg.render is not None:
        base: list[str] = [cfg.render.output] if cfg.render.output is not None else []
    else:
        base = list(cfg.data.paths)
    if cfg.data.defaults is not None:
        base = [*base, cfg.data.defaults]
    return base
