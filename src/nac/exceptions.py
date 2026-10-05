# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Daniel Schmidt


class NacError(Exception):
    """Base class for all nac errors."""


class ConfigError(NacError):
    """Missing, malformed, or invalid nac.yaml."""


class EngineNotFoundError(NacError):
    """An explicitly-configured tools.terraform.engine binary is not on PATH."""


class NoEngineAvailableError(NacError):
    """Neither tofu nor terraform was found on PATH and no engine was configured."""


class BootstrapError(NacError):
    """Base class for OpenTofu zero-config bootstrap failures."""


class UnsupportedPlatformError(BootstrapError):
    """The current OS/architecture has no matching OpenTofu release asset."""


class BootstrapDeclinedError(BootstrapError):
    """Installation was not confirmed and no binary is already cached."""


class ChecksumMismatchError(BootstrapError):
    """The downloaded archive's SHA-256 didn't match the published checksum."""
