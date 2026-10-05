[![Tests](https://github.com/netascode/nac/actions/workflows/test.yml/badge.svg)](https://github.com/netascode/nac/actions/workflows/test.yml)
![Python Support](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-informational "Python Support: 3.10, 3.11, 3.12, 3.13, 3.14")

# nac

An umbrella CLI for Network-as-Code workflows, driven by a single
`nac.yaml` config file.

## Overview

Network-as-Code repos run the same workflow regardless of architecture:
validate the data, plan, apply, test. `nac` is one CLI for all of it. Instead
of juggling `terraform`/`tofu`, `nac-validate` and `nac-test` with their own
flags, you describe the repo once in `nac.yaml` and run `nac validate`,
`nac plan`, `nac apply`, `nac test`. The same commands work on a laptop and
in CI.

## Installation

Install `nac` itself and there's nothing else to set up: it resolves and
runs the rest of the toolchain for you (via `uvx`, falling back to a local
install if one's already on `PATH`), so there's no separate
`nac-validate`/`nac-test` install or version-pinning to manage yourself.

The package is published on PyPI as **`nac-cli`**; the command it installs is
`nac`. Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
first if you don't have it, then:

```bash
uv tool install nac-cli
```

Upgrade or uninstall with:

```bash
uv tool upgrade nac-cli
uv tool uninstall nac-cli
```

Pin a specific version with `uv tool install nac-cli==0.2.0`.

> [!WARNING]
> Don't `pip install nac` or run `uvx nac` -- that is a different, unrelated
> package.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) — always
  required; `nac` uses it to run `nac-validate`/`nac-test` via `uvx`, so
  you never install those two yourself.
- `terraform` or `tofu` on `PATH` — if neither is installed, `nac setup` can
  bootstrap-install OpenTofu for you (see
  [Tool/version management](#toolversion-management)).
- [`tenv`](https://github.com/tofuutils/tenv) — only needed if you pin
  `tools.terraform.version` in `nac.yaml`.

Run `nac setup` to verify all of the above (plus any `env.required`
variables from your config) before running anything else.

## Quickstart

A `nac.yaml` at the repo root is optional — every field defaults, so an
empty or missing file is perfectly valid for a repo that sticks to the
`data/`/`tests/` conventions and needs no env vars checked. The most
common lean config just declares the environment variables the wrapped tools
expect, so `nac setup` has something to check:

```yaml
env:
  required: [ACI_URL, ACI_USERNAME, ACI_PASSWORD]
```

Then, from the repo root:

```bash
nac setup       # verify prerequisites, report resolved tool versions
nac init        # terraform/tofu init
nac validate    # nac-validate against the configured data paths
nac plan        # terraform/tofu plan -> plan.tfplan
nac apply       # apply the saved plan (or interactively, without one)
nac test        # nac-test against the configured data/templates/output
nac destroy     # destroy the managed infrastructure (interactive unless --auto-approve)
```

Every field not shown above falls back to a sensible default — see
[`nac.yaml` reference](#nacyaml-reference) below for the full set of
defaults and a worked example for repos that render a `model.yaml`
before validating (e.g. NX-OS).

## CLI reference

Global options, available on every subcommand:

| Option | Env var | Default | Description |
|---|---|---|---|
| `--config` | `NAC_CONFIG` | `./nac.yaml` | Path to the config file. |
| `-v`, `--verbosity` | `NAC_VERBOSITY` | `WARNING` | `DEBUG`\|`INFO`\|`WARNING`\|`ERROR`\|`CRITICAL`. |
| `--no-color` | `NO_COLOR` | off | Disable colored output. |

Every subcommand except `setup` forwards extra arguments to the wrapped tool
(e.g. `nac plan -var-file=prod.tfvars`), and `--help` shows `nac`'s help
followed by the wrapped tool's own options. The wrapped tool's exit code is
returned. `--artifacts`, available on the same subcommands, also writes the
command's output to `<command>.txt` in `working_dir` (e.g. `validate.txt`).

### `nac setup`

Verifies prerequisites and reports resolved tool versions — a pre-flight for
CI and local use. Checks `uv` is on `PATH`; checks `tenv` only if
`tools.terraform.version` is set; resolves the `terraform`/`tofu` binary
(explicit `tools.terraform.engine`, or auto-detected: `tofu` then
`terraform`); checks every `env.required` variable is set (never prints
values); reports resolved `terraform`/`tofu`, `nac-validate`, and `nac-test`
versions. Fails fast with a non-zero exit on any missing prerequisite.

| Flag | Description |
|---|---|
| `--yes`, `--install` | Skip the confirmation prompt for the OpenTofu bootstrap install. |
| `--prewarm` | Pre-warm the `uvx` cache for `nac-validate`/`nac-test` — skipped for a tool that already resolves to a local install. |

### `nac init`

Streams `terraform init` (or `tofu init`) in `working_dir`.

| Flag | Description |
|---|---|
| `--artifacts` | Also write the output to `init.txt`. |

### `nac validate`

If `render.target` is set, first streams a targeted
`terraform apply -target=<target> -auto-approve` to produce `render.output`,
then streams `nac-validate` against the resolved data paths (`render.output`
if a render just happened, else `data.paths`). The render step is fully
implied by config, never a separate opt-in.

| Flag | Description |
|---|---|
| `--artifacts` | Also write the output (render step included) to `validate.txt`. |

### `nac plan`

Streams `terraform plan -out=plan.tfplan`.

| Flag | Description |
|---|---|
| `--artifacts` | Also stream `terraform show` twice to emit `plan.txt` and `plan.json` alongside the saved plan. |

### `nac apply`

If a saved `plan.tfplan` exists in `working_dir`, streams
`terraform apply plan.tfplan` (and deletes the plan file after a successful
apply); otherwise runs `terraform apply` interactively (stdin is inherited,
so the normal confirmation prompt works).

| Flag | Description |
|---|---|
| `--auto-approve` | Pass `-auto-approve` when applying without a saved plan file. |
| `--artifacts` | Also write the output to `apply.txt`. |

### `nac destroy`

Streams `terraform destroy` (interactive unless `--auto-approve`, matching
`terraform destroy`'s own default confirmation prompt).

| Flag | Description |
|---|---|
| `--auto-approve` | Pass `-auto-approve` when destroying. |
| `--artifacts` | Also write the output to `destroy.txt`. |

### `nac test`

Streams `nac-test` against the resolved data paths (`render.output` if
`render` is configured, else `data.paths`, plus `data.defaults` whenever
it's configured) and the `templates`/`filters`/`output` from the `test:`
config block.

| Flag | Description |
|---|---|
| `--artifacts` | Also write the output to `test.txt`. |

## `nac.yaml` reference

A single `nac.yaml` at the repo root (path overridable with `--config`)
drives every subcommand. Every field is optional, and so is the file itself
— a missing `nac.yaml` is treated the same as an empty one, with every
field falling back to its default. That's a legitimate config for a repo
that needs no `env.required` checks and follows the `data/`/`tests/`
conventions, not just a fallback for ad hoc smoke-testing.

**Data resolution rules** (no boolean toggles anywhere — both follow
automatically from whether `render`/`render.target`/`data.defaults` are
configured):

- **validate data** = `render.output` if `render.target` is set, else
  `data.paths`.
- **test data** = (`render.output` if `render` is configured at all, else
  `data.paths`) + `data.defaults` (appended whenever it's configured).

**Field reference:**

| Field | Default | Notes |
|---|---|---|
| `working_dir` | `.` | Directory `terraform`/`tofu` runs in. |
| `data.paths` | `[data/]` | Raw data source(s) for `validate`/`test` when no render applies. |
| `data.defaults` | `defaults.yaml` if it exists in `working_dir`, else unset | Appended to `test` data whenever configured. |
| `render.target` | unset | Terraform target for a pre-validation render, e.g. `module.nxos.local_sensitive_file.model`. |
| `render.output` | unset | Rendered file path, e.g. `model.yaml`; required if `render.target` is set. |
| `validate.schema` | unset → flag omitted | Passed to `nac-validate -s`; omitted lets `nac-validate` use its own default. |
| `validate.rules` | unset → flag omitted | Passed to `nac-validate -r`; omitted lets `nac-validate` use its own default. |
| `test.templates` | `tests/templates` | Passed to `nac-test -t`. |
| `test.filters` | `tests/filters` if that directory exists in `working_dir`, else unset | Passed to `nac-test -f`. |
| `test.output` | `tests/results` | Passed to `nac-test -o`. |
| `tools.terraform.engine` | auto-detected: `tofu` if on `PATH`, else `terraform` | Explicit value always wins over detection. |
| `tools.terraform.version` | unset | Only set if you need `tenv` to pin/install a specific version. |
| `tools.nac_validate` | unset (any local install, else latest via `uvx`) | Version/spec a local install must satisfy, else passed to `uvx --from nac-validate<spec>`; e.g. `1.2.0` or `>=0.9,<1.0`. |
| `tools.nac_test` | unset (any local install, else latest via `uvx`) | Version/spec a local install must satisfy, else passed to `uvx --from nac-test<spec>`; e.g. `2.0.0` or `>=2.0,<3.0`. |
| `env.required` | `[]` | Variable names `nac setup` checks are present (values are never printed). |

**Worked examples.** Lean NX-OS (render + validate + test all use the
rendered `model.yaml`):

```yaml
tools:
  terraform:
    engine: tofu

render:
  target: module.nxos.local_sensitive_file.model
  output: model.yaml

env:
  required: [NXOS_USERNAME, NXOS_PASSWORD]
```

Lean ACI (no `render` at all; `test` appends `data.defaults` since
`defaults.yaml` exists at the repo root):

```yaml
env:
  required: [ACI_URL, ACI_USERNAME, ACI_PASSWORD]
```

Fully-expanded NX-OS config, with every field made explicit — useful when a
repo genuinely deviates from convention:

```yaml
working_dir: .

data:
  paths: [data/]
  defaults: null

render:
  target: module.nxos.local_sensitive_file.model
  output: model.yaml

validate:
  schema: .schema.yaml
  rules: [.rules]

test:
  templates: tests/templates
  filters: tests/filters
  output: tests/results

tools:
  terraform:
    engine: tofu
    version: "1.9.5"
  nac_validate: ">=0.9,<1.0"
  nac_test: ">=2.0,<3.0"

env:
  required: [NXOS_USERNAME, NXOS_PASSWORD]
```

## Tool/version management

- **`terraform`/`tofu`**: with no `tools.terraform.version` set, `nac`
  resolves the binary directly via `PATH` — `tofu` first, `terraform` as
  fallback (or whichever `tools.terraform.engine` names explicitly). If
  neither is found, `nac setup` (interactively, or with `--yes`/`--install`)
  offers to download and cache a verified OpenTofu binary itself — no
  package manager or `tenv` required. Setting `tools.terraform.version`
  switches to [`tenv`](https://github.com/tofuutils/tenv) for version
  pinning/auto-install (`TOFUENV_TOFU_VERSION`/`TFENV_TERRAFORM_VERSION` +
  the matching auto-install env var).
- **`nac-validate`/`nac-test`**: prefers a local install already on `PATH`
  if it satisfies `tools.nac_validate`/`tools.nac_test` (unset means any
  local version is acceptable) — same PATH-first philosophy as
  `terraform`/`tofu` above. Otherwise falls back to `uvx`
  (`uv tool run`) -- `uvx --from nac-validate==<version> nac-validate ...`.
  Omit `tools.nac_validate`/`tools.nac_test` to let `uvx` resolve the latest
  published release when no usable local install exists. `nac setup` reports
  which source (`local` or `uvx`) each tool actually resolved to.

## License

[MPL-2.0](LICENSE)
