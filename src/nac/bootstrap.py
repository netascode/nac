# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt

import hashlib
import io
import platform
import shutil
import stat
import sys
import zipfile
from pathlib import Path
from typing import Any, cast

import httpx
import platformdirs

from nac.exceptions import (
    BootstrapDeclinedError,
    BootstrapError,
    ChecksumMismatchError,
    UnsupportedPlatformError,
)

_OS_MAP = {
    "darwin": "darwin",
    "linux": "linux",
    "win32": "windows",
    "cygwin": "windows",
}
_ARCH_MAP = {
    "x86_64": "amd64",
    "amd64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
    "i386": "386",
    "i686": "386",
    "x86": "386",
    "armv7l": "arm",
    "armv6l": "arm",
}

_GITHUB_API = "https://api.github.com/repos/opentofu/opentofu/releases"


def cache_dir() -> Path:
    return Path(platformdirs.user_cache_dir("nac"))


def _binary_name() -> str:
    return "tofu.exe" if sys.platform == "win32" else "tofu"


def _cached_binary_path(version: str) -> Path:
    return cache_dir() / "bin" / "tofu" / version / _binary_name()


def find_cached_binary() -> Path | None:
    """Return the first cached tofu binary found, or None. No network access."""
    root = cache_dir() / "bin" / "tofu"
    if not root.is_dir():
        return None
    name = _binary_name()
    for version_dir in root.iterdir():
        candidate = version_dir / name
        if candidate.is_file():
            return candidate
    return None


def detect_platform() -> tuple[str, str]:
    """Return (os_name, arch_name) in OpenTofu's release-asset vocabulary."""
    os_name = _OS_MAP.get(sys.platform)
    arch_name = _ARCH_MAP.get(platform.machine().lower())
    if os_name is None or arch_name is None:
        raise UnsupportedPlatformError(
            f"Unsupported platform for OpenTofu bootstrap: {sys.platform}/{platform.machine()}"
        )
    return os_name, arch_name


def install(
    version: str | None = None,
    *,
    confirmed: bool,
    client: httpx.Client | None = None,
) -> Path:
    """Ensure a cached OpenTofu binary exists locally and return its path.

    Never prompts — only gates on `confirmed`, which the caller (`nac
    setup`) obtains via its own TTY-detection/prompting. If a binary is
    already cached, it is returned immediately with no network call,
    regardless of `confirmed`.
    """
    cached = find_cached_binary()
    if cached is not None:
        return cached

    if not confirmed:
        raise BootstrapDeclinedError(
            "OpenTofu is not installed and installation was not confirmed."
        )

    owns_client = client is None
    client = client or httpx.Client(timeout=30.0, follow_redirects=True)
    try:
        os_name, arch_name = detect_platform()
        release = _get_release(client, version)
        resolved_version = _tag_to_version(release["tag_name"])
        dest = _cached_binary_path(resolved_version)

        asset_name = f"tofu_{resolved_version}_{os_name}_{arch_name}.zip"
        sums_name = f"tofu_{resolved_version}_SHA256SUMS"
        archive_bytes = _download(client, _asset_url(release, asset_name))
        sums_text = _download(client, _asset_url(release, sums_name)).decode()

        expected = _parse_sha256sums(sums_text, asset_name)
        actual = hashlib.sha256(archive_bytes).hexdigest()
        if actual != expected:
            raise ChecksumMismatchError(
                f"Checksum mismatch for {asset_name}: expected {expected}, got {actual}"
            )

        _extract_binary(archive_bytes, dest, os_name)
        return dest
    finally:
        if owns_client:
            client.close()


def _get_release(client: httpx.Client, version: str | None) -> dict[str, Any]:
    url = (
        f"{_GITHUB_API}/latest" if version is None else f"{_GITHUB_API}/tags/v{version}"
    )
    resp = client.get(url)
    if resp.status_code != 200:
        raise BootstrapError(
            f"Failed to query OpenTofu releases ({resp.status_code}): {url}"
        )
    result: dict[str, Any] = resp.json()
    return result


def _tag_to_version(tag: str) -> str:
    return tag[1:] if tag.startswith("v") else tag


def _asset_url(release: dict[str, Any], name: str) -> str:
    for asset in release.get("assets", []):
        if asset.get("name") == name:
            return cast(str, asset["browser_download_url"])
    raise BootstrapError(f"Release asset not found: {name}")


def _download(client: httpx.Client, url: str) -> bytes:
    resp = client.get(url)
    if resp.status_code != 200:
        raise BootstrapError(f"Download failed ({resp.status_code}): {url}")
    return resp.content


def _parse_sha256sums(text: str, filename: str) -> str:
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == filename:
            return parts[0]
    raise BootstrapError(f"No checksum entry for {filename} in SHA256SUMS")


def _extract_binary(archive_bytes: bytes, dest: Path, os_name: str) -> None:
    member = "tofu.exe" if os_name == "windows" else "tofu"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    with (
        zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf,
        zf.open(member) as src,
        tmp.open("wb") as out,
    ):
        shutil.copyfileobj(src, out)
    if os_name != "windows":
        tmp.chmod(tmp.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    tmp.replace(dest)
