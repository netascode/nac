# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""Unit tests for nac.output."""

import pytest

from nac.output import (
    DIM,
    GREEN,
    apply_no_color_env,
    color,
    echo_command,
    echo_summary,
    format_command,
    strip_ansi,
)


@pytest.mark.unit
class TestColor:
    def test_wraps_text_in_ansi_codes_by_default(self):
        assert color(GREEN, "OK") == f"{GREEN}OK\033[0m"

    def test_no_color_true_returns_plain_text(self):
        assert color(GREEN, "OK", no_color=True) == "OK"


@pytest.mark.unit
class TestEchoSummary:
    def test_default_output_contains_title_and_checkmarked_line(self, capsys):
        echo_summary("Title", ["ok"])

        out = capsys.readouterr().out
        assert "Title" in out
        assert "✓ ok" in out

    def test_no_color_true_omits_ansi_codes(self, capsys):
        echo_summary("Title", ["ok"], no_color=True)

        out = capsys.readouterr().out
        assert "\033[" not in out
        assert "Title" in out
        assert "✓ ok" in out


@pytest.mark.unit
class TestStripAnsi:
    def test_removes_sgr_color_codes(self):
        assert strip_ansi("\033[92mOK\033[0m") == "OK"

    def test_plain_text_is_unchanged(self):
        assert strip_ansi("plain text") == "plain text"

    def test_multiple_codes_in_one_line(self):
        assert strip_ansi("\033[1m\033[92m✓\033[0m OK") == "✓ OK"


@pytest.mark.unit
class TestApplyNoColorEnv:
    def test_no_color_false_leaves_env_untouched(self):
        base = {"FOO": "bar"}

        env = apply_no_color_env(False, base_env=base)

        assert env == {"FOO": "bar"}
        assert "NO_COLOR" not in env

    def test_no_color_true_adds_no_color_var(self):
        base = {"FOO": "bar"}

        env = apply_no_color_env(True, base_env=base)

        assert env["NO_COLOR"] == "1"
        assert env["FOO"] == "bar"

    def test_does_not_mutate_base_env(self):
        base = {"FOO": "bar"}

        apply_no_color_env(True, base_env=base)

        assert "NO_COLOR" not in base


@pytest.mark.unit
class TestFormatCommand:
    def test_posix_quotes_arguments_with_spaces(self, mocker):
        mocker.patch("nac.output.sys.platform", "linux")

        assert format_command(["tofu", "plan", "-var=a b"]) == "tofu plan '-var=a b'"

    def test_windows_uses_cmd_quoting(self, mocker):
        mocker.patch("nac.output.sys.platform", "win32")

        assert format_command(["tofu.exe", "plan", "-var=a b"]) == (
            'tofu.exe plan "-var=a b"'
        )


@pytest.mark.unit
class TestEchoCommand:
    def test_prints_dim_dollar_line_to_stderr(self, mocker):
        echo = mocker.patch("nac.output.typer.echo")

        echo_command(["tofu", "plan"])

        echo.assert_called_once_with(color(DIM, "$ tofu plan"), err=True)

    def test_nothing_goes_to_stdout(self, capsys):
        echo_command(["tofu", "plan"])

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == "$ tofu plan\n"

    def test_no_color_true_omits_ansi_codes(self, capsys):
        echo_command(["tofu", "plan"], no_color=True)

        assert capsys.readouterr().err == "$ tofu plan\n"
