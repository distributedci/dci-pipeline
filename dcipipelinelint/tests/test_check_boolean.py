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

from dcipipelinelint.checks.check_boolean import check


class TestCheckBoolean:
    """Test check_boolean check."""

    def test_python_true(self):
        """Test that Python True is detected."""
        jobdef = {"name": "test-job", "enabled": True}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].check_id == "python-boolean"
        assert results[0].severity == "W"
        assert "true" in results[0].message.lower()

    def test_python_false(self):
        """Test that Python False is detected."""
        jobdef = {"name": "test-job", "enabled": False}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].check_id == "python-boolean"

    def test_nested_boolean(self):
        """Test that nested boolean is detected."""
        jobdef = {"name": "test-job", "config": {"enabled": True}}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1

    def test_no_boolean(self):
        """Test that jobdef without boolean passes."""
        jobdef = {"name": "test-job", "enabled": "true"}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 0

    def test_skip_when_no_jobdef(self):
        """Test that check is skipped when jobdef is None."""
        results = check(None, "test-pipeline.yml", None)
        assert len(results) == 0
