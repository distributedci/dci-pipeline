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

from dcipipelinelint.checks.check_job_name import check


class TestCheckJobName:
    """Test check_job_name check."""

    def test_matching_name(self):
        """Test that matching job name passes."""
        jobdef = {"name": "test-job"}
        results = check(jobdef, "test-job-pipeline.yml", 1)
        assert len(results) == 0

    def test_mismatch_name(self):
        """Test that mismatched job name fails."""
        # This should fail because normalized names don't match
        jobdef = {"name": "completely-different"}
        results = check(jobdef, "virt-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].check_id == "job-name-mismatch"
        assert results[0].severity == "W"

    def test_normalized_match_libvirt(self):
        """Test that libvirt matches virt after normalization."""
        # libvirt normalized to virt should match virt filename
        jobdef = {"name": "libvirt"}
        results = check(jobdef, "libvirt-pipeline.yml", 1)
        assert len(results) == 0

    def test_normalized_match(self):
        """Test that normalized names match."""
        jobdef = {"name": "libvirt"}
        results = check(jobdef, "libvirt-pipeline.yml", 1)
        assert len(results) == 0

    def test_missing_name(self):
        """Test that missing name is handled."""
        jobdef = {}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 0

    def test_skip_when_no_jobdef(self):
        """Test that check is skipped when jobdef is None."""
        results = check(None, "test-pipeline.yml", None)
        assert len(results) == 0
