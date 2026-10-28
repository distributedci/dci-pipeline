# -*- coding: utf-8 -*-
#
# Copyright (C) 2020-2025 Red Hat, Inc
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations

""" """

import datetime
import errno
import json
import logging
import os
import subprocess
import sys

from dciqueue import lib

log = logging.getLogger(__name__)

COMMAND = "remove-resource"


def register_command(subparsers):
    parser = subparsers.add_parser(COMMAND, help="Remove a resource from a pool")
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force the removal of the resource from the pool",
    )
    parser.add_argument("pool", help="Name of the pool")
    parser.add_argument("name", help="Name of the resource")
    parser.add_argument("reason", help="Reason of the removal")
    return COMMAND


def execute_command(args):
    return remove_resource(
        args.top_dir, args.pool, args.name, args.reason, force=args.force
    )


def remove_resource(top_dir, pool, name, reason, force=False):
    if not lib.check_pool(top_dir, pool):
        log.error("Pool %s does not exist" % pool)
        return 1

    if not force and (not isinstance(reason, str) or not reason.strip()):
        msg = "A non-empty reason is required to remove a resource."
        log.error(msg)
        print(msg, file=sys.stderr)
        return 1

    with lib.resource_lock(top_dir):
        return _remove_resource(top_dir, pool, name, reason, force)


def _remove_resource(top_dir, pool, name, reason, force=False, removed_by_parent=False):
    """Remove a resource and its children while holding the resource lock."""
    path = lib.resource_path(top_dir, pool, name)
    if not force and not os.path.exists(path):
        msg = "Trying to remove resource %s that does not exist." % name
        log.error(msg)
        print(msg, file=sys.stderr)
        return 1

    children = lib.children_of(top_dir, pool, name)
    parent = lib.get_parent(top_dir, pool, name)

    if not force and not removed_by_parent:
        prefix = ""
        if os.environ.get("TMUX"):
            prefix = subprocess.check_output(
                "tmux display-message -p '#S: '||:",
                stderr=subprocess.DEVNULL,
                shell=True,
                universal_newlines=True,
            ).strip("\n")
        reason = prefix + reason

    for child_pool, child in children:
        # An independently reserved child stays reserved on soft removal.
        if force or not lib.read_reason(top_dir, child_pool, child):
            _remove_resource(top_dir, child_pool, child, reason, force, not force)

    for key in ("available", "pool"):
        entry = os.path.join(top_dir, key, pool, name)
        if os.path.lexists(entry):
            os.unlink(entry)

    reason_dir = os.path.join(top_dir, "reason", pool)
    try:
        os.makedirs(reason_dir)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    reason_path = lib.reason_path(top_dir, pool, name)
    if force:
        if os.path.exists(reason_path):
            os.unlink(reason_path)
    else:
        data = {
            "reason": reason,
            "pool": pool,
            "resource": name,
            "date": str(datetime.datetime.now()),
        }
        if parent:
            data["parent"] = {"pool": parent[0], "resource": parent[1]}
        if removed_by_parent:
            data["removed_by_parent"] = True
        with open(reason_path, "w") as fd:
            json.dump(data, fd)

    return 0


# remove_resource_cmd.py ends here
