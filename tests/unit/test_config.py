# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""Unit tests for nac.config: load_config, defaulting, and resolution helpers."""

from pathlib import Path

import pydantic
import pytest

from nac.config import (
    DataConfig,
    EnvConfig,
    NacConfig,
    RenderConfig,
    ToolsConfig,
    ValidateConfig,
    _apply_filesystem_defaults,
    _format_validation_error,
    load_config,
    resolve_test_data,
    resolve_validate_data,
)
from nac.config import TestConfig as NacTestConfig
from nac.exceptions import ConfigError

pytestmark = pytest.mark.unit

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def nac_yaml_fixture(name: str) -> Path:
    """Return the path to a named nac.yaml fixture under tests/fixtures/nac-yaml/."""
    return FIXTURES_DIR / "nac-yaml" / name / "nac.yaml"


# ---------------------------------------------------------------------------
# 1. load_config happy path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture_name",
    [
        "minimal",
        "aci-lean",
        "iosxe-lean",
        "nxos-lean",
        "nxos-full",
        "filters-present",
        "filters-absent",
    ],
)
def test_load_config_valid_fixtures_parse(fixture_name: str) -> None:
    cfg = load_config(nac_yaml_fixture(fixture_name))
    assert isinstance(cfg, NacConfig)


def test_load_config_nxos_full_resolved_fields() -> None:
    cfg = load_config(nac_yaml_fixture("nxos-full"))
    assert cfg.tools.terraform.engine == "tofu"
    assert cfg.tools.terraform.version == "1.9.5"
    assert cfg.tools.nac_validate == ">=0.9,<1.0"
    assert cfg.tools.nac_test == ">=2.0,<3.0"
    assert cfg.render is not None
    assert cfg.render.target == "module.nxos.local_sensitive_file.model"
    assert cfg.render.output == "model.yaml"
    assert cfg.validate.schema == ".schema.yaml"
    assert cfg.validate.rules == [".rules"]


def test_load_config_nxos_lean_resolved_fields() -> None:
    cfg = load_config(nac_yaml_fixture("nxos-lean"))
    assert cfg.tools.terraform.engine == "tofu"
    assert cfg.render is not None
    assert cfg.render.target == "module.nxos.local_sensitive_file.model"
    assert cfg.render.output == "model.yaml"


def test_load_config_iosxe_lean_resolved_fields() -> None:
    cfg = load_config(nac_yaml_fixture("iosxe-lean"))
    assert cfg.render is not None
    assert cfg.render.target is None
    assert cfg.render.output == "model.yaml"
    assert cfg.env.required == ["IOSXE_USERNAME", "IOSXE_PASSWORD"]


# ---------------------------------------------------------------------------
# 2. load_config error paths (must always raise ConfigError)
# ---------------------------------------------------------------------------


def test_load_config_missing_file_uses_defaults(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.yaml"
    cfg = load_config(missing)
    assert cfg.data.paths == ["data/"]
    assert cfg.render is None
    assert cfg.env.required == []
    assert cfg.working_dir == missing.parent.resolve()


def test_load_config_invalid_syntax_fixture() -> None:
    with pytest.raises(ConfigError):
        load_config(nac_yaml_fixture("invalid-syntax"))


def test_load_config_unknown_top_level_key(tmp_path: Path) -> None:
    config_path = tmp_path / "nac.yaml"
    config_path.write_text("bogus_key: 1\n")
    with pytest.raises(ConfigError):
        load_config(config_path)


def test_load_config_unknown_nested_key(tmp_path: Path) -> None:
    config_path = tmp_path / "nac.yaml"
    config_path.write_text("tools:\n  terraform:\n    bogus: 1\n")
    with pytest.raises(ConfigError, match=r"tools\.terraform\.bogus") as exc_info:
        load_config(config_path)
    assert "tools.terraform.bogus" in str(exc_info.value)


def test_load_config_top_level_list_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "nac.yaml"
    config_path.write_text("- a\n- b\n")
    with pytest.raises(ConfigError, match="must contain a YAML mapping"):
        load_config(config_path)


def test_load_config_top_level_scalar_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "nac.yaml"
    config_path.write_text("just-a-scalar\n")
    with pytest.raises(ConfigError, match="must contain a YAML mapping"):
        load_config(config_path)


# ---------------------------------------------------------------------------
# 3. _format_validation_error
# ---------------------------------------------------------------------------


def test_format_validation_error_root_level() -> None:
    with pytest.raises(pydantic.ValidationError) as exc_info:
        NacConfig.model_validate("not-a-mapping")

    message = _format_validation_error(Path("nac.yaml"), exc_info.value)
    assert "Invalid config file: nac.yaml" in message
    assert "<root>:" in message


def test_format_validation_error_nested_path() -> None:
    with pytest.raises(pydantic.ValidationError) as exc_info:
        NacConfig.model_validate({"tools": {"terraform": {"bogus": 1}}})

    message = _format_validation_error(Path("nac.yaml"), exc_info.value)
    assert "tools.terraform.bogus:" in message


# ---------------------------------------------------------------------------
# 4. _apply_filesystem_defaults (exercised via load_config on fixtures)
# ---------------------------------------------------------------------------


def test_apply_filesystem_defaults_direct_call() -> None:
    cfg = NacConfig()
    config_path = nac_yaml_fixture("aci-lean")

    resolved = _apply_filesystem_defaults(cfg, config_path)

    assert resolved.data.defaults == "defaults.yaml"
    assert resolved.working_dir == config_path.parent.resolve()


def test_filesystem_defaults_detects_defaults_yaml_when_present() -> None:
    cfg = load_config(nac_yaml_fixture("aci-lean"))
    assert cfg.data.defaults == "defaults.yaml"


def test_filesystem_defaults_leaves_defaults_none_when_absent() -> None:
    cfg = load_config(nac_yaml_fixture("minimal"))
    assert cfg.data.defaults is None


def test_filesystem_defaults_detects_test_filters_when_present() -> None:
    cfg = load_config(nac_yaml_fixture("filters-present"))
    assert cfg.test.filters == "tests/filters"


def test_filesystem_defaults_leaves_test_filters_none_when_absent() -> None:
    cfg = load_config(nac_yaml_fixture("filters-absent"))
    assert cfg.test.filters is None


def test_working_dir_anchored_to_config_file_not_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_path = nac_yaml_fixture("nxos-lean")
    monkeypatch.chdir(tmp_path)

    cfg = load_config(fixture_path)

    assert cfg.working_dir == fixture_path.parent.resolve()
    assert cfg.working_dir != tmp_path.resolve()


# ---------------------------------------------------------------------------
# 5. resolve_validate_data
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture_name", ["nxos-lean", "nxos-full"])
def test_resolve_validate_data_uses_render_output_when_target_set(
    fixture_name: str,
) -> None:
    cfg = load_config(nac_yaml_fixture(fixture_name))
    assert resolve_validate_data(cfg) == ["model.yaml"]


def test_resolve_validate_data_falls_through_to_data_paths_when_no_target() -> None:
    cfg = load_config(nac_yaml_fixture("iosxe-lean"))
    assert cfg.render is not None
    assert cfg.render.target is None
    assert resolve_validate_data(cfg) == ["data/"]


@pytest.mark.parametrize("fixture_name", ["aci-lean", "minimal"])
def test_resolve_validate_data_uses_data_paths_when_no_render(
    fixture_name: str,
) -> None:
    cfg = load_config(nac_yaml_fixture(fixture_name))
    assert cfg.render is None
    assert resolve_validate_data(cfg) == ["data/"]


def test_resolve_validate_data_raises_when_output_missing_for_target() -> None:
    render = RenderConfig.model_construct(target="t", output=None)
    cfg = NacConfig.model_construct(
        working_dir=Path("."),
        data=DataConfig(),
        render=render,
        validate=ValidateConfig(),
        test=NacTestConfig(),
        tools=ToolsConfig(),
        env=EnvConfig(),
    )
    with pytest.raises(ConfigError, match="render.output"):
        resolve_validate_data(cfg)


def test_resolve_validate_data_returns_a_copy_of_data_paths() -> None:
    cfg = load_config(nac_yaml_fixture("minimal"))
    result = resolve_validate_data(cfg)
    result.append("mutated/")
    assert cfg.data.paths == ["data/"]


# ---------------------------------------------------------------------------
# 6. resolve_test_data
# ---------------------------------------------------------------------------


def test_resolve_test_data_render_output_plus_defaults(tmp_path: Path) -> None:
    # nxos-full has render.output set but no defaults.yaml on disk; copy its
    # config into a tmp dir alongside a defaults.yaml to exercise the
    # combined "render output + data.defaults set" case.
    fixture_dir = nac_yaml_fixture("nxos-full").parent
    config_path = tmp_path / "nac.yaml"
    config_path.write_text(fixture_dir.joinpath("nac.yaml").read_text())
    (tmp_path / "defaults.yaml").write_text("{}\n")

    cfg = load_config(config_path)
    assert cfg.data.defaults == "defaults.yaml"
    assert resolve_test_data(cfg) == ["model.yaml", "defaults.yaml"]


def test_resolve_test_data_render_output_only() -> None:
    cfg = load_config(nac_yaml_fixture("iosxe-lean"))
    assert cfg.data.defaults is None
    assert resolve_test_data(cfg) == ["model.yaml"]


def test_resolve_test_data_no_render_with_defaults_detected() -> None:
    cfg = load_config(nac_yaml_fixture("aci-lean"))
    assert cfg.render is None
    assert resolve_test_data(cfg) == ["data/", "defaults.yaml"]


def test_resolve_test_data_no_render_no_defaults() -> None:
    cfg = load_config(nac_yaml_fixture("minimal"))
    assert cfg.render is None
    assert cfg.data.defaults is None
    assert resolve_test_data(cfg) == ["data/"]


def test_resolve_test_data_empty_render_and_no_defaults_is_empty(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "nac.yaml"
    config_path.write_text("render: {}\n")

    cfg = load_config(config_path)

    assert cfg.render is not None
    assert cfg.render.target is None
    assert cfg.render.output is None
    assert cfg.data.defaults is None
    assert resolve_test_data(cfg) == []


# ---------------------------------------------------------------------------
# 7. Defaulting matrix
# ---------------------------------------------------------------------------


def test_defaults_constructed_directly() -> None:
    cfg = NacConfig()

    assert cfg.validate.schema is None
    assert cfg.validate.rules is None
    assert cfg.data.paths == ["data/"]
    assert cfg.data.defaults is None
    assert cfg.render is None
    assert cfg.tools.terraform.engine is None
    assert cfg.tools.terraform.version is None
    assert cfg.tools.nac_validate is None
    assert cfg.tools.nac_test is None
    assert cfg.env.required == []
    assert cfg.working_dir == Path(".")
    assert cfg.test.templates == "tests/templates"
    assert cfg.test.filters is None
    assert cfg.test.output == "tests/results"


def test_defaults_via_minimal_fixture() -> None:
    cfg = load_config(nac_yaml_fixture("minimal"))

    assert cfg.validate.schema is None
    assert cfg.validate.rules is None
    assert cfg.data.paths == ["data/"]
    assert cfg.render is None
    assert cfg.tools.terraform.engine is None
    assert cfg.tools.terraform.version is None
    assert cfg.tools.nac_validate is None
    assert cfg.tools.nac_test is None
