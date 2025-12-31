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

"""Result classes and formatting for dci-pipeline-lint."""


class LintResult:
    """Represents a single linting result."""

    def __init__(
        self,
        filename,
        line,
        severity,
        check_id,
        message,
        job_name=None,
    ):
        """
        Initialize a LintResult.

        Args:
            filename: Path to the pipeline file
            line: Line number (None for file-level checks)
            severity: 'E' (error), 'W' (warning), 'I' (info)
            check_id: Unique identifier for the check
            message: Human-readable message
            job_name: Name of the job (optional)
        """
        self.filename = filename
        self.line = line
        self.severity = severity
        self.check_id = check_id
        self.message = message
        self.job_name = job_name

    def format_rpmlint(self):
        """
        Format result as rpmlint-style string.

        Returns:
            String in format: filename:line:severity:check_id: message
        """
        line_str = str(self.line) if self.line is not None else ""
        return f"{self.filename}:{line_str}:{self.severity}:{self.check_id}: {self.message}"

    def to_dict(self):
        """
        Convert result to dictionary for JSON output.

        Returns:
            Dictionary with all result fields
        """
        return {
            "filename": self.filename,
            "line": self.line,
            "severity": self.severity,
            "check_id": self.check_id,
            "message": self.message,
            "job_name": self.job_name,
        }
