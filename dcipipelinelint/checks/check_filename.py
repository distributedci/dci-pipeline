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

"""Check for filename format validation."""

from dcipipelinelint.result import LintResult


def check(jobdef, filename, line_number):
    """
    Check if filename ends with -pipeline.yml.

    This is a file-level check, so it only runs when jobdef is None.

    Args:
        jobdef: Job definition (None for file-level checks)
        filename: Path to the pipeline file
        line_number: Line number (not used for file-level checks)

    Returns:
        List of LintResult objects (empty if check passes)
    """
    results = []

    # Only run this check for file-level (jobdef is None)
    if jobdef is not None:
        return results

    if filename and not filename.endswith("-pipeline.yml"):
        results.append(
            LintResult(
                filename=filename,
                line=None,
                severity="E",
                check_id="filename-format",
                message="Filename should end with -pipeline.yml",
            )
        )

    return results
