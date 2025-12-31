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

from dcipipelinelint.checks.check_stage import check


class TestCheckStage:
    """Test check_stage check."""

    def test_valid_stage_build(self):
        """Test that valid stage 'build' passes."""
        jobdef = {"name": "test-job", "stage": "build"}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 0

    def test_valid_stage_install(self):
        """Test that valid stage 'install' passes."""
        jobdef = {"name": "test-job", "stage": "install"}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 0

    def test_valid_stage_upgrade(self):
        """Test that valid stage 'upgrade' passes."""
        jobdef = {"name": "test-job", "stage": "upgrade"}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 0

    def test_valid_stage_workload(self):
        """Test that valid stage 'workload' passes."""
        jobdef = {"name": "test-job", "stage": "workload"}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 0

    def test_valid_stage_upgraded_workload(self):
        """Test that valid stage 'upgraded-workload' passes."""
        jobdef = {"name": "test-job", "stage": "upgraded-workload"}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 0

    def test_invalid_stage(self):
        """Test that invalid stage fails."""
        jobdef = {"name": "test-job", "stage": "invalid-stage"}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].check_id == "invalid-stage"
        assert results[0].severity == "E"
        assert "invalid-stage" in results[0].message

    def test_missing_stage(self):
        """Test that missing stage passes (not checked here)."""
        jobdef = {"name": "test-job"}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 0

    def test_skip_when_no_jobdef(self):
        """Test that check is skipped when jobdef is None."""
        results = check(None, "test-pipeline.yml", None)
        assert len(results) == 0
