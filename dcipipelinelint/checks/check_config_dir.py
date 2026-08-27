#
# Copyright (C) 2025-2026 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""Check for correct dci_config_dir vs dci_config_dirs usage."""

from dcipipelinelint.result import LintResult

AGENT_PLAYBOOK = "dci-openshift-agent.yml"
APP_AGENT_PLAYBOOK = "dci-openshift-app-agent.yml"


def check(jobdef, filename, line_number):
    """
    Check that dci-openshift-agent jobs use dci_config_dirs (plural)
    and dci-openshift-app-agent jobs use dci_config_dir (singular).

    Args:
        jobdef: Job definition dictionary
        filename: Path to the pipeline file
        line_number: Line number of the job definition

    Returns:
        List of LintResult objects (empty if check passes)
    """
    results = []

    if jobdef is None:
        return results

    playbook = jobdef.get("ansible_playbook", "")
    extravars = jobdef.get("ansible_extravars", {})
    if not isinstance(extravars, dict):
        return results

    if playbook.endswith(AGENT_PLAYBOOK) and not playbook.endswith(APP_AGENT_PLAYBOOK):
        if "dci_config_dir" in extravars:
            results.append(
                LintResult(
                    filename=filename,
                    line=line_number,
                    severity="E",
                    check_id="wrong-config-dir",
                    message="dci-openshift-agent requires 'dci_config_dirs' (plural), not 'dci_config_dir'",
                    job_name=jobdef.get("name"),
                )
            )
        elif "dci_config_dirs" not in extravars:
            results.append(
                LintResult(
                    filename=filename,
                    line=line_number,
                    severity="E",
                    check_id="missing-config-dir",
                    message="dci-openshift-agent requires 'dci_config_dirs' in ansible_extravars",
                    job_name=jobdef.get("name"),
                )
            )
    elif playbook.endswith(APP_AGENT_PLAYBOOK):
        if "dci_config_dirs" in extravars:
            results.append(
                LintResult(
                    filename=filename,
                    line=line_number,
                    severity="E",
                    check_id="wrong-config-dir",
                    message="dci-openshift-app-agent requires 'dci_config_dir' (singular), not 'dci_config_dirs'",
                    job_name=jobdef.get("name"),
                )
            )
        elif "dci_config_dir" not in extravars:
            results.append(
                LintResult(
                    filename=filename,
                    line=line_number,
                    severity="E",
                    check_id="missing-config-dir",
                    message="dci-openshift-app-agent requires 'dci_config_dir' in ansible_extravars",
                    job_name=jobdef.get("name"),
                )
            )

    return results
