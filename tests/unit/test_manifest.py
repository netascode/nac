# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""Unit tests for nac.manifest."""

import logging

import pytest

from nac.manifest import (
    Manifest,
    classify,
    compatible_range,
    load_manifest,
)


@pytest.mark.unit
class TestCompatibleRange:
    def test_major_version_allows_up_to_next_major(self):
        assert compatible_range("2.0.0") == ">=2.0.0,<3"

    def test_zero_major_allows_up_to_next_minor(self):
        assert compatible_range("0.13.1") == ">=0.13.1,<0.14"

    def test_prerelease_is_kept(self):
        assert compatible_range("2.0.0b2") == ">=2.0.0b2,<3"

    def test_invalid_version_returns_none(self):
        assert compatible_range("latest") is None


@pytest.mark.unit
class TestClassify:
    @pytest.mark.parametrize(
        ("actual", "tested", "expected"),
        [
            ("2.0.0", "2.0.0", "tested"),
            ("2.3.1", "2.0.0", "compatible"),
            ("3.0.0", "2.0.0", "untested"),
            ("1.9.0", "2.0.0", "untested"),
            ("0.13.4", "0.13.1", "compatible"),
            ("0.14.0", "0.13.1", "untested"),
            ("1.12.0-beta1", "1.12.1", "untested"),
        ],
    )
    def test_classification(self, actual, tested, expected):
        assert classify(actual, tested) == expected

    def test_invalid_versions_return_none(self):
        assert classify("unknown", "2.0.0") is None
        assert classify("2.0.0", "unknown") is None


@pytest.mark.unit
class TestManifestChecks:
    manifest = Manifest(
        module="netascode/nac-nxos/nxos 0.3.0",
        tools={"nac-validate": "2.0.0"},
    )

    def test_untested_tool_warns_with_context(self):
        warning = self.manifest.check_tool("nac-validate", "1.2.0")

        assert warning == (
            "nac-validate 1.2.0 is outside the range tested with "
            "netascode/nac-nxos/nxos 0.3.0 (tested: 2.0.0, compatible: >=2.0.0,<3)"
        )

    def test_compatible_tool_only_logs_info(self, caplog):
        with caplog.at_level(logging.INFO, logger="nac.manifest"):
            assert self.manifest.check_tool("nac-validate", "2.1.0") is None

        assert "semver-compatible" in caplog.text

    def test_tested_tool_is_silent(self, caplog):
        with caplog.at_level(logging.INFO, logger="nac.manifest"):
            assert self.manifest.check_tool("nac-validate", "2.0.0") is None

        assert caplog.text == ""

    def test_unknown_tool_or_version_is_silent(self):
        assert self.manifest.check_tool("nac-test", "0.1.0") is None
        assert self.manifest.check_tool("nac-validate", None) is None


@pytest.mark.unit
class TestLoadManifest:
    def test_loads_manifest_of_initialized_module(self, tmp_path, write_module):
        write_module(tmp_path)

        manifest = load_manifest(tmp_path)

        assert manifest is not None
        assert manifest.module == "netascode/nac-nxos/nxos 0.3.0"
        assert manifest.tools == {"nac-validate": "2.0.0", "nac-test": "2.0.0"}

    def test_manifest_at_module_root_is_ignored(self, tmp_path, write_module):
        module_dir = write_module(tmp_path, manifest=None)
        (module_dir / "nac-manifest.yaml").write_text(
            "schema: 1\ntools: {nac-test: 2.0.0}\n"
        )

        assert load_manifest(tmp_path) is None

    def test_not_initialized_returns_none(self, tmp_path):
        assert load_manifest(tmp_path) is None

    def test_module_without_manifest_returns_none(self, tmp_path, write_module):
        write_module(tmp_path, manifest=None)

        assert load_manifest(tmp_path) is None

    @pytest.mark.parametrize(
        "content",
        [
            "tools: {nac-test: 2.0.0}\n",  # schema missing
            "schema: 99\ntools: {}\n",  # unsupported schema
            "schema: 1\ntools: [nac-test]\n",  # wrong type
            "schema: [1\n",  # malformed YAML
        ],
    )
    def test_invalid_manifest_returns_none(self, tmp_path, write_module, content):
        write_module(tmp_path, manifest=content)

        assert load_manifest(tmp_path) is None

    def test_malformed_modules_json_returns_none(self, tmp_path):
        modules_dir = tmp_path / ".terraform" / "modules"
        modules_dir.mkdir(parents=True)
        (modules_dir / "modules.json").write_text("not json")

        assert load_manifest(tmp_path) is None

    def test_unknown_keys_are_ignored(self, tmp_path, write_module):
        write_module(
            tmp_path,
            manifest="schema: 1\nplatform: {nxos: '10.5(4)'}\ntools: {nac-test: 2.0.0}\n",
        )

        manifest = load_manifest(tmp_path)

        assert manifest is not None
        assert manifest.tools == {"nac-test": "2.0.0"}

    def test_unquoted_numeric_versions_are_coerced(self, tmp_path, write_module):
        write_module(tmp_path, manifest="schema: 1\ntools: {nac-test: 2.0}\n")

        manifest = load_manifest(tmp_path)

        assert manifest is not None
        assert manifest.tools == {"nac-test": "2.0"}

    def test_prefers_shallowest_module(self, tmp_path, write_module):
        write_module(
            tmp_path,
            manifest="schema: 1\ntools: {nac-test: 9.0.0}\n",
            key="wrapper.nxos",
        )
        write_module(
            tmp_path,
            manifest="schema: 1\ntools: {nac-test: 2.0.0}\n",
            key="nxos",
        )

        manifest = load_manifest(tmp_path)

        assert manifest is not None
        assert manifest.tools == {"nac-test": "2.0.0"}

    def test_nested_module_found_behind_local_wrapper(self, tmp_path, write_module):
        write_module(tmp_path, manifest=None, key="wrapper", source="./wrapper")
        write_module(tmp_path, key="wrapper.nxos")

        manifest = load_manifest(tmp_path)

        assert manifest is not None
        assert manifest.module == "netascode/nac-nxos/nxos 0.3.0"

    def test_non_registry_source_labelled_by_module_key(self, tmp_path, write_module):
        write_module(
            tmp_path,
            source="git::https://github.com/netascode/terraform-nxos-nac-nxos.git",
            version="",
        )

        manifest = load_manifest(tmp_path)

        assert manifest is not None
        assert manifest.module == "module.nxos"
