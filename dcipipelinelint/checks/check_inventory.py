#
# Copyright (C) 2025 Red Hat, Inc.
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

"""Check for absolute inventory paths."""

from dcipipelinelint.result import LintResult
from dcipipelinelint.utils import is_absolute_path


def check(jobdef, filename, line_number):
    """
    Check if ansible_inventory uses absolute paths.

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

    inventory = jobdef.get("ansible_inventory")
    if inventory and not is_absolute_path(inventory):
        results.append(
            LintResult(
                filename=filename,
                line=line_number,
                severity="W",
                check_id="relative-inventory",
                message=f"Inventory path '{inventory}' should be absolute",
                job_name=jobdef.get("name"),
            )
        )

    return results
