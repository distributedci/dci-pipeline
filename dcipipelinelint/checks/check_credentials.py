#
# Copyright (C) 2026 Red Hat, Inc.
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

"""Check for dci_credentials field format."""

from dcipipelinelint.result import LintResult


def check(jobdef, filename, line_number):
    """
    Check dci_credentials field follows the correct format.

    Args:
        jobdef: Job definition dictionary
        filename: Path to the pipeline file
        line_number: Line number of the job definition

    Returns:
        List of LintResult objects (empty if check passes)
    """
    results = []

    # Skip if no jobdef (file-level check)
    if jobdef is None:
        return results

    credentials = jobdef.get("dci_credentials")

    # Only check if dci_credentials is present
    if credentials:
        # Check if path starts with ~
        if credentials != "~/.config/dci-pipeline/dci_credentials.yml":
            results.append(
                LintResult(
                    filename=filename,
                    line=line_number,
                    severity="W",
                    check_id="credentials-filename",
                    message=f"Credentials path '{credentials}' should be ~/.config/dci-pipeline/dci_credentials.yml",
                    job_name=jobdef.get("name"),
                )
            )

    # no credential
    else:
        results.append(
            LintResult(
                filename=filename,
                line=line_number,
                severity="E",
                check_id="no-credentials",
                message="No credentials provided in dci_credentials field",
                job_name=jobdef.get("name"),
            )
        )

    return results
