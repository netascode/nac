[![Tests](https://github.com/netascode/nac/actions/workflows/test.yml/badge.svg)](https://github.com/netascode/nac/actions/workflows/test.yml)
![Python Support](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-informational "Python Support: 3.11, 3.12, 3.13, 3.14")

# nac

An umbrella CLI for Network-as-Code workflows, driven by a single `nac.yaml`
config file.

Every Network-as-Code repository runs the same workflow, regardless of the
architecture: validate the data model, plan, apply and test. Each step uses a
different tool with its own options: `terraform` or `tofu`, `nac-validate` and
`nac-test`. `nac` is a single CLI for the whole workflow. The repository is
described once in `nac.yaml`, and the same commands work on a laptop and in a
CI/CD pipeline:

```bash
nac setup       # verify prerequisites and report resolved tool versions
nac init        # terraform/tofu init
nac validate    # nac-validate against the configured data paths
nac plan        # terraform/tofu plan -> plan.tfplan
nac apply       # apply the saved plan (or interactively, without one)
nac test        # nac-test against the configured data/templates/output
nac destroy     # destroy the managed infrastructure
```

Full documentation: https://netascode.cisco.com/docs/tools/nac/overview

## How It Works

- **One configuration file:** `nac.yaml` defines where the data model,
  schema, rules and test templates are located, which Terraform engine to use
  and which environment variables are required. Every field has a default, so
  a repository following the `data/` and `tests/` conventions works without a
  `nac.yaml` at all.
- **Managed toolchain:** `nac-validate` and `nac-test` are used from a local
  installation if one satisfies the configured version, or run via `uvx`
  otherwise. If neither `terraform` nor `tofu` is installed, `nac setup` can
  install OpenTofu.
- **Tested versions:** a Network-as-Code Terraform module can declare the
  `nac-validate` and `nac-test` versions it was tested with in
  `nac/manifest.yaml`. `nac` then uses a compatible version by default and
  warns about versions outside of the tested range.
- **Pass-through:** arguments not known to `nac` are forwarded to the wrapped
  tool, and the exit code of the wrapped tool is returned.

## Installation

`nac` is published on PyPI as **`nac-cli`**; the command it installs is `nac`.
Install it with [uv](https://docs.astral.sh/uv/getting-started/installation/):

```bash
uv tool install nac-cli
```

> [!WARNING]
> Don't `pip install nac` or run `uvx nac` -- that is a different, unrelated
> package.

See the [installation docs](https://netascode.cisco.com/docs/tools/nac/installation/)
for prerequisites, and [usage](https://netascode.cisco.com/docs/tools/nac/usage/)
and [configuration](https://netascode.cisco.com/docs/tools/nac/configuration/)
for the full command and `nac.yaml` reference.

## License

[MPL-2.0](LICENSE)
