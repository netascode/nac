# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""Unit tests for nac.terraform."""

import pytest

from nac.config import TerraformToolConfig
from nac.exceptions import EngineNotFoundError, NoEngineAvailableError
from nac.terraform import (
    DEFAULT_PLAN_FILE,
    TERRAFORM_AUTO_INSTALL_ENV,
    TERRAFORM_VERSION_ENV,
    TOFU_AUTO_INSTALL_ENV,
    TOFU_VERSION_ENV,
    build_apply_argv,
    build_destroy_argv,
    build_engine_env,
    build_init_argv,
    build_plan_argv,
    build_render_apply_argv,
    build_show_json_argv,
    build_show_text_argv,
    resolve_engine_binary,
)


@pytest.mark.unit
class TestResolveEngineBinary:
    def test_explicit_engine_found(self, mocker):
        mocker.patch(
            "nac.terraform.shutil.which",
            side_effect=lambda name: "/usr/bin/tofu" if name == "tofu" else None,
        )
        cfg = TerraformToolConfig(engine="tofu")

        engine, path = resolve_engine_binary(cfg)

        assert engine == "tofu"
        assert path == "/usr/bin/tofu"

    def test_explicit_engine_not_found(self, mocker):
        mocker.patch("nac.terraform.shutil.which", return_value=None)
        cfg = TerraformToolConfig(engine="terraform")

        with pytest.raises(EngineNotFoundError, match="terraform"):
            resolve_engine_binary(cfg)

    def test_explicit_engine_no_fallback(self, mocker):
        mocker.patch(
            "nac.terraform.shutil.which",
            side_effect=lambda name: (
                "/usr/bin/terraform" if name == "terraform" else None
            ),
        )
        cfg = TerraformToolConfig(engine="tofu")

        with pytest.raises(EngineNotFoundError, match="tofu"):
            resolve_engine_binary(cfg)

    def test_none_prefers_tofu(self, mocker):
        mocker.patch(
            "nac.terraform.shutil.which",
            side_effect=lambda name: f"/usr/bin/{name}",
        )
        cfg = TerraformToolConfig(engine=None)

        engine, path = resolve_engine_binary(cfg)

        assert engine == "tofu"
        assert path == "/usr/bin/tofu"

    def test_none_falls_back_to_terraform(self, mocker):
        mocker.patch(
            "nac.terraform.shutil.which",
            side_effect=lambda name: (
                "/usr/bin/terraform" if name == "terraform" else None
            ),
        )
        cfg = TerraformToolConfig(engine=None)

        engine, path = resolve_engine_binary(cfg)

        assert engine == "terraform"
        assert path == "/usr/bin/terraform"

    def test_none_neither_available(self, mocker):
        mocker.patch("nac.terraform.shutil.which", return_value=None)
        mocker.patch("nac.terraform.bootstrap.find_cached_binary", return_value=None)
        cfg = TerraformToolConfig(engine=None)

        with pytest.raises(NoEngineAvailableError):
            resolve_engine_binary(cfg)

    def test_none_neither_on_path_falls_back_to_bootstrap_cache(self, mocker, tmp_path):
        """FR-12: a previously bootstrap-installed tofu is reused without
        re-prompting, even though it's never on PATH."""
        mocker.patch("nac.terraform.shutil.which", return_value=None)
        cached_path = tmp_path / "bin" / "tofu" / "1.9.5" / "tofu"
        mocker.patch(
            "nac.terraform.bootstrap.find_cached_binary", return_value=cached_path
        )
        cfg = TerraformToolConfig(engine=None)

        engine, path = resolve_engine_binary(cfg)

        assert engine == "tofu"
        assert path == str(cached_path)

    def test_explicit_engine_never_consults_bootstrap_cache(self, mocker, tmp_path):
        """An explicit engine is a hard requirement -- no bootstrap fallback."""
        mocker.patch("nac.terraform.shutil.which", return_value=None)
        find_cached_mock = mocker.patch(
            "nac.terraform.bootstrap.find_cached_binary",
            return_value=tmp_path / "tofu",
        )
        cfg = TerraformToolConfig(engine="terraform")

        with pytest.raises(EngineNotFoundError):
            resolve_engine_binary(cfg)

        find_cached_mock.assert_not_called()


@pytest.mark.unit
class TestBuildEngineEnv:
    def test_no_version_no_extra_keys(self):
        base = {"PATH": "/usr/bin"}

        env = build_engine_env("tofu", None, base_env=base)

        assert TOFU_VERSION_ENV not in env
        assert TOFU_AUTO_INSTALL_ENV not in env
        assert TERRAFORM_VERSION_ENV not in env
        assert TERRAFORM_AUTO_INSTALL_ENV not in env

    def test_version_tofu(self):
        env = build_engine_env("tofu", "1.7.0", base_env={})

        assert env[TOFU_VERSION_ENV] == "1.7.0"
        assert env[TOFU_AUTO_INSTALL_ENV] == "true"

    def test_version_terraform(self):
        env = build_engine_env("terraform", "1.9.0", base_env={})

        assert env[TERRAFORM_VERSION_ENV] == "1.9.0"
        assert env[TERRAFORM_AUTO_INSTALL_ENV] == "true"

    def test_version_unrecognized_engine(self):
        env = build_engine_env("bogus", "1.0.0", base_env={})

        assert TOFU_VERSION_ENV not in env
        assert TOFU_AUTO_INSTALL_ENV not in env
        assert TERRAFORM_VERSION_ENV not in env
        assert TERRAFORM_AUTO_INSTALL_ENV not in env

    def test_returns_new_dict_does_not_mutate_base(self):
        base_env = {"FOO": "bar"}

        result = build_engine_env("tofu", "1.7.0", base_env=base_env)
        result["MUTATED"] = "yes"

        assert base_env == {"FOO": "bar"}
        assert "MUTATED" not in base_env

    def test_base_env_none_copies_os_environ(self, monkeypatch):
        monkeypatch.setenv("NAC_TEST_MARKER", "marker-value")

        env = build_engine_env("tofu", None, base_env=None)

        assert env["NAC_TEST_MARKER"] == "marker-value"


@pytest.mark.unit
class TestArgvBuilders:
    def test_build_init_argv(self):
        assert build_init_argv("tofu") == ["tofu", "init"]

    def test_build_init_argv_no_color(self):
        assert build_init_argv("tofu", no_color=True) == ["tofu", "init", "-no-color"]

    def test_build_render_apply_argv(self):
        assert build_render_apply_argv("tofu", "module.foo") == [
            "tofu",
            "apply",
            "-target=module.foo",
            "-auto-approve",
        ]

    def test_build_render_apply_argv_no_color(self):
        assert build_render_apply_argv("tofu", "module.foo", no_color=True) == [
            "tofu",
            "apply",
            "-target=module.foo",
            "-auto-approve",
            "-no-color",
        ]

    def test_build_plan_argv_default(self):
        assert build_plan_argv("tofu") == [
            "tofu",
            "plan",
            f"-out={DEFAULT_PLAN_FILE}",
        ]

    def test_build_plan_argv_no_color(self):
        assert build_plan_argv("tofu", no_color=True) == [
            "tofu",
            "plan",
            f"-out={DEFAULT_PLAN_FILE}",
            "-no-color",
        ]

    def test_build_plan_argv_custom_out_file(self):
        assert build_plan_argv("tofu", out_file="custom.tfplan") == [
            "tofu",
            "plan",
            "-out=custom.tfplan",
        ]

    def test_build_show_text_argv_default(self):
        assert build_show_text_argv("tofu") == [
            "tofu",
            "show",
            DEFAULT_PLAN_FILE,
        ]

    def test_build_show_text_argv_no_color(self):
        assert build_show_text_argv("tofu", no_color=True) == [
            "tofu",
            "show",
            "-no-color",
            DEFAULT_PLAN_FILE,
        ]

    def test_build_show_text_argv_custom_plan_file(self):
        assert build_show_text_argv("tofu", plan_file="custom.tfplan") == [
            "tofu",
            "show",
            "custom.tfplan",
        ]

    def test_build_show_json_argv_default(self):
        assert build_show_json_argv("tofu") == [
            "tofu",
            "show",
            "-json",
            DEFAULT_PLAN_FILE,
        ]

    def test_build_show_json_argv_custom_plan_file(self):
        assert build_show_json_argv("tofu", plan_file="custom.tfplan") == [
            "tofu",
            "show",
            "-json",
            "custom.tfplan",
        ]


@pytest.mark.unit
class TestBuildApplyArgv:
    def test_plan_file_with_auto_approve_ignores_auto_approve(self):
        argv = build_apply_argv("tofu", plan_file="plan.tfplan", auto_approve=True)

        assert argv == ["tofu", "apply", "plan.tfplan"]

    def test_no_plan_file_auto_approve_true(self):
        argv = build_apply_argv("tofu", plan_file=None, auto_approve=True)

        assert argv == ["tofu", "apply", "-auto-approve"]

    def test_no_plan_file_auto_approve_false(self):
        argv = build_apply_argv("tofu", plan_file=None, auto_approve=False)

        assert argv == ["tofu", "apply"]

    def test_no_color_true_is_forwarded_before_plan_file(self):
        argv = build_apply_argv(
            "tofu", plan_file="plan.tfplan", auto_approve=True, no_color=True
        )

        assert argv == ["tofu", "apply", "-no-color", "plan.tfplan"]

    def test_no_color_true_is_forwarded_before_auto_approve(self):
        argv = build_apply_argv(
            "tofu", plan_file=None, auto_approve=True, no_color=True
        )

        assert argv == ["tofu", "apply", "-no-color", "-auto-approve"]


@pytest.mark.unit
class TestBuildDestroyArgv:
    def test_defaults(self):
        assert build_destroy_argv("tofu") == ["tofu", "destroy"]

    def test_auto_approve(self):
        assert build_destroy_argv("tofu", auto_approve=True) == [
            "tofu",
            "destroy",
            "-auto-approve",
        ]

    def test_no_color(self):
        assert build_destroy_argv("tofu", no_color=True) == [
            "tofu",
            "destroy",
            "-no-color",
        ]

    def test_no_color_forwarded_before_auto_approve(self):
        argv = build_destroy_argv("tofu", auto_approve=True, no_color=True)

        assert argv == ["tofu", "destroy", "-no-color", "-auto-approve"]
