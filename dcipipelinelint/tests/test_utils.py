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

import pytest

from dcipipelinelint.utils import (
    find_boolean_literals,
    is_absolute_path,
    load_pipeline_file,
)


class TestLoadPipelineFile:
    """Test load_pipeline_file function."""

    def test_load_valid_pipeline(self, tmp_path):
        """Test loading a valid pipeline file."""
        pipeline_file = tmp_path / "test-pipeline.yml"
        pipeline_content = """---
- name: test-job
  stage: ocp
  topic: OCP-4.14
"""
        pipeline_file.write_text(pipeline_content)

        result = load_pipeline_file(str(pipeline_file))
        assert len(result) == 1
        assert result[0]["name"] == "test-job"
        assert result[0]["stage"] == "ocp"
        assert result[0]["topic"] == "OCP-4.14"

    def test_load_multiple_jobs(self, tmp_path):
        """Test loading a pipeline file with multiple jobs."""
        pipeline_file = tmp_path / "test-pipeline.yml"
        pipeline_content = """---
- name: job1
  stage: ocp
- name: job2
  stage: cnf
"""
        pipeline_file.write_text(pipeline_content)

        result = load_pipeline_file(str(pipeline_file))
        assert len(result) == 2
        assert result[0]["name"] == "job1"
        assert result[1]["name"] == "job2"

    def test_load_empty_file(self, tmp_path):
        """Test loading an empty pipeline file."""
        pipeline_file = tmp_path / "test-pipeline.yml"
        pipeline_file.write_text("---\n")

        result = load_pipeline_file(str(pipeline_file))
        assert result == []

    def test_load_invalid_yaml(self, tmp_path):
        """Test loading invalid YAML raises exception."""
        pipeline_file = tmp_path / "test-pipeline.yml"
        pipeline_file.write_text("invalid: yaml: content: [unclosed")

        with pytest.raises(Exception):
            load_pipeline_file(str(pipeline_file))

    def test_load_nonexistent_file(self):
        """Test loading nonexistent file raises exception."""
        with pytest.raises(Exception):
            load_pipeline_file("/nonexistent/file.yml")


class TestIsAbsolutePath:
    """Test is_absolute_path function."""

    def test_absolute_path_starts_with_slash(self):
        """Test absolute path starting with /."""
        assert is_absolute_path("/usr/share/test.yml") is True

    def test_absolute_path_starts_with_tilde(self):
        """Test absolute path starting with ~."""
        assert is_absolute_path("~/test.yml") is True

    def test_absolute_path_starts_with_at_placeholder(self):
        """Test placeholder pattern starting with @."""
        assert is_absolute_path("@QUEUE/@RESOURCE") is True
        assert is_absolute_path("@QUEUE/@RESOURCE-installed.yml") is True

    def test_relative_path(self):
        """Test relative path."""
        assert is_absolute_path("test.yml") is False
        assert is_absolute_path("agents/test.yml") is False
        assert is_absolute_path("./test.yml") is False

    def test_none_path(self):
        """Test None path."""
        assert is_absolute_path(None) is False

    def test_empty_path(self):
        """Test empty path."""
        assert is_absolute_path("") is False


class TestFindBooleanLiterals:
    """Test find_boolean_literals function."""

    def test_find_python_true(self):
        """Test finding Python True literal."""
        data = {"enabled": True, "disabled": False}
        results = list(find_boolean_literals(data))
        assert len(results) == 2
        assert ("enabled", True) in results
        assert ("disabled", False) in results

    def test_find_python_true_in_nested_dict(self):
        """Test finding Python True in nested dictionary."""
        data = {
            "level1": {
                "level2": {
                    "enabled": True,
                }
            }
        }
        results = list(find_boolean_literals(data))
        assert len(results) == 1
        assert ("enabled", True) in results

    def test_find_python_true_in_list(self):
        """Test finding Python True in list."""
        data = {"items": [True, False, "string", 42]}
        results = list(find_boolean_literals(data))
        assert len(results) == 2
        assert ("items", True) in results
        assert ("items", False) in results

    def test_no_boolean_literals(self):
        """Test data with no Python boolean literals."""
        data = {"enabled": "true", "disabled": "false", "count": 42}
        results = list(find_boolean_literals(data))
        assert len(results) == 0

    def test_empty_dict(self):
        """Test empty dictionary."""
        results = list(find_boolean_literals({}))
        assert len(results) == 0

    def test_none_value(self):
        """Test None value."""
        data = {"key": None}
        results = list(find_boolean_literals(data))
        assert len(results) == 0
