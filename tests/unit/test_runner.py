# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""Unit tests for nac.runner."""

import os
import sys
import threading
import time
from pathlib import Path

import pytest

from nac.runner import run_streaming


def _echo_argv(text: str) -> list[str]:
    return [sys.executable, "-c", f"print({text!r})"]


@pytest.mark.unit
def test_streams_stdout_and_returns_exit_code(tmp_path: Path, capsys):
    code = run_streaming(_echo_argv("hello"), cwd=tmp_path, env=dict(os.environ))

    assert code == 0
    assert "hello" in capsys.readouterr().out


@pytest.mark.unit
def test_nonzero_exit_code_is_propagated(tmp_path: Path):
    argv = [sys.executable, "-c", "import sys; sys.exit(3)"]

    code = run_streaming(argv, cwd=tmp_path, env=dict(os.environ))

    assert code == 3


@pytest.mark.unit
def test_writes_output_to_log_file(tmp_path: Path):
    log_path = tmp_path / "out.log"

    run_streaming(
        _echo_argv("hello"), cwd=tmp_path, env=dict(os.environ), log_path=log_path
    )

    assert log_path.read_text().strip() == "hello"


@pytest.mark.unit
def test_log_file_parent_dirs_are_created(tmp_path: Path):
    log_path = tmp_path / "nested" / "dir" / "out.log"

    run_streaming(
        _echo_argv("hello"), cwd=tmp_path, env=dict(os.environ), log_path=log_path
    )

    assert log_path.read_text().strip() == "hello"


@pytest.mark.unit
def test_second_run_truncates_log_instead_of_appending(tmp_path: Path):
    """Regression test: a stale artifact from a prior run (e.g. `plan.json`
    from an earlier `nac plan --artifacts`) must not leak into the new
    output -- appending would produce two concatenated JSON blobs."""
    log_path = tmp_path / "plan.json"

    run_streaming(
        _echo_argv("first"), cwd=tmp_path, env=dict(os.environ), log_path=log_path
    )
    run_streaming(
        _echo_argv("second"), cwd=tmp_path, env=dict(os.environ), log_path=log_path
    )

    assert log_path.read_text().strip() == "second"


@pytest.mark.unit
def test_append_true_continues_the_same_log_within_one_invocation(tmp_path: Path):
    """A single logical invocation that makes two run_streaming calls (e.g.
    `nac validate`'s render step followed by the nac-validate call) should
    have the second call append rather than truncate, so both calls' output
    lands in one file in order."""
    log_path = tmp_path / "validate.txt"

    run_streaming(
        _echo_argv("first"), cwd=tmp_path, env=dict(os.environ), log_path=log_path
    )
    run_streaming(
        _echo_argv("second"),
        cwd=tmp_path,
        env=dict(os.environ),
        log_path=log_path,
        append=True,
    )

    assert log_path.read_text().splitlines() == ["first", "second"]


@pytest.mark.unit
def test_no_log_path_does_not_create_any_file(tmp_path: Path):
    run_streaming(_echo_argv("hello"), cwd=tmp_path, env=dict(os.environ))

    assert list(tmp_path.iterdir()) == []


@pytest.mark.unit
def test_quiet_suppresses_output_on_success(tmp_path: Path, capsys):
    code = run_streaming(
        _echo_argv("hello"), cwd=tmp_path, env=dict(os.environ), quiet=True
    )

    assert code == 0
    assert capsys.readouterr().out == ""


@pytest.mark.unit
def test_quiet_reveals_output_on_failure(tmp_path: Path, capsys):
    argv = [sys.executable, "-c", "print('boom'); import sys; sys.exit(3)"]

    code = run_streaming(argv, cwd=tmp_path, env=dict(os.environ), quiet=True)

    assert code == 3
    assert "boom" in capsys.readouterr().out


@pytest.mark.unit
def test_quiet_still_writes_full_output_to_log_file(tmp_path: Path):
    log_path = tmp_path / "out.log"

    run_streaming(
        _echo_argv("hello"),
        cwd=tmp_path,
        env=dict(os.environ),
        log_path=log_path,
        quiet=True,
    )

    assert log_path.read_text().strip() == "hello"


@pytest.mark.unit
def test_log_file_strips_ansi_codes_terminal_copy_keeps_them(tmp_path: Path, capsys):
    """A log artifact like plan.txt must stay clean text even though the
    terminal-facing copy of the same subprocess output may be colored."""
    log_path = tmp_path / "out.log"
    colored = "\033[92mhello\033[0m"
    argv = [sys.executable, "-c", f"print({colored!r})"]

    run_streaming(argv, cwd=tmp_path, env=dict(os.environ), log_path=log_path)

    assert log_path.read_text().strip() == "hello"
    assert colored in capsys.readouterr().out


@pytest.mark.unit
def test_partial_line_without_trailing_newline_is_flushed_promptly(
    tmp_path: Path, mocker
):
    """Regression test: terraform's interactive apply confirmation prints
    "Enter a value: " with no trailing newline, then waits on stdin. A
    naive `for line in proc.stdout` reader blocks in readline() until a
    newline (or EOF) shows up, so that prompt would sit invisible until
    whatever comes after the pause below -- this asserts it's flushed to
    the terminal immediately instead."""
    script = (
        "import sys, time\n"
        "sys.stdout.write('PROMPT: ')\n"
        "sys.stdout.flush()\n"
        "time.sleep(0.4)\n"
        "print('DONE')\n"
    )
    argv = [sys.executable, "-c", script]

    captured: list[str] = []
    prompt_seen = threading.Event()

    class _Capture:
        def write(self, text: str) -> None:
            captured.append(text)
            if "PROMPT" in text:
                prompt_seen.set()

        def flush(self) -> None:
            pass

    mocker.patch("nac.runner.sys.stdout", _Capture())

    thread = threading.Thread(
        target=run_streaming,
        kwargs={"cmd": argv, "cwd": tmp_path, "env": dict(os.environ)},
    )
    start = time.monotonic()
    thread.start()
    try:
        assert prompt_seen.wait(timeout=2), "prompt was never flushed"
        elapsed = time.monotonic() - start
        # The subprocess doesn't send its next newline until after a 0.4s
        # sleep -- a line-buffered reader would only surface the prompt
        # once that arrives, so a fast readback proves it isn't waiting on it.
        assert elapsed < 0.3
    finally:
        thread.join(timeout=2)
