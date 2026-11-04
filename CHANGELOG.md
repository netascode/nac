## Unreleased

- Enable `nac-validate`'s and `nac-test`'s `--artifacts` option (schema, rules and test templates packaged with the module or with bundles) by default via `NAC_VALIDATE_ARTIFACTS`/`NAC_TEST_ARTIFACTS`; versions without the option ignore it, and an existing value of the env var or a passed-through `--no-artifacts` takes precedence

## 0.1.0

- Initial release
