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

from dcipipelinelint.checks.check_credentials import check


class TestCheckCredentials:
    """Test check_credentials check."""

    def test_valid_credentials_path(self):
        """Test that valid credentials path passes."""
        jobdef = {"dci_credentials": "~/.config/dci-pipeline/dci_credentials.yml"}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 0

    def test_credentials_not_starting_with_tilde(self):
        """Test that credentials path not starting with ~ fails."""
        jobdef = {"dci_credentials": "/etc/dci/dci_credentials.yml"}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].check_id == "credentials-filename"
        assert results[0].severity == "W"

    def test_credentials_relative_path(self):
        """Test that relative credentials path fails."""
        jobdef = {"dci_credentials": "dci_credentials.yml"}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].check_id == "credentials-filename"
        assert results[0].severity == "W"

    def test_credentials_wrong_filename(self):
        """Test that wrong filename fails."""
        jobdef = {"dci_credentials": "~/.config/dci-pipeline/credentials.yml"}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].check_id == "credentials-filename"
        assert results[0].severity == "W"

    def test_credentials_both_errors(self):
        """Test that incorrect credentials path is detected."""
        jobdef = {"dci_credentials": "/etc/dci/credentials.yml"}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].check_id == "credentials-filename"
        assert results[0].severity == "W"

    def test_missing_credentials(self):
        """Test that missing dci_credentials triggers an error."""
        jobdef = {"name": "test-job"}
        results = check(jobdef, "test-pipeline.yml", 1)
        assert len(results) == 1
        assert results[0].check_id == "no-credentials"
        assert results[0].severity == "E"

    def test_skip_when_no_jobdef(self):
        """Test that check is skipped when jobdef is None."""
        results = check(None, "test-pipeline.yml", None)
        assert len(results) == 0
