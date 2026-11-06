## 0.2.1

- Read `nac.yaml` defaults from a `config` section in the module's `nac/manifest.yaml`: `render.resource` (relative to the module, e.g. `local_sensitive_file.model` becomes `module.nxos.local_sensitive_file.model`), `render.output` and `env.required`. Settings in the project's `nac.yaml` take precedence key by key, an explicit `null` turns a default off, and an invalid `config` section is ignored with a warning; `nac setup` lists the defaults taken from the module
- Fail `nac validate` with a clear message if the render step didn't write `render.output` (e.g. because it doesn't match the module's `write_model_file`), and show the output path in the Render Summary

## 0.2.0

- Only require `uv` when `nac-validate`/`nac-test` aren't installed locally in a satisfying version: `nac setup` no longer fails without `uv` if both tools resolve locally, and `nac validate`/`nac test` fail with a clear message (instead of a missing-executable error) when `uvx` would be needed but `uv` isn't on `PATH`
- Enable `nac-validate`'s and `nac-test`'s `--artifacts` option (schema, rules and test templates packaged with the module or with bundles) by default via `NAC_VALIDATE_ARTIFACTS`/`NAC_TEST_ARTIFACTS`; versions without the option ignore it, and an existing value of the env var or a passed-through `--no-artifacts` takes precedence

## 0.1.0

- Initial release
