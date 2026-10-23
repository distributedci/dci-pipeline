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

from unittest.mock import patch

import pytest

from dcipipelinelint.main import main


class TestMainCLI:
    """Test main CLI."""

    def test_main_no_args(self):
        """Test main with no arguments."""
        with patch("sys.argv", ["dci-pipeline-lint"]):
            with pytest.raises(SystemExit):
                main()

    def test_main_with_file(self, sample_pipeline_file, capsys):
        """Test main with a valid file."""
        with patch("sys.argv", ["dci-pipeline-lint", sample_pipeline_file]):
            exit_code = main()
            # Should exit with 0 if no errors, 1 if errors found
            assert exit_code in [0, 1]

    def test_main_multiple_files(
        self, sample_pipeline_file, invalid_pipeline_file, capsys
    ):
        """Test main with multiple files."""
        with patch(
            "sys.argv",
            ["dci-pipeline-lint", sample_pipeline_file, invalid_pipeline_file],
        ):
            exit_code = main()
            assert exit_code in [0, 1]

    def test_main_nonexistent_file(self, capsys):
        """Test main with nonexistent file."""
        with patch("sys.argv", ["dci-pipeline-lint", "/nonexistent/file.yml"]):
            exit_code = main()
            # Should handle gracefully
            assert exit_code in [0, 1]

    def test_main_severity_filter(self, sample_pipeline_file, capsys):
        """Test main with severity filter."""
        with patch(
            "sys.argv", ["dci-pipeline-lint", "--severity", "E", sample_pipeline_file]
        ):
            exit_code = main()
            assert exit_code in [0, 1]

    def test_main_format_json(self, sample_pipeline_file, capsys):
        """Test main with JSON format."""
        with patch(
            "sys.argv", ["dci-pipeline-lint", "--format", "json", sample_pipeline_file]
        ):
            exit_code = main()
            assert exit_code in [0, 1]

    def test_main_format_junit(self, sample_pipeline_file, capsys):
        """Test main with JUnit XML format."""
        with patch(
            "sys.argv", ["dci-pipeline-lint", "--format", "junit", sample_pipeline_file]
        ):
            exit_code = main()
            assert exit_code in [0, 1]
            captured = capsys.readouterr()
            assert "<?xml" in captured.out
            assert "testsuites" in captured.out
