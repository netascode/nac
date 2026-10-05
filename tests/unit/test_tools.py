# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""Unit tests for nac.tools."""

from typing import Any

import pytest

from nac.config import (
    DataConfig,
    NacConfig,
    TestConfig,
    ToolsConfig,
    ValidateConfig,
)
from nac.tools import (
    ToolSource,
    _local_tool_version,
    _pin_suffix,
    _satisfies,
    build_help_argv,
    build_prewarm_argv,
    build_test_argv,
    build_validate_argv,
    resolve_tool_source,
)


def make_config(**overrides: Any) -> NacConfig:
    defaults: dict[str, Any] = {}
    defaults.update(overrides)
    return NacConfig(**defaults)


@pytest.fixture(autouse=True)
def no_local_tool(mocker):
    """By default, pretend nac-validate/nac-test aren't on PATH.

    Keeps argv-building tests deterministic regardless of what's actually
    installed on the machine running the suite. Tests exercising the local
    resolution path override this explicitly.
    """
    mocker.patch("nac.tools.shutil.which", return_value=None)


@pytest.mark.unit
class TestPinSuffix:
    def test_plain_version(self):
        assert _pin_suffix("1.2.3") == "==1.2.3"

    @pytest.mark.parametrize(
        "specifier",
        ["==1.0", "!=1.0", ">=1.0", "<=1.0", "~=1.0", ">1.0", "<1.0"],
    )
    def test_specifier_prefixes_unchanged(self, specifier):
        assert _pin_suffix(specifier) == specifier

    def test_strips_whitespace(self):
        assert _pin_suffix("  1.2.3  ") == "==1.2.3"


@pytest.mark.unit
class TestLocalToolVersion:
    def test_parses_version_from_stdout(self, mocker):
        mocker.patch(
            "nac.tools.subprocess.run",
            return_value=mocker.Mock(stdout="nac-validate, version 1.2.3\n", stderr=""),
        )

        assert _local_tool_version("/usr/bin/nac-validate") == "1.2.3"

    def test_parses_version_from_stderr(self, mocker):
        mocker.patch(
            "nac.tools.subprocess.run",
            return_value=mocker.Mock(stdout="", stderr="nac-test v0.9.4"),
        )

        assert _local_tool_version("/usr/bin/nac-test") == "0.9.4"

    def test_no_version_found_returns_none(self, mocker):
        mocker.patch(
            "nac.tools.subprocess.run",
            return_value=mocker.Mock(stdout="usage: nac-test [OPTIONS]", stderr=""),
        )

        assert _local_tool_version("/usr/bin/nac-test") is None

    def test_binary_missing_returns_none(self, mocker):
        mocker.patch("nac.tools.subprocess.run", side_effect=OSError("not found"))

        assert _local_tool_version("/usr/bin/nac-test") is None


@pytest.mark.unit
class TestSatisfies:
    def test_plain_version_matches_exact(self):
        assert _satisfies("1.2.3", "1.2.3")
        assert not _satisfies("1.2.4", "1.2.3")

    def test_specifier_range(self):
        assert _satisfies("0.9.5", ">=0.9,<1.0")
        assert not _satisfies("1.0.0", ">=0.9,<1.0")

    def test_invalid_constraint_returns_false(self):
        assert not _satisfies("1.2.3", "not-a-version")

    def test_invalid_version_returns_false(self):
        assert not _satisfies("not-a-version", ">=1.0")


@pytest.mark.unit
class TestResolveToolSource:
    def test_not_found_falls_back_to_uvx(self, mocker):
        mocker.patch("nac.tools.shutil.which", return_value=None)

        source = resolve_tool_source("nac-validate", ">=1.0")

        assert source == ToolSource(mode="uvx", path=None, version=None)

    def test_found_unpinned_uses_local(self, mocker):
        mocker.patch("nac.tools.shutil.which", return_value="/usr/bin/nac-validate")
        mocker.patch("nac.tools._local_tool_version", return_value="1.2.3")

        source = resolve_tool_source("nac-validate", None)

        assert source == ToolSource(
            mode="local", path="/usr/bin/nac-validate", version="1.2.3"
        )

    def test_found_satisfies_constraint_uses_local(self, mocker):
        mocker.patch("nac.tools.shutil.which", return_value="/usr/bin/nac-validate")
        mocker.patch("nac.tools._local_tool_version", return_value="0.9.5")

        source = resolve_tool_source("nac-validate", ">=0.9,<1.0")

        assert source == ToolSource(
            mode="local", path="/usr/bin/nac-validate", version="0.9.5"
        )

    def test_found_does_not_satisfy_constraint_falls_back_to_uvx(self, mocker):
        mocker.patch("nac.tools.shutil.which", return_value="/usr/bin/nac-validate")
        mocker.patch("nac.tools._local_tool_version", return_value="1.0.0")

        source = resolve_tool_source("nac-validate", ">=0.9,<1.0")

        assert source == ToolSource(mode="uvx", path=None, version="1.0.0")

    def test_found_unparsable_version_with_constraint_falls_back_to_uvx(self, mocker):
        mocker.patch("nac.tools.shutil.which", return_value="/usr/bin/nac-validate")
        mocker.patch("nac.tools._local_tool_version", return_value=None)

        source = resolve_tool_source("nac-validate", ">=0.9,<1.0")

        assert source == ToolSource(mode="uvx", path=None, version=None)


@pytest.mark.unit
class TestBuildValidateArgv:
    def test_no_pin_when_nac_validate_none(self):
        cfg = make_config(tools=ToolsConfig(nac_validate=None))

        argv = build_validate_argv(cfg)

        assert "--from" not in argv

    def test_pin_with_existing_specifier_unchanged(self):
        cfg = make_config(tools=ToolsConfig(nac_validate=">=0.9,<1.0"))

        argv = build_validate_argv(cfg)

        idx = argv.index("--from")
        assert argv[idx + 1] == "nac-validate>=0.9,<1.0"

    def test_pin_with_plain_version(self):
        cfg = make_config(tools=ToolsConfig(nac_validate="1.2.3"))

        argv = build_validate_argv(cfg)

        idx = argv.index("--from")
        assert argv[idx + 1] == "nac-validate==1.2.3"

    def test_data_paths_positional_after_nac_validate(self):
        cfg = make_config(
            data=DataConfig(paths=["data/foo", "data/bar"]),
            render=None,
        )

        argv = build_validate_argv(cfg)

        idx = argv.index("nac-validate")
        assert argv[idx : idx + 3] == ["nac-validate", "data/foo", "data/bar"]

    def test_no_schema_flag_when_none(self):
        cfg = make_config(validate=ValidateConfig(schema=None))

        argv = build_validate_argv(cfg)

        assert "-s" not in argv

    def test_schema_flag_when_set(self):
        cfg = make_config(validate=ValidateConfig(schema="schema.yaml"))

        argv = build_validate_argv(cfg)

        idx = argv.index("-s")
        assert argv[idx + 1] == "schema.yaml"

    def test_no_rules_flags_when_none(self):
        cfg = make_config(validate=ValidateConfig(rules=None))

        argv = build_validate_argv(cfg)

        assert "-r" not in argv

    def test_rules_flags_one_per_rule_in_order(self):
        cfg = make_config(validate=ValidateConfig(rules=["r1", "r2"]))

        argv = build_validate_argv(cfg)

        r_indices = [i for i, a in enumerate(argv) if a == "-r"]
        assert len(r_indices) == 2
        assert argv[r_indices[0] + 1] == "r1"
        assert argv[r_indices[1] + 1] == "r2"

    def test_uses_local_binary_when_available(self, mocker):
        mocker.patch("nac.tools.shutil.which", return_value="/usr/bin/nac-validate")
        mocker.patch("nac.tools._local_tool_version", return_value="1.2.3")
        cfg = make_config(
            tools=ToolsConfig(nac_validate="1.2.3"),
            data=DataConfig(paths=["data/foo"]),
            render=None,
        )

        argv = build_validate_argv(cfg)

        assert argv[0] == "/usr/bin/nac-validate"
        assert "uvx" not in argv
        assert "--from" not in argv
        assert argv[1:] == ["data/foo"]


@pytest.mark.unit
class TestBuildTestArgv:
    def test_no_pin_when_nac_test_none(self):
        cfg = make_config(tools=ToolsConfig(nac_test=None))

        argv = build_test_argv(cfg)

        assert "--from" not in argv

    def test_pin_with_existing_specifier_unchanged(self):
        cfg = make_config(tools=ToolsConfig(nac_test=">=0.9,<1.0"))

        argv = build_test_argv(cfg)

        idx = argv.index("--from")
        assert argv[idx + 1] == "nac-test>=0.9,<1.0"

    def test_pin_with_plain_version(self):
        cfg = make_config(tools=ToolsConfig(nac_test="1.2.3"))

        argv = build_test_argv(cfg)

        idx = argv.index("--from")
        assert argv[idx + 1] == "nac-test==1.2.3"

    def test_each_data_path_gets_own_d_flag(self):
        cfg = make_config(
            data=DataConfig(paths=["data/"], defaults="defaults.yaml"),
            render=None,
        )

        argv = build_test_argv(cfg)

        d_indices = [i for i, a in enumerate(argv) if a == "-d"]
        assert len(d_indices) == 2
        assert argv[d_indices[0] + 1] == "data/"
        assert argv[d_indices[1] + 1] == "defaults.yaml"

    def test_templates_flag_always_present(self):
        cfg = make_config(test=TestConfig())

        argv = build_test_argv(cfg)

        idx = argv.index("-t")
        assert argv[idx + 1] == "tests/templates"

    def test_filters_flag_omitted_when_none(self):
        cfg = make_config(test=TestConfig(filters=None))

        argv = build_test_argv(cfg)

        assert "-f" not in argv

    def test_filters_flag_present_when_set(self):
        cfg = make_config(test=TestConfig(filters="tests/filters"))

        argv = build_test_argv(cfg)

        idx = argv.index("-f")
        assert argv[idx + 1] == "tests/filters"

    def test_output_flag_always_present(self):
        cfg = make_config(test=TestConfig())

        argv = build_test_argv(cfg)

        idx = argv.index("-o")
        assert argv[idx + 1] == "tests/results"

    def test_uses_local_binary_when_available(self, mocker):
        mocker.patch("nac.tools.shutil.which", return_value="/usr/bin/nac-test")
        mocker.patch("nac.tools._local_tool_version", return_value="1.2.3")
        cfg = make_config(tools=ToolsConfig(nac_test="1.2.3"), test=TestConfig())

        argv = build_test_argv(cfg)

        assert argv[0] == "/usr/bin/nac-test"
        assert "uvx" not in argv
        assert "--from" not in argv


@pytest.mark.unit
class TestBuildPrewarmArgv:
    def test_nac_validate_no_version(self):
        argv = build_prewarm_argv("nac-validate", None)

        assert argv == [
            "uv",
            "tool",
            "install",
            "--from",
            "nac-validate",
            "nac-validate",
        ]

    def test_nac_validate_with_version(self):
        argv = build_prewarm_argv("nac-validate", "1.2.3")

        assert argv == [
            "uv",
            "tool",
            "install",
            "--from",
            "nac-validate==1.2.3",
            "nac-validate",
        ]

    def test_nac_test_no_version(self):
        argv = build_prewarm_argv("nac-test", None)

        assert argv == ["uv", "tool", "install", "--from", "nac-test", "nac-test"]

    def test_nac_test_with_version(self):
        argv = build_prewarm_argv("nac-test", "1.2.3")

        assert argv == [
            "uv",
            "tool",
            "install",
            "--from",
            "nac-test==1.2.3",
            "nac-test",
        ]


@pytest.mark.unit
class TestBuildHelpArgv:
    def test_nac_validate_no_version(self):
        argv = build_help_argv("nac-validate", None)

        assert argv == ["uvx", "nac-validate", "--help"]

    def test_nac_validate_with_version(self):
        argv = build_help_argv("nac-validate", "1.2.3")

        assert argv == [
            "uvx",
            "--from",
            "nac-validate==1.2.3",
            "nac-validate",
            "--help",
        ]

    def test_nac_test_no_version(self):
        argv = build_help_argv("nac-test", None)

        assert argv == ["uvx", "nac-test", "--help"]

    def test_nac_test_with_version(self):
        argv = build_help_argv("nac-test", "1.2.3")

        assert argv == [
            "uvx",
            "--from",
            "nac-test==1.2.3",
            "nac-test",
            "--help",
        ]

    def test_uses_local_binary_when_available(self, mocker):
        mocker.patch("nac.tools.shutil.which", return_value="/usr/bin/nac-test")
        mocker.patch("nac.tools._local_tool_version", return_value="1.2.3")

        argv = build_help_argv("nac-test", "1.2.3")

        assert argv == ["/usr/bin/nac-test", "--help"]
