# dci-pipeline Best Practices

## Goal: maximize reusability of job definitions

The overarching goal of these practices is to make pipeline job
definitions as reusable as possible across labs, resources and git
repositories. A job definition should describe *what* to run, not *where*
it happens to live, so the same file can be shared unchanged between
environments.

To achieve this, the recommended layout on the jumphost machine (the host
running dci-pipeline) is to store the pipelines repository and any other
git repositories under `~/dci`:

```text
~/dci/lab-config/
├── pipelines/         # git repo holding the *-pipeline.yml files
├── inventories/       # inventory files, stored independently
└── ...                # other git repos (configs, hooks, etc.)
```

Two conventions make this work:

- **Relative inventory paths.** Inventories are referenced relatively and
  resolved via the `INVENTORIES_DIRS` configuration variable, so they can
  be stored independently of the pipeline files (in their own repository
  or directory) and remain lab-specific while the pipeline files stay
  generic. See [Inventory Path Resolution](README.md#inventory-path-resolution).
- **Common naming conventions.** Inventory paths follow patterns keyed on
  the type of job — `@QUEUE/@RESOURCE` for `dci-openshift-agent` jobs and
  `@QUEUE/@RESOURCE-installed` for `dci-openshift-app-agent` jobs — and job
  names match their pipeline filename. Consistent names let a single
  pipeline file target any lab and resource by substitution.

`dci-pipeline-lint` encodes these practices as automated checks. The
sections below describe what it verifies and how to fix each finding.

## Running the linter

Run the linter on your pipeline files before committing:

```ShellSession
$ dci-pipeline-lint my-pipeline.yml
$ dci-pipeline-lint --format json pipeline1.yml pipeline2.yml
$ dci-pipeline-lint --severity E my-pipeline.yml   # errors only
```

## Severity levels

Each finding has a severity, reported as the third field of the
rpmlint-style output (`filename:line:severity:check_id: message`):

- **E** (error) — must be fixed. If any error is present, the linter
  exits with a non-zero status (useful to fail a CI job).
- **W** (warning) — should be fixed; does not affect the exit code.
- **I** (info) — informational only.

The exit code is `0` when no errors are found and `1` when at least one
error is present.

## Checks

The checks below are grouped by severity. The `check_id` in parentheses
is the identifier you can pass to `--check` / `--exclude` to include or
skip a specific check.

### Errors (E)

#### Filename must end with `-pipeline.yml` (`filename-format`)

Pipeline files must be named with the `-pipeline.yml` suffix so they are
recognized as pipeline definitions.

- Bad: `my-job.yml`
- Good: `my-job-pipeline.yml`

#### A valid `stage` is required (`invalid-stage`)

When a job defines a `stage`, it must be one of the predefined stages:

`build`, `hub-install`, `hub-upgrade`, `install`, `upgrade`,
`workload`, `upgraded-workload`

Using any other value is an error.

#### The `topic` field is mandatory (`missing-topic`)

Every job definition must declare a `topic`. It identifies the DCI topic
the job runs against.

```yaml
- name: my-job
  topic: OCP-4.20
  ...
```

#### Credentials must be provided (`no-credentials`)

Every job must set `dci_credentials`. A job without credentials cannot
authenticate against DCI.

#### `dci_config_dir` vs `dci_config_dirs` must match the agent (`wrong-config-dir`, `missing-config-dir`)

The correct key depends on the agent playbook:

- `dci-openshift-agent` (`dci-openshift-agent.yml`) requires
  `dci_config_dirs` (**plural**) in `ansible_extravars`.
- `dci-openshift-app-agent` (`dci-openshift-app-agent.yml`) requires
  `dci_config_dir` (**singular**) in `ansible_extravars`.

Using the wrong form (`wrong-config-dir`) or omitting it entirely
(`missing-config-dir`) is an error.

```yaml
- name: install
  ansible_playbook: /usr/share/dci-openshift-agent/dci-openshift-agent.yml
  ansible_extravars:
    dci_config_dirs:            # plural for dci-openshift-agent
      - /etc/dci-openshift-agent

- name: workload
  ansible_playbook: /usr/share/dci-openshift-app-agent/dci-openshift-app-agent.yml
  ansible_extravars:
    dci_config_dir: /etc/dci-openshift-app-agent   # singular for the app agent
```

### Warnings (W)

#### Use YAML booleans, not Python booleans (`python-boolean`)

Use lowercase `true` / `false` (YAML booleans) rather than Python-style
`True` / `False`. The check searches nested structures recursively.

- Bad: `some_flag: True`
- Good: `some_flag: true`

#### Credentials should use the standard path (`credentials-filename`)

When `dci_credentials` is set, it should point to the standard location:

```yaml
dci_credentials: ~/.config/dci-pipeline/dci_credentials.yml
```

#### Prefer relative inventory paths (`absolute-inventory`)

`ansible_inventory` should use a relative path, which is resolved via
`INVENTORIES_DIRS`, rather than an absolute filesystem path (`/...` or
`~/...`). The `@QUEUE` and `@RESOURCE` placeholders are allowed. This
check is skipped when the job generates its inventory dynamically via
`inventory_playbook`.

#### Inventory should match the playbook (`inventory-mapping-mismatch`)

`ansible_inventory` should match the expected pattern for the playbook:

| Playbook | Expected inventory |
| --- | --- |
| `dci-openshift-agent.yml` | `@QUEUE/@RESOURCE` |
| `dci-openshift-app-agent.yml` | `@QUEUE/@RESOURCE-installed` |

This check is skipped when the job uses `inventory_playbook`.

#### Job name should match the filename (`job-name-mismatch`)

The job `name` should match the pipeline filename (without the
`-pipeline.yml` suffix). A numeric version segment such as `-4.20` in the
filename is ignored when matching, so both of these are accepted for a
file named `acm-hub-4.20-pipeline.yml`:

- job name `acm-hub`
- job name `acm-hub-4.20`

## Adding or skipping checks

- Run only specific checks: `dci-pipeline-lint --check missing-topic --check invalid-stage file-pipeline.yml`
- Skip specific checks: `dci-pipeline-lint --exclude absolute-inventory file-pipeline.yml`

New checks live in `dcipipelinelint/checks/` as `check_*.py` modules
exposing a `check(jobdef, filename, line_number)` function; they are
discovered automatically.
