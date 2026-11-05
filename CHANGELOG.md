## Unreleased

- Only require `uv` when `nac-validate`/`nac-test` aren't installed locally in a satisfying version: `nac setup` no longer fails without `uv` if both tools resolve locally, and `nac validate`/`nac test` fail with a clear message (instead of a missing-executable error) when `uvx` would be needed but `uv` isn't on `PATH`
- Enable `nac-validate`'s and `nac-test`'s `--artifacts` option (schema, rules and test templates packaged with the module or with bundles) by default via `NAC_VALIDATE_ARTIFACTS`/`NAC_TEST_ARTIFACTS`; versions without the option ignore it, and an existing value of the env var or a passed-through `--no-artifacts` takes precedence

## 0.1.0

- Initial release
