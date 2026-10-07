# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""Integration tests: real `nac init`/`plan`/`apply` against a trivial local-only
Terraform/OpenTofu fixture, verifying streamed output and exit code propagation.

These tests shell out to a real `tofu`/`terraform` binary and perform a real
(local-only, no cloud credentials) provider init/plan/apply, so they are
slower than the unit suite and are excluded from the default run via the
`integration` marker.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        shutil.which("tofu") is None and shutil.which("terraform") is None,
        reason="requires tofu or terraform on PATH",
    ),
]

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "local_only"

# The fixture's time_sleep resource sleeps for this long during apply.
SLEEP_DURATION_S = 3.0

# A fixed (not per-test-tmp_path) provider plugin cache dir, shared across
# test runs on the same machine. Combined with the fixture's committed
# .terraform.lock.hcl, this turns `tofu/terraform init` from a ~3s network
# round-trip into a local cache hit after the first run.
PLUGIN_CACHE_DIR = Path(tempfile.gettempdir()) / "nac-pytest-tf-plugin-cache"


def _tf_env() -> dict[str, str]:
    PLUGIN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return {**os.environ, "TF_PLUGIN_CACHE_DIR": str(PLUGIN_CACHE_DIR)}


def _detect_engine() -> str:
    """Prefer tofu, falling back to terraform, matching nac's own default."""
    if shutil.which("tofu") is not None:
        return "tofu"
    return "terraform"


def _write_nac_yaml(tmp_path: Path, engine: str) -> Path:
    cfg_path = tmp_path / "nac.yaml"
    cfg_path.write_text(
        f"working_dir: .\ntools:\n  terraform:\n    engine: {engine}\n",
        encoding="utf-8",
    )
    return cfg_path


def _run_nac(cfg_path: Path, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a `nac` subcommand as a real subprocess and wait for completion."""
    return subprocess.run(
        [sys.executable, "-m", "nac", "--config", str(cfg_path), *args],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=_tf_env(),
        check=False,
    )


def test_init_plan_apply_streams_output_in_real_time(tmp_path: Path) -> None:
    """`nac init` -> `nac plan` -> `nac apply` against a local-only fixture.

    Asserts each step exits 0, and that `apply`'s output is streamed
    incrementally (the first line arrives well before the 3s time_sleep
    resource finishes) rather than being buffered until process exit.
    """
    shutil.copytree(FIXTURES_DIR, tmp_path, dirs_exist_ok=True)
    # Don't let the broken/ subfixture confuse this working directory.
    shutil.rmtree(tmp_path / "broken", ignore_errors=True)

    engine = _detect_engine()
    cfg_path = _write_nac_yaml(tmp_path, engine)

    init_proc = _run_nac(cfg_path, tmp_path, "init")
    assert init_proc.returncode == 0, init_proc.stdout

    plan_proc = _run_nac(cfg_path, tmp_path, "plan")
    assert plan_proc.returncode == 0, plan_proc.stdout

    t_start = time.monotonic()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "nac",
            "--config",
            str(cfg_path),
            "apply",
            "--auto-approve",
        ],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=None,
        text=True,
        bufsize=1,
        env=_tf_env(),
    )
    assert proc.stdout is not None

    lines: list[str] = []
    line_timestamps: list[float] = []
    for line in proc.stdout:
        line_timestamps.append(time.monotonic())
        lines.append(line)
    proc.wait()
    t_end = time.monotonic()

    output = "".join(lines)
    assert proc.returncode == 0, output
    assert line_timestamps, "expected at least one line of streamed apply output"

    t_first = line_timestamps[0]
    total_duration = t_end - t_start

    # The first line of output (e.g. "Initializing..."/plan header) should
    # arrive well before the process exits (the 3s time_sleep resource is
    # still running), proving output is streamed incrementally rather than
    # buffered until exit. Measured relative to process exit rather than to
    # launch so slow interpreter/engine startup (e.g. Windows CI runners,
    # where it can exceed 1.5s) can't cause false failures; if output were
    # buffered, every line would arrive at ~t_end and this gap would be ~0.
    first_line_lead = t_end - t_first
    assert first_line_lead > SLEEP_DURATION_S / 2, (
        f"first streamed line arrived only {first_line_lead:.2f}s before the process "
        f"exited, expected more than {SLEEP_DURATION_S / 2:.2f}s"
    )

    # The overall apply should take roughly as long as the time_sleep
    # resource itself (a tolerant >= check to avoid CI flakiness -- SPEC.md's
    # own prototype observed ~3.13s for a 3s resource).
    assert total_duration >= SLEEP_DURATION_S - 0.5, (
        f"apply completed in {total_duration:.2f}s, "
        f"expected at least ~{SLEEP_DURATION_S - 0.5:.2f}s"
    )

    output_file = tmp_path / "output.txt"
    assert output_file.is_file()
    assert "hello from nac integration test" in output_file.read_text(encoding="utf-8")


def test_init_propagates_nonzero_exit_code_on_broken_hcl(tmp_path: Path) -> None:
    """A broken Terraform fixture makes `nac init` fail with a non-zero code
    that matches the underlying tofu/terraform child process's own exit code
    (proving the failure isn't swallowed or remapped)."""
    broken_fixture = FIXTURES_DIR / "broken"
    shutil.copytree(broken_fixture, tmp_path, dirs_exist_ok=True)

    engine = _detect_engine()
    cfg_path = _write_nac_yaml(tmp_path, engine)

    nac_proc = _run_nac(cfg_path, tmp_path, "init")
    assert nac_proc.returncode != 0, nac_proc.stdout

    # Cross-check: running the raw engine binary directly in the same
    # directory should fail with the exact same exit code nac propagated.
    raw_proc = subprocess.run(
        [engine, "init", "-no-color"],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=_tf_env(),
        check=False,
    )
    assert raw_proc.returncode != 0
    assert nac_proc.returncode == raw_proc.returncode
