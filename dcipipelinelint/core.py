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

"""Core linting engine for dci-pipeline-lint."""

import logging
import os

from dcipipelinelint import checks
from dcipipelinelint.utils import load_pipeline_file

log = logging.getLogger(__name__)


class Linter:
    """Main linter class that orchestrates checks."""

    def __init__(self):
        """Initialize the linter and discover checks."""
        self.checks = checks.get_all_checks()

    def lint_file(self, filename):
        """
        Lint a single pipeline file.

        Args:
            filename: Path to the pipeline file

        Returns:
            List of LintResult objects
        """
        results = []

        # Check if file exists
        if not os.path.exists(filename):
            log.warning(f"File not found: {filename}")
            return results

        try:
            # Load job definitions from file
            jobdefs = load_pipeline_file(filename)
        except Exception as e:
            log.error(f"Error loading file {filename}: {e}")
            return results

        # Run file-level checks (checks that operate on the filename itself)
        for check_func in self.checks:
            try:
                # File-level checks receive None as jobdef
                file_results = check_func(None, filename, None)
                if file_results:
                    results.extend(file_results)
            except Exception as e:
                log.error(
                    f"Error running check {check_func.__name__} on file {filename}: {e}"
                )

        # Run job-level checks for each job definition
        for jobdef in jobdefs:
            if not isinstance(jobdef, dict):
                continue

            # Try to get line number (simplified - actual implementation may need YAML parsing)
            line_number = None

            for check_func in self.checks:
                try:
                    job_results = check_func(jobdef, filename, line_number)
                    if job_results:
                        results.extend(job_results)
                except Exception as e:
                    log.error(
                        f"Error running check {check_func.__name__} on job {jobdef.get('name', 'unknown')}: {e}"
                    )

        return results

    def lint_files(self, filenames):
        """
        Lint multiple pipeline files.

        Args:
            filenames: List of paths to pipeline files

        Returns:
            List of LintResult objects from all files
        """
        all_results = []
        for filename in filenames:
            results = self.lint_file(filename)
            all_results.extend(results)
        return all_results
