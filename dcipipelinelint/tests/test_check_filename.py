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

from dcipipelinelint.checks.check_filename import check


class TestCheckFilename:
    """Test check_filename check."""

    def test_valid_filename(self):
        """Test that valid filename passes."""
        results = check(None, "test-pipeline.yml", None)
        assert len(results) == 0

    def test_invalid_filename_no_suffix(self):
        """Test that filename without -pipeline.yml fails."""
        results = check(None, "test.yml", None)
        assert len(results) == 1
        assert results[0].check_id == "filename-format"
        assert results[0].severity == "E"
        assert results[0].line is None

    def test_invalid_filename_wrong_suffix(self):
        """Test that filename with wrong suffix fails."""
        results = check(None, "test-pipeline.yaml", None)
        assert len(results) == 1
        assert results[0].check_id == "filename-format"

    def test_skip_when_jobdef_provided(self):
        """Test that check is skipped when jobdef is provided."""
        jobdef = {"name": "test-job"}
        results = check(jobdef, "test.yml", 1)
        assert len(results) == 0

    def test_none_filename(self):
        """Test that None filename is handled."""
        results = check(None, None, None)
        assert len(results) == 0
