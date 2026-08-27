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

"""DRY utilities for dci-pipeline-lint."""

import os
import re

import yaml

VERSION_SEGMENT_PATTERN = re.compile(r"-\d+\.\d+")


def load_pipeline_file(path):
    """
    Load a pipeline YAML file.

    Simplified version for linting - doesn't handle vault encryption.
    For linting purposes, we don't need to decrypt vault statements.

    Args:
        path: Path to the pipeline file

    Returns:
        List of job definitions (dictionaries)

    Raises:
        Exception: If file cannot be read or YAML is invalid
    """
    with open(os.path.expanduser(path)) as stream:
        data = stream.read(-1)

    jobdefs = yaml.load(data, Loader=yaml.BaseLoader)
    if jobdefs is None:
        return []
    # Filter out empty strings and None values from YAML parsing
    if isinstance(jobdefs, list):
        return [j for j in jobdefs if j != "" and j is not None]
    if jobdefs == "" or jobdefs is None:
        return []
    return [jobdefs]


def strip_version_segments(name):
    """
    Remove numeric version segments like -4.20 from a pipeline or job name.

    Args:
        name: Pipeline base name or job name

    Returns:
        Name with version segments removed
    """
    if not name:
        return name
    return VERSION_SEGMENT_PATTERN.sub("", name)


def job_name_matches_filename(job_name, base_filename):
    """
    Check whether a job name is consistent with a pipeline base filename.

    A match is allowed when names are equal or when only the filename includes
    version segments (e.g. acm-hub vs acm-hub-4.20).

    Args:
        job_name: Job name from the pipeline definition
        base_filename: Pipeline filename without -pipeline.yml suffix

    Returns:
        True if the names are considered consistent
    """
    if job_name == base_filename:
        return True
    if job_name == strip_version_segments(base_filename):
        return True
    return False


def has_inventory_playbook(jobdef):
    """
    Return True when the job generates its inventory dynamically.

    Args:
        jobdef: Job definition dictionary

    Returns:
        True if inventory_playbook is defined
    """
    return bool(jobdef and jobdef.get("inventory_playbook"))


def is_absolute_path(path):
    """
    Check if a path is absolute.

    Args:
        path: Path string to check

    Returns:
        True if path is absolute (starts with /, ~, or @ for placeholders), False otherwise
    """
    if not path:
        return False
    # Allow absolute paths, home directory paths, and placeholder patterns (@QUEUE/@RESOURCE)
    return path.startswith("/") or path.startswith("~") or path.startswith("@")


def find_boolean_literals(data, path=""):
    """
    Recursively find Python boolean literals (True/False) in nested structures.

    Args:
        data: Data structure to search (dict, list, or primitive)
        path: Current path in the structure (for tracking location)

    Yields:
        Tuples of (key, value) where value is True or False
        For nested structures, returns the immediate key containing the boolean
    """
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, bool):
                yield (key, value)
            elif isinstance(value, (dict, list)):
                yield from find_boolean_literals(value, key)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, bool):
                # For list items, use the parent path as the key
                yield (path if path else "items", item)
            elif isinstance(item, (dict, list)):
                yield from find_boolean_literals(item, path)
    elif isinstance(data, bool):
        yield (path, data)
