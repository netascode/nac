# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

"""Unit tests for nac.bootstrap."""

from __future__ import annotations

import hashlib
import io
import platform
import stat
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from nac import bootstrap
from nac.exceptions import (
    BootstrapDeclinedError,
    BootstrapError,
    ChecksumMismatchError,
    UnsupportedPlatformError,
)

_GITHUB_API = "https://api.github.com/repos/opentofu/opentofu/releases"


@dataclass
class FakeResponse:
    """A minimal stand-in for httpx.Response: .status_code, .json(), .content."""

    status_code: int
    json_data: Any = None
    content: bytes = b""

    def json(self) -> Any:
        return self.json_data


@dataclass
class FakeClient:
    """A minimal stand-in for httpx.Client: routes URLs to FakeResponses."""

    routes: dict[str, FakeResponse] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)
    closed: bool = False

    def get(self, url: str) -> FakeResponse:
        self.calls.append(url)
        if url not in self.routes:
            raise AssertionError(f"unexpected network call to {url}")
        return self.routes[url]

    def close(self) -> None:
        self.closed = True


class NoNetworkClient:
    """A client that fails the test if .get() is ever called."""

    def get(self, url: str) -> FakeResponse:
        raise AssertionError(f"unexpected network call to {url}")


def _make_zip(member_name: str, content: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(member_name, content)
    return buf.getvalue()


def _install(*, confirmed: bool, client: Any = None) -> Path:
    """Thin wrapper so test-double clients (not real httpx.Client subclasses)
    don't trip ty's nominal typing on install()'s `client` parameter."""
    return bootstrap.install(confirmed=confirmed, client=client)


def _release_for(version_tag: str, asset_name: str, sums_name: str) -> dict[str, Any]:
    return {
        "tag_name": version_tag,
        "assets": [
            {
                "name": asset_name,
                "browser_download_url": f"https://example.com/{asset_name}",
            },
            {
                "name": sums_name,
                "browser_download_url": f"https://example.com/{sums_name}",
            },
        ],
    }


# ---------------------------------------------------------------------------
# install(): cache hit
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_install_cache_hit_returns_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bootstrap, "cache_dir", lambda: tmp_path)
    version = "1.9.5"
    binary_path = tmp_path / "bin" / "tofu" / version / bootstrap._binary_name()
    binary_path.parent.mkdir(parents=True)
    binary_path.write_bytes(b"fake-binary-content")

    result = _install(confirmed=False, client=NoNetworkClient())

    assert result == binary_path
    assert result.read_bytes() == b"fake-binary-content"


# ---------------------------------------------------------------------------
# install(): not cached, confirmed=False
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_install_not_cached_not_confirmed_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bootstrap, "cache_dir", lambda: tmp_path)
    client = FakeClient()

    with pytest.raises(BootstrapDeclinedError):
        _install(confirmed=False, client=client)

    assert client.calls == []


# ---------------------------------------------------------------------------
# Shared happy-path fixture builder
# ---------------------------------------------------------------------------

# Captured at import: tests monkeypatch sys.platform to simulate other OSes.
_ON_WINDOWS = sys.platform == "win32"

_VERSION = "1.9.5"
_TAG = f"v{_VERSION}"
_BINARY_CONTENT = b"#!/bin/sh\necho fake-tofu\n"


def _build_happy_path(
    monkeypatch: pytest.MonkeyPatch, *, bad_checksum: bool = False
) -> tuple[FakeClient, str]:
    """Patch sys.platform/platform.machine to linux/amd64 and build a FakeClient
    that serves a valid (or, if bad_checksum, checksum-mismatched) release.

    Returns (client, asset_name).
    """
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")

    asset_name = f"tofu_{_VERSION}_linux_amd64.zip"
    sums_name = f"tofu_{_VERSION}_SHA256SUMS"
    release = _release_for(_TAG, asset_name, sums_name)

    archive_bytes = _make_zip("tofu", _BINARY_CONTENT)
    real_digest = hashlib.sha256(archive_bytes).hexdigest()
    digest = ("0" * 64) if bad_checksum else real_digest
    sums_text = f"{digest}  {asset_name}\n"

    client = FakeClient(
        routes={
            f"{_GITHUB_API}/latest": FakeResponse(200, json_data=release),
            f"https://example.com/{asset_name}": FakeResponse(
                200, content=archive_bytes
            ),
            f"https://example.com/{sums_name}": FakeResponse(
                200, content=sums_text.encode()
            ),
        }
    )
    return client, asset_name


# ---------------------------------------------------------------------------
# install(): not cached, confirmed=True, happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_install_happy_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bootstrap, "cache_dir", lambda: tmp_path)
    client, _ = _build_happy_path(monkeypatch)

    result = _install(confirmed=True, client=client)

    expected_dest = tmp_path / "bin" / "tofu" / _VERSION / "tofu"
    assert result == expected_dest
    assert result.exists()
    assert result.read_bytes() == _BINARY_CONTENT

    if not _ON_WINDOWS:  # Windows has no POSIX exec bits to check
        mode = result.stat().st_mode
        assert mode & stat.S_IEXEC
        assert mode & stat.S_IXGRP
        assert mode & stat.S_IXOTH


# ---------------------------------------------------------------------------
# install(): checksum mismatch
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_install_checksum_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bootstrap, "cache_dir", lambda: tmp_path)
    client, _ = _build_happy_path(monkeypatch, bad_checksum=True)

    with pytest.raises(ChecksumMismatchError):
        _install(confirmed=True, client=client)

    dest = tmp_path / "bin" / "tofu" / _VERSION / "tofu"
    assert not dest.exists()
    assert not dest.with_name(dest.name + ".part").exists()


# ---------------------------------------------------------------------------
# install(): second run hits the cache, no additional network calls
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_install_second_run_uses_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bootstrap, "cache_dir", lambda: tmp_path)
    client, _ = _build_happy_path(monkeypatch)

    first = _install(confirmed=True, client=client)
    calls_after_first = len(client.calls)
    assert calls_after_first > 0

    second = _install(confirmed=False, client=client)

    assert second == first
    assert len(client.calls) == calls_after_first


# ---------------------------------------------------------------------------
# install(): owns_client behavior
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_install_owns_client_closes_self_created_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bootstrap, "cache_dir", lambda: tmp_path)
    client, _ = _build_happy_path(monkeypatch)

    def fake_httpx_client(*args: Any, **kwargs: Any) -> FakeClient:
        return client

    monkeypatch.setattr(bootstrap.httpx, "Client", fake_httpx_client)

    result = _install(confirmed=True, client=None)

    assert result.exists()
    assert client.closed is True


@pytest.mark.unit
def test_install_does_not_close_caller_provided_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bootstrap, "cache_dir", lambda: tmp_path)
    client, _ = _build_happy_path(monkeypatch)

    result = _install(confirmed=True, client=client)

    assert result.exists()
    assert client.closed is False


# ---------------------------------------------------------------------------
# detect_platform()
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("sys_platform", "machine", "expected"),
    [
        ("darwin", "x86_64", ("darwin", "amd64")),
        ("linux", "aarch64", ("linux", "arm64")),
        ("win32", "AMD64", ("windows", "amd64")),
    ],
)
def test_detect_platform_known_combinations(
    monkeypatch: pytest.MonkeyPatch,
    sys_platform: str,
    machine: str,
    expected: tuple[str, str],
) -> None:
    monkeypatch.setattr(sys, "platform", sys_platform)
    monkeypatch.setattr(platform, "machine", lambda: machine)

    assert bootstrap.detect_platform() == expected


@pytest.mark.unit
def test_detect_platform_unsupported_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(platform, "machine", lambda: "sparc64")

    with pytest.raises(UnsupportedPlatformError):
        bootstrap.detect_platform()


# ---------------------------------------------------------------------------
# _parse_sha256sums()
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_sha256sums_plain_line() -> None:
    text = "deadbeef  tofu_1.9.5_linux_amd64.zip\n"

    result = bootstrap._parse_sha256sums(text, "tofu_1.9.5_linux_amd64.zip")

    assert result == "deadbeef"


@pytest.mark.unit
def test_parse_sha256sums_binary_mode_prefix() -> None:
    text = "cafef00d *tofu_1.9.5_linux_amd64.zip\n"

    result = bootstrap._parse_sha256sums(text, "tofu_1.9.5_linux_amd64.zip")

    assert result == "cafef00d"


@pytest.mark.unit
def test_parse_sha256sums_no_match_raises() -> None:
    text = "deadbeef  some_other_file.zip\n"

    with pytest.raises(BootstrapError):
        bootstrap._parse_sha256sums(text, "tofu_1.9.5_linux_amd64.zip")


# ---------------------------------------------------------------------------
# _tag_to_version()
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_tag_to_version_strips_leading_v() -> None:
    assert bootstrap._tag_to_version("v1.9.5") == "1.9.5"


@pytest.mark.unit
def test_tag_to_version_unchanged_without_leading_v() -> None:
    assert bootstrap._tag_to_version("1.9.5") == "1.9.5"


# ---------------------------------------------------------------------------
# _asset_url()
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_asset_url_missing_asset_raises() -> None:
    release = _release_for("v1.9.5", "tofu_1.9.5_linux_amd64.zip", "SHA256SUMS")

    with pytest.raises(BootstrapError):
        bootstrap._asset_url(release, "does_not_exist.zip")


# ---------------------------------------------------------------------------
# _get_release() / _download(): non-200 responses
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_release_non_200_raises() -> None:
    client = FakeClient(
        routes={f"{_GITHUB_API}/latest": FakeResponse(404, json_data={})}
    )

    with pytest.raises(BootstrapError):
        bootstrap._get_release(client, None)  # ty: ignore[invalid-argument-type]


@pytest.mark.unit
def test_download_non_200_raises() -> None:
    url = "https://example.com/asset.zip"
    client = FakeClient(routes={url: FakeResponse(500, content=b"")})

    with pytest.raises(BootstrapError):
        bootstrap._download(client, url)  # ty: ignore[invalid-argument-type]
