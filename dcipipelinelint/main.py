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

"""Main entry point for dci-pipeline-lint."""

import argparse
import json
import sys
import xml.etree.ElementTree as ET

from dcipipelinelint.core import Linter


def format_results_rpmlint(results):
    """
    Format results in rpmlint style.

    Args:
        results: List of LintResult objects

    Returns:
        List of formatted strings
    """
    return [r.format_rpmlint() for r in results]


def format_results_json(results):
    """
    Format results in JSON style.

    Args:
        results: List of LintResult objects

    Returns:
        JSON string
    """
    results_dict = [r.to_dict() for r in results]
    summary = {
        "total_errors": sum(1 for r in results if r.severity == "E"),
        "total_warnings": sum(1 for r in results if r.severity == "W"),
        "total_info": sum(1 for r in results if r.severity == "I"),
    }
    return json.dumps({"results": results_dict, "summary": summary}, indent=2)


def format_results_junit(results):
    """
    Format results in JUnit XML style.

    Args:
        results: List of LintResult objects

    Returns:
        JUnit XML string
    """
    # Group results by filename
    results_by_file = {}
    for result in results:
        filename = result.filename
        if filename not in results_by_file:
            results_by_file[filename] = []
        results_by_file[filename].append(result)

    # Create root testsuites element
    testsuites = ET.Element("testsuites")
    testsuites.set("name", "dci-pipeline-lint")

    total_tests = 0
    total_failures = 0
    total_errors = 0

    # Create a testsuite for each file
    for filename, file_results in results_by_file.items():
        errors = sum(1 for r in file_results if r.severity == "E")
        failures = sum(1 for r in file_results if r.severity == "W")
        skipped = sum(1 for r in file_results if r.severity == "I")
        tests = len(file_results)

        total_tests += tests
        total_failures += failures
        total_errors += errors

        testsuite = ET.SubElement(testsuites, "testsuite")
        testsuite.set("name", filename)
        testsuite.set("tests", str(tests))
        testsuite.set("failures", str(failures))
        testsuite.set("errors", str(errors))
        testsuite.set("skipped", str(skipped))

        # Create testcase for each result
        for result in file_results:
            testcase = ET.SubElement(testsuite, "testcase")
            testcase.set("classname", result.check_id)
            testcase.set("name", result.message[:100])  # Limit name length
            testcase.set("time", "0")

            # Add failure/error/skipped element based on severity
            if result.severity == "E":
                failure = ET.SubElement(testcase, "error")
                failure.set("type", result.check_id)
                failure.set("message", result.message)
                if result.line is not None:
                    failure.text = f"{result.filename}:{result.line}: {result.message}"
                else:
                    failure.text = f"{result.filename}: {result.message}"
            elif result.severity == "W":
                failure = ET.SubElement(testcase, "failure")
                failure.set("type", result.check_id)
                failure.set("message", result.message)
                if result.line is not None:
                    failure.text = f"{result.filename}:{result.line}: {result.message}"
                else:
                    failure.text = f"{result.filename}: {result.message}"
            elif result.severity == "I":
                skipped = ET.SubElement(testcase, "skipped")
                skipped.set("message", result.message)

    testsuites.set("tests", str(total_tests))
    testsuites.set("failures", str(total_failures))
    testsuites.set("errors", str(total_errors))

    # Convert to string
    # ET.indent is available in Python 3.9+, use it if available
    if hasattr(ET, "indent"):
        ET.indent(testsuites, space="  ")
    return ET.tostring(testsuites, encoding="unicode", xml_declaration=True)


def filter_results(results, severity=None, check_ids=None, exclude_check_ids=None):
    """
    Filter results by severity and check IDs.

    Args:
        results: List of LintResult objects
        severity: Filter by severity (E/W/I)
        check_ids: Include only these check IDs
        exclude_check_ids: Exclude these check IDs

    Returns:
        Filtered list of LintResult objects
    """
    filtered = results

    if severity:
        filtered = [r for r in filtered if r.severity == severity]

    if check_ids:
        filtered = [r for r in filtered if r.check_id in check_ids]

    if exclude_check_ids:
        filtered = [r for r in filtered if r.check_id not in exclude_check_ids]

    return filtered


def main(args=None):
    """
    Main entry point for dci-pipeline-lint.

    Args:
        args: Command line arguments (defaults to sys.argv)

    Returns:
        Exit code (0 if no errors, 1 if errors found)
    """
    if args is None:
        args = sys.argv

    parser = argparse.ArgumentParser(
        prog="dci-pipeline-lint",
        description="Lint dci-pipeline job definition files",
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="Pipeline file(s) to check",
    )
    parser.add_argument(
        "--severity",
        choices=["E", "W", "I"],
        help="Filter by severity (E=error, W=warning, I=info)",
    )
    parser.add_argument(
        "--check",
        action="append",
        dest="checks",
        help="Run specific check(s) only (can be specified multiple times)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        dest="exclude_checks",
        help="Exclude specific check(s) (can be specified multiple times)",
    )
    parser.add_argument(
        "--format",
        choices=["rpmlint", "json", "junit"],
        default="rpmlint",
        help="Output format (default: rpmlint)",
    )

    parsed_args = parser.parse_args(args[1:])

    # Initialize linter
    linter = Linter()

    # Lint all files
    all_results = linter.lint_files(parsed_args.files)

    # Filter results
    filtered_results = filter_results(
        all_results,
        severity=parsed_args.severity,
        check_ids=parsed_args.checks,
        exclude_check_ids=parsed_args.exclude_checks,
    )

    # Format and output results
    if parsed_args.format == "json":
        output = format_results_json(filtered_results)
        print(output)
    elif parsed_args.format == "junit":
        output = format_results_junit(filtered_results)
        print(output)
    else:
        output_lines = format_results_rpmlint(filtered_results)
        for line in output_lines:
            print(line)

    # Return exit code: 0 if no errors, 1 if errors found
    has_errors = any(r.severity == "E" for r in filtered_results)
    return 1 if has_errors else 0
