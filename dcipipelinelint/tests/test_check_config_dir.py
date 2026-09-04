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

from dcipipelinelint.checks.check_config_dir import check


class TestCheckConfigDir:
    """Test check_config_dir check."""

    def test_agent_correct_plural(self):
        """dci-openshift-agent with dci_config_dirs (plural) passes."""
        jobdef = {
            "name": "test-job",
            "ansible_playbook": "/usr/share/dci-openshift-agent/dci-openshift-agent.yml",
            "ansible_extravars": {
                "dci_config_dirs": ["../dci-openshift-agent"],
            },
        }
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 0

    def test_agent_wrong_singular(self):
        """dci-openshift-agent with dci_config_dir (singular) is an error."""
        jobdef = {
            "name": "test-job",
            "ansible_playbook": "/usr/share/dci-openshift-agent/dci-openshift-agent.yml",
            "ansible_extravars": {
                "dci_config_dir": "../dci-openshift-agent",
            },
        }
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].severity == "E"
        assert results[0].check_id == "wrong-config-dir"
        assert "plural" in results[0].message

    def test_app_agent_correct_singular(self):
        """dci-openshift-app-agent with dci_config_dir (singular) passes."""
        jobdef = {
            "name": "test-job",
            "ansible_playbook": "/usr/share/dci-openshift-app-agent/dci-openshift-app-agent.yml",
            "ansible_extravars": {
                "dci_config_dir": "../dci-openshift-app-agent",
            },
        }
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 0

    def test_app_agent_wrong_plural(self):
        """dci-openshift-app-agent with dci_config_dirs (plural) is an error."""
        jobdef = {
            "name": "test-job",
            "ansible_playbook": "/usr/share/dci-openshift-app-agent/dci-openshift-app-agent.yml",
            "ansible_extravars": {
                "dci_config_dirs": ["../dci-openshift-app-agent"],
            },
        }
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].severity == "E"
        assert results[0].check_id == "wrong-config-dir"
        assert "singular" in results[0].message

    def test_agent_no_extravars(self):
        """dci-openshift-agent without ansible_extravars is an error."""
        jobdef = {
            "name": "test-job",
            "ansible_playbook": "/usr/share/dci-openshift-agent/dci-openshift-agent.yml",
        }
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].severity == "E"
        assert results[0].check_id == "missing-config-dir"
        assert "dci_config_dirs" in results[0].message

    def test_agent_extravars_without_config_dirs(self):
        """dci-openshift-agent with extravars but no dci_config_dirs is an error."""
        jobdef = {
            "name": "test-job",
            "ansible_playbook": "/usr/share/dci-openshift-agent/dci-openshift-agent.yml",
            "ansible_extravars": {
                "dci_tags": ["debug"],
            },
        }
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].severity == "E"
        assert results[0].check_id == "missing-config-dir"

    def test_app_agent_no_extravars(self):
        """dci-openshift-app-agent without ansible_extravars is an error."""
        jobdef = {
            "name": "test-job",
            "ansible_playbook": "/usr/share/dci-openshift-app-agent/dci-openshift-app-agent.yml",
        }
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].severity == "E"
        assert results[0].check_id == "missing-config-dir"
        assert "dci_config_dir" in results[0].message

    def test_app_agent_extravars_without_config_dir(self):
        """dci-openshift-app-agent with extravars but no dci_config_dir is an error."""
        jobdef = {
            "name": "test-job",
            "ansible_playbook": "/usr/share/dci-openshift-app-agent/dci-openshift-app-agent.yml",
            "ansible_extravars": {
                "dci_tags": ["debug"],
            },
        }
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].severity == "E"
        assert results[0].check_id == "missing-config-dir"

    def test_other_playbook_ignored(self):
        """Other playbooks are not checked."""
        jobdef = {
            "name": "test-job",
            "ansible_playbook": "/usr/share/other-agent/other-agent.yml",
            "ansible_extravars": {
                "dci_config_dir": "../other-agent",
                "dci_config_dirs": ["../other-agent"],
            },
        }
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 0

    def test_skip_when_no_jobdef(self):
        """Check is skipped when jobdef is None."""
        results = check(None, "test-pipeline.yml", None)
        assert len(results) == 0

    def test_agent_relative_playbook_path(self):
        """Relative playbook path ending in dci-openshift-agent.yml is checked."""
        jobdef = {
            "name": "test-job",
            "ansible_playbook": "../../dci-openshift-agent/dci-openshift-agent.yml",
            "ansible_extravars": {
                "dci_config_dir": "../dci-openshift-agent",
            },
        }
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].severity == "E"

    def test_app_agent_relative_playbook_path(self):
        """Relative playbook path ending in dci-openshift-app-agent.yml is checked."""
        jobdef = {
            "name": "test-job",
            "ansible_playbook": "../../dci-openshift-app-agent/dci-openshift-app-agent.yml",
            "ansible_extravars": {
                "dci_config_dirs": ["../dci-openshift-app-agent"],
            },
        }
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].severity == "E"
