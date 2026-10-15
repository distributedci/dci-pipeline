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

"""Check for valid stage and prev_stages names."""

from dcipipelinelint.result import LintResult

# Pre-defined list of valid stages
VALID_STAGES = [
    "build",
    "hub-install",
    "hub-upgrade",
    "install",
    "upgrade",
    "workload",
    "upgraded-workload",
]


def check(jobdef, filename, line_number):
    """
    Check if the stage and prev_stages fields are in the predefined list.

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

    stage = jobdef.get("stage")
    if stage and stage not in VALID_STAGES:
        results.append(
            LintResult(
                filename=filename,
                line=line_number,
                severity="E",
                check_id="invalid-stage",
                message=f"Stage '{stage}' is not in predefined list: {', '.join(VALID_STAGES)}",
                job_name=jobdef.get("name"),
            )
        )

    prev_stages = jobdef.get("prev_stages")
    if prev_stages:
        # prev_stages may be a single string or a list of strings
        if not isinstance(prev_stages, list):
            prev_stages = [prev_stages]
        for prev_stage in prev_stages:
            if prev_stage not in VALID_STAGES:
                results.append(
                    LintResult(
                        filename=filename,
                        line=line_number,
                        severity="E",
                        check_id="invalid-prev-stage",
                        message=f"prev_stages entry '{prev_stage}' is not in predefined list: {', '.join(VALID_STAGES)}",
                        job_name=jobdef.get("name"),
                    )
                )

    return results
