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

from dcipipelinelint.checks.check_inventory import check


class TestCheckInventory:
    """Test check_inventory check."""

    def test_absolute_path_slash(self):
        """Test that absolute path starting with / passes."""
        jobdef = {"name": "test-job", "ansible_inventory": "/path/to/inventory.yml"}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 0

    def test_absolute_path_tilde(self):
        """Test that absolute path starting with ~ passes."""
        jobdef = {"name": "test-job", "ansible_inventory": "~/inventories/agent.yml"}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 0

    def test_absolute_path_at_placeholder(self):
        """Test that placeholder pattern starting with @ passes."""
        jobdef = {"name": "test-job", "ansible_inventory": "@QUEUE/@RESOURCE"}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 0

    def test_absolute_path_at_placeholder_with_suffix(self):
        """Test that placeholder pattern with suffix passes."""
        jobdef = {
            "name": "test-job",
            "ansible_inventory": "@QUEUE/@RESOURCE-installed.yml",
        }
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 0

    def test_relative_path(self):
        """Test that relative path fails."""
        jobdef = {"name": "test-job", "ansible_inventory": "inventories/agent.yml"}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].check_id == "relative-inventory"
        assert results[0].severity == "W"

    def test_missing_inventory(self):
        """Test that missing inventory passes."""
        jobdef = {"name": "test-job"}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 0

    def test_skip_when_no_jobdef(self):
        """Test that check is skipped when jobdef is None."""
        results = check(None, "test-pipeline.yml", None)
        assert len(results) == 0
