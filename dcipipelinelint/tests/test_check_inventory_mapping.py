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

from dcipipelinelint.checks.check_inventory_mapping import check


class TestCheckInventoryMapping:
    """Test check_inventory_mapping check."""

    def test_matching_mapping_openshift_agent(self):
        """Test that matching inventory pattern passes for openshift-agent."""
        jobdef = {
            "name": "test-job",
            "ansible_playbook": "/usr/share/dci-openshift-agent/dci-openshift-agent.yml",
            "ansible_inventory": "@QUEUE/@RESOURCE",
        }
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 0

    def test_mismatch_mapping_openshift_agent_yaml_extension(self):
        """Yaml inventory extension is rejected: extension-less form required."""
        jobdef = {
            "name": "test-job",
            "ansible_playbook": "/usr/share/dci-openshift-agent/dci-openshift-agent.yml",
            "ansible_inventory": "@QUEUE/@RESOURCE.yml",
        }
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].check_id == "inventory-mapping-mismatch"

    def test_mismatch_mapping_openshift_agent_ini_extension(self):
        """Ini inventory extension is rejected: extension-less form required."""
        jobdef = {
            "name": "test-job",
            "ansible_playbook": "/usr/share/dci-openshift-agent/dci-openshift-agent.yml",
            "ansible_inventory": "@QUEUE/@RESOURCE.ini",
        }
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].check_id == "inventory-mapping-mismatch"

    def test_matching_mapping_openshift_app_agent(self):
        """Test that matching inventory pattern passes for openshift-app-agent."""
        jobdef = {
            "name": "test-job",
            "ansible_playbook": "/usr/share/dci-openshift-app-agent/dci-openshift-app-agent.yml",
            "ansible_inventory": "@QUEUE/@RESOURCE-installed",
        }
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 0

    def test_mismatch_mapping_openshift_app_agent_yaml_extension(self):
        """Yaml inventory extension is rejected: extension-less form required."""
        jobdef = {
            "name": "test-job",
            "ansible_playbook": "/usr/share/dci-openshift-app-agent/dci-openshift-app-agent.yml",
            "ansible_inventory": "@QUEUE/@RESOURCE-installed.yml",
        }
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].check_id == "inventory-mapping-mismatch"

    def test_mismatch_mapping_openshift_app_agent_ini_extension(self):
        """Ini inventory extension is rejected: extension-less form required."""
        jobdef = {
            "name": "test-job",
            "ansible_playbook": "/usr/share/dci-openshift-app-agent/dci-openshift-app-agent.yml",
            "ansible_inventory": "@QUEUE/@RESOURCE-installed.ini",
        }
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].check_id == "inventory-mapping-mismatch"

    def test_mismatch_mapping_openshift_agent(self):
        """Test that mismatched inventory pattern fails for openshift-agent."""
        jobdef = {
            "name": "test-job",
            "ansible_playbook": "/usr/share/dci-openshift-agent/dci-openshift-agent.yml",
            "ansible_inventory": "relative/path/inventory.yml",
        }
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].check_id == "inventory-mapping-mismatch"
        assert results[0].severity == "W"

    def test_mismatch_mapping_openshift_app_agent(self):
        """Test that mismatched inventory pattern fails for openshift-app-agent."""
        jobdef = {
            "name": "test-job",
            "ansible_playbook": "/usr/share/dci-openshift-app-agent/dci-openshift-app-agent.yml",
            "ansible_inventory": "@QUEUE/@RESOURCE",
        }
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].check_id == "inventory-mapping-mismatch"
        assert results[0].severity == "W"

    def test_skip_with_inventory_playbook(self):
        """Inventory mapping check is skipped when inventory_playbook is set."""
        jobdef = {
            "name": "acm-hub",
            "ansible_playbook": "/usr/share/dci-openshift-agent/dci-openshift-agent.yml",
            "ansible_inventory": "~/inventories/@QUEUE-@RESOURCE-hosts",
            "inventory_playbook": "~/dci/hardware-validation-config/files/abi-inventory.yml",
        }
        results = check(jobdef, "acm-hub-4.20-pipeline.yml", 1)
        assert len(results) == 0

    def test_missing_playbook(self):
        """Test that missing playbook passes."""
        jobdef = {"name": "test-job", "ansible_inventory": "~/inventories/agent.yml"}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 0

    def test_missing_inventory(self):
        """Test that missing inventory passes."""
        jobdef = {
            "name": "test-job",
            "ansible_playbook": "/usr/share/dci-openshift-agent/dci-openshift-agent.yml",
        }
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 0

    def test_missing_playbook_openshift_app_agent(self):
        """Test that missing playbook passes."""
        jobdef = {
            "name": "test-job",
            "ansible_inventory": "@QUEUE/@RESOURCE-installed",
        }
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 0

    def test_skip_when_no_jobdef(self):
        """Test that check is skipped when jobdef is None."""
        results = check(None, "test-pipeline.yml", None)
        assert len(results) == 0
