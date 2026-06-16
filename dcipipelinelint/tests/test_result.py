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

from dcipipelinelint.result import LintResult


class TestLintResult:
    """Test LintResult class."""

    def test_create_result_with_all_fields(self):
        """Test creating a LintResult with all fields."""
        result = LintResult(
            filename="test-pipeline.yml",
            line=5,
            severity="E",
            check_id="test-check",
            message="Test message",
            job_name="test-job",
        )
        assert result.filename == "test-pipeline.yml"
        assert result.line == 5
        assert result.severity == "E"
        assert result.check_id == "test-check"
        assert result.message == "Test message"
        assert result.job_name == "test-job"

    def test_create_result_without_line(self):
        """Test creating a LintResult without line number (file-level check)."""
        result = LintResult(
            filename="test-pipeline.yml",
            line=None,
            severity="W",
            check_id="filename-format",
            message="Filename should end with -pipeline.yml",
        )
        assert result.filename == "test-pipeline.yml"
        assert result.line is None
        assert result.severity == "W"
        assert result.check_id == "filename-format"
        assert result.message == "Filename should end with -pipeline.yml"
        assert result.job_name is None

    def test_create_result_without_job_name(self):
        """Test creating a LintResult without job_name."""
        result = LintResult(
            filename="test-pipeline.yml",
            line=10,
            severity="I",
            check_id="info-check",
            message="Info message",
        )
        assert result.job_name is None

    def test_format_rpmlint_with_line(self):
        """Test rpmlint-style formatting with line number."""
        result = LintResult(
            filename="test-pipeline.yml",
            line=5,
            severity="E",
            check_id="test-check",
            message="Test error message",
            job_name="test-job",
        )
        expected = "test-pipeline.yml:5:E:test-check: Test error message"
        assert result.format_rpmlint() == expected

    def test_format_rpmlint_without_line(self):
        """Test rpmlint-style formatting without line number."""
        result = LintResult(
            filename="test-pipeline.yml",
            line=None,
            severity="W",
            check_id="filename-format",
            message="Filename should end with -pipeline.yml",
        )
        expected = "test-pipeline.yml::W:filename-format: Filename should end with -pipeline.yml"
        assert result.format_rpmlint() == expected

    def test_format_rpmlint_different_severities(self):
        """Test rpmlint-style formatting with different severities."""
        error = LintResult(
            filename="test.yml",
            line=1,
            severity="E",
            check_id="error-check",
            message="Error",
        )
        warning = LintResult(
            filename="test.yml",
            line=2,
            severity="W",
            check_id="warning-check",
            message="Warning",
        )
        info = LintResult(
            filename="test.yml",
            line=3,
            severity="I",
            check_id="info-check",
            message="Info",
        )
        assert error.format_rpmlint() == "test.yml:1:E:error-check: Error"
        assert warning.format_rpmlint() == "test.yml:2:W:warning-check: Warning"
        assert info.format_rpmlint() == "test.yml:3:I:info-check: Info"

    def test_to_dict_with_all_fields(self):
        """Test converting LintResult to dictionary with all fields."""
        result = LintResult(
            filename="test-pipeline.yml",
            line=5,
            severity="E",
            check_id="test-check",
            message="Test message",
            job_name="test-job",
        )
        expected = {
            "filename": "test-pipeline.yml",
            "line": 5,
            "severity": "E",
            "check_id": "test-check",
            "message": "Test message",
            "job_name": "test-job",
        }
        assert result.to_dict() == expected

    def test_to_dict_without_optional_fields(self):
        """Test converting LintResult to dictionary without optional fields."""
        result = LintResult(
            filename="test-pipeline.yml",
            line=None,
            severity="W",
            check_id="filename-format",
            message="Filename should end with -pipeline.yml",
        )
        expected = {
            "filename": "test-pipeline.yml",
            "line": None,
            "severity": "W",
            "check_id": "filename-format",
            "message": "Filename should end with -pipeline.yml",
            "job_name": None,
        }
        assert result.to_dict() == expected
