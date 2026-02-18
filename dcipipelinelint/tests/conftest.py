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

"""Pytest fixtures for dci-pipeline-lint tests."""

import pytest


@pytest.fixture
def valid_jobdef():
    """Return a minimal valid job definition."""
    return {
        "name": "test-job",
        "stage": "ocp",
        "topic": "OCP-4.14",
        "ansible_playbook": "/usr/share/dci-openshift-agent/dci-openshift-agent.yml",
        "ansible_inventory": "~/inventories/agent.yml",
    }


@pytest.fixture
def sample_pipeline_file(tmp_path):
    """Create a temporary pipeline file with sample content."""
    pipeline_file = tmp_path / "test-pipeline.yml"
    pipeline_content = """---
- name: test-job
  stage: ocp
  topic: OCP-4.14
"""
    pipeline_file.write_text(pipeline_content)
    return str(pipeline_file)


@pytest.fixture
def invalid_pipeline_file(tmp_path):
    """Create a temporary pipeline file with invalid content."""
    pipeline_file = tmp_path / "invalid-pipeline.yml"
    pipeline_content = """---
- name: test-job
  stage: invalid-stage
"""
    pipeline_file.write_text(pipeline_content)
    return str(pipeline_file)
