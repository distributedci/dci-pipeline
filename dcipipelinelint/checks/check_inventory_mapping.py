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

"""Check for inventory mapping according to playbook."""

import fnmatch
import os

from dcipipelinelint.result import LintResult

# Cache for loaded mappings
_mappings_cache = None


def _load_mappings():
    """Load inventory mappings from data file."""
    global _mappings_cache
    if _mappings_cache is not None:
        return _mappings_cache

    _mappings_cache = []
    mapping_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "inventory_mapping.yml"
    )

    if os.path.exists(mapping_file):
        import yaml

        with open(mapping_file) as f:
            data = yaml.load(f, Loader=yaml.SafeLoader)
            if data and "mappings" in data:
                _mappings_cache = data["mappings"]

    return _mappings_cache


def check(jobdef, filename, line_number):
    """
    Check if inventory matches expected pattern for given playbook.

    Args:
        jobdef: Job definition dictionary
        filename: Path to the pipeline file
        line_number: Line number of the job definition

    Returns:
        List of LintResult objects (empty if check passes)
    """
    results = []

    # Skip if no jobdef (file-level check)
    if jobdef is None:
        return results

    playbook = jobdef.get("ansible_playbook")
    inventory = jobdef.get("ansible_inventory")

    if not playbook or not inventory:
        return results

    mappings = _load_mappings()
    if not mappings:
        return results

    # Find matching mapping for playbook
    for mapping in mappings:
        playbook_pattern = mapping.get("playbook_pattern", "")
        if fnmatch.fnmatch(playbook, playbook_pattern):
            inventory_pattern = mapping.get("inventory_pattern", "")
            if not fnmatch.fnmatch(inventory, inventory_pattern):
                results.append(
                    LintResult(
                        filename=filename,
                        line=line_number,
                        severity="W",
                        check_id="inventory-mapping-mismatch",
                        message=f"Inventory '{inventory}' doesn't match expected pattern '{inventory_pattern}' for playbook '{playbook}'",
                        job_name=jobdef.get("name"),
                    )
                )
            break

    return results
