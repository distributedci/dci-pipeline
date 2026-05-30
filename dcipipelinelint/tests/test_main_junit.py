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

import xml.etree.ElementTree as ET

from dcipipelinelint.main import format_results_junit
from dcipipelinelint.result import LintResult


class TestJUnitFormat:
    """Test JUnit XML format output."""

    def test_junit_format_empty_results(self):
        """Test JUnit format with no results."""
        results = []
        xml_output = format_results_junit(results)
        root = ET.fromstring(xml_output)
        assert root.tag == "testsuites"
        assert root.get("tests") == "0"
        assert root.get("failures") == "0"
        assert root.get("errors") == "0"

    def test_junit_format_with_errors(self):
        """Test JUnit format with error results."""
        results = [
            LintResult(
                filename="test.yml",
                line=5,
                severity="E",
                check_id="invalid-stage",
                message="Invalid stage",
            ),
            LintResult(
                filename="test.yml",
                line=10,
                severity="E",
                check_id="missing-topic",
                message="Missing topic",
            ),
        ]
        xml_output = format_results_junit(results)
        root = ET.fromstring(xml_output)
        assert root.get("tests") == "2"
        assert root.get("errors") == "2"
        assert root.get("failures") == "0"

        testsuite = root.find("testsuite")
        assert testsuite is not None
        assert testsuite.get("name") == "test.yml"
        assert len(testsuite.findall("testcase")) == 2

    def test_junit_format_with_warnings(self):
        """Test JUnit format with warning results."""
        results = [
            LintResult(
                filename="test.yml",
                line=5,
                severity="W",
                check_id="relative-inventory",
                message="Relative inventory path",
            ),
        ]
        xml_output = format_results_junit(results)
        root = ET.fromstring(xml_output)
        assert root.get("failures") == "1"
        assert root.get("errors") == "0"

        testsuite = root.find("testsuite")
        testcase = testsuite.find("testcase")
        assert testcase is not None
        failure = testcase.find("failure")
        assert failure is not None
        assert failure.get("type") == "relative-inventory"

    def test_junit_format_with_info(self):
        """Test JUnit format with info results."""
        results = [
            LintResult(
                filename="test.yml",
                line=5,
                severity="I",
                check_id="info-check",
                message="Info message",
            ),
        ]
        xml_output = format_results_junit(results)
        root = ET.fromstring(xml_output)
        testsuite = root.find("testsuite")
        testcase = testsuite.find("testcase")
        skipped = testcase.find("skipped")
        assert skipped is not None

    def test_junit_format_multiple_files(self):
        """Test JUnit format with results from multiple files."""
        results = [
            LintResult(
                filename="file1.yml",
                line=5,
                severity="E",
                check_id="check1",
                message="Error in file1",
            ),
            LintResult(
                filename="file2.yml",
                line=10,
                severity="W",
                check_id="check2",
                message="Warning in file2",
            ),
        ]
        xml_output = format_results_junit(results)
        root = ET.fromstring(xml_output)
        testsuites = root.findall("testsuite")
        assert len(testsuites) == 2
        assert testsuites[0].get("name") == "file1.yml"
        assert testsuites[1].get("name") == "file2.yml"

    def test_junit_format_no_line_number(self):
        """Test JUnit format with result without line number."""
        results = [
            LintResult(
                filename="test.yml",
                line=None,
                severity="E",
                check_id="filename-format",
                message="Filename should end with -pipeline.yml",
            ),
        ]
        xml_output = format_results_junit(results)
        root = ET.fromstring(xml_output)
        testsuite = root.find("testsuite")
        testcase = testsuite.find("testcase")
        error = testcase.find("error")
        assert error is not None
        assert "test.yml:" in error.text
