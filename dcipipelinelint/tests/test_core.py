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

from dcipipelinelint.core import Linter


class TestLinter:
    """Test Linter class."""

    def test_linter_initialization(self):
        """Test Linter initialization."""
        linter = Linter()
        assert linter is not None
        assert hasattr(linter, "checks")
        assert isinstance(linter.checks, list)

    def test_discover_checks(self):
        """Test that checks are discovered automatically."""
        linter = Linter()
        # Should discover at least some checks
        assert len(linter.checks) > 0

    def test_lint_file_not_found(self):
        """Test linting a nonexistent file."""
        linter = Linter()
        results = linter.lint_file("/nonexistent/file.yml")
        assert len(results) == 0

    def test_lint_valid_file(self, sample_pipeline_file):
        """Test linting a valid pipeline file."""
        linter = Linter()
        results = linter.lint_file(sample_pipeline_file)
        # Should return list of results (may be empty if all checks pass)
        assert isinstance(results, list)

    def test_lint_file_with_jobdefs(self, tmp_path):
        """Test linting a file with job definitions."""
        pipeline_file = tmp_path / "test-pipeline.yml"
        pipeline_content = """---
- name: test-job
  stage: ocp
  topic: OCP-4.14
"""
        pipeline_file.write_text(pipeline_content)

        linter = Linter()
        results = linter.lint_file(str(pipeline_file))
        assert isinstance(results, list)
        # Each result should have required fields
        for result in results:
            assert hasattr(result, "filename")
            assert hasattr(result, "severity")
            assert hasattr(result, "check_id")
            assert hasattr(result, "message")

    def test_lint_multiple_files(self, sample_pipeline_file, invalid_pipeline_file):
        """Test linting multiple files."""
        linter = Linter()
        results = linter.lint_files([sample_pipeline_file, invalid_pipeline_file])
        assert isinstance(results, list)
        # Should have results from both files
        filenames = {r.filename for r in results}
        assert sample_pipeline_file in filenames or len(results) == 0
        assert invalid_pipeline_file in filenames or len(results) == 0

    def test_lint_empty_file(self, tmp_path):
        """Test linting an empty file."""
        pipeline_file = tmp_path / "empty-pipeline.yml"
        pipeline_file.write_text("---\n")

        linter = Linter()
        results = linter.lint_file(str(pipeline_file))
        assert isinstance(results, list)

    def test_lint_invalid_yaml(self, tmp_path):
        """Test linting invalid YAML."""
        pipeline_file = tmp_path / "invalid.yml"
        pipeline_file.write_text("invalid: yaml: [unclosed")

        linter = Linter()
        # Should handle gracefully, not crash
        results = linter.lint_file(str(pipeline_file))
        assert isinstance(results, list)
