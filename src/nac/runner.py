# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

import codecs
import os
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path
from typing import cast

from nac.output import strip_ansi, utf8_env

_READ_SIZE = 4096


def _write_stdout(data: bytes) -> None:
    """Pass the child's raw bytes through untouched.

    Going via the binary buffer avoids the text layer's newline translation
    (\r\n -> \r\r\n on Windows) and its locale encoding (cp1252 on Windows
    cannot encode much of what terraform/tofu print).
    """
    sys.stdout.flush()
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:  # replaced stdout without a binary layer
        sys.stdout.write(data.decode("utf-8", errors="replace"))
        sys.stdout.flush()
        return
    buffer.write(data)
    buffer.flush()


def run_streaming(
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
    log_path: Path | None = None,
    quiet: bool = False,
    append: bool = False,
) -> int:
    """Run cmd as a subprocess, streaming merged stdout+stderr in real time.

    stdin is inherited from the parent so interactive prompts (e.g.
    terraform's apply confirmation) still work. cmd[0] must already be a
    resolved path — this function does no binary resolution itself.

    Output is read in raw chunks via os.read (not line-by-line) -- a
    line-buffered `for line in proc.stdout` blocks until a newline shows
    up, so a prompt like terraform's trailing "Enter a value: " (no
    newline, then it waits on stdin) would otherwise sit unflushed and
    invisible until the next newline arrives.

    When quiet is True, output is captured instead of being streamed live;
    it is only written to stdout if the command exits non-zero, so a caller
    can pair this with its own short status line on success while still
    surfacing the real output on failure.

    Output written to log_path always has ANSI escape codes stripped --
    regardless of whether the terminal-facing copy was colored -- so log
    file artifacts (e.g. plan.txt) stay clean, human-diffable text.

    By default log_path is opened in truncate mode, so a stale artifact
    from a previous, separate invocation never leaks into new output. Pass
    append=True when this call is a continuation of an earlier
    run_streaming call within the same invocation that already truncated
    the same log_path (e.g. nac validate's render step followed by the
    nac-validate call itself), so both calls' output lands in one file in
    order. append has no effect when log_path is None.
    """
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)

    mode = "a" if append else "w"
    # newline="" keeps the child's own line endings: on Windows it already
    # emits \r\n, which default newline translation would turn into \r\r\n.
    log_cm = (
        log_path.open(mode, encoding="utf-8", newline="")
        if log_path is not None
        else nullcontext()
    )
    with log_cm as log_file:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=utf8_env(env),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=None,
            bufsize=0,
        )
        if proc.stdout is None:
            raise RuntimeError("subprocess stdout was not piped")
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        buffered: list[bytes] = []
        fd = proc.stdout.fileno()
        while True:
            raw = os.read(fd, _READ_SIZE)
            if not raw:
                break
            if quiet:
                buffered.append(raw)
            else:
                _write_stdout(raw)
            if log_file is not None:
                log_file.write(strip_ansi(decoder.decode(raw)))
        proc.wait()
    if proc.returncode is None:
        raise RuntimeError("subprocess did not report an exit code")
    if quiet and proc.returncode != 0:
        _write_stdout(b"".join(buffered))
    return cast(int, proc.returncode)
