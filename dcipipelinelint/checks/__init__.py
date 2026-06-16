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

"""Check discovery and registration for dci-pipeline-lint."""

import importlib
import logging
import pkgutil

log = logging.getLogger(__name__)


def get_all_checks():
    """
    Get all registered check functions.

    Discovers and imports all check_*.py modules dynamically.

    Returns:
        List of check functions
    """
    checks_list = []

    # Get the directory containing check modules
    checks_dir = __path__[0]

    # Discover and import all check_*.py modules
    for _, name, ispkg in pkgutil.iter_modules([checks_dir]):
        if name.startswith("check_") and not ispkg:
            try:
                module = importlib.import_module(f"dcipipelinelint.checks.{name}")
                # Look for a function named 'check' in the module
                if hasattr(module, "check"):
                    checks_list.append(module.check)
            except Exception as e:
                # Log error but continue discovering other checks
                log.warning(f"Failed to import check module {name}: {e}")

    return checks_list
