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

"""Check for job name consistency with filename."""

import os

from dcipipelinelint.result import LintResult


def check(jobdef, filename, line_number):
    """
    Check if job name is consistent with filename.

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

    job_name = jobdef.get("name")
    if not job_name or not filename:
        return results

    # Extract base filename without extension and -pipeline suffix
    base_filename = os.path.basename(filename)
    if base_filename.endswith("-pipeline.yml"):
        base_filename = base_filename[: -len("-pipeline.yml")]  # Remove "-pipeline.yml"
    elif base_filename.endswith(".yml"):
        base_filename = base_filename[:-4]  # Remove ".yml"

    # Check if job name matches filename exactly
    if job_name != base_filename:
        results.append(
            LintResult(
                filename=filename,
                line=line_number,
                severity="W",
                check_id="job-name-mismatch",
                message=f"Job name '{job_name}' doesn't match filename pattern '{base_filename}'",
                job_name=job_name,
            )
        )

    return results
