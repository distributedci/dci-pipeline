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

import logging
import os

from dciqueue import lib

log = logging.getLogger(__name__)

COMMAND = "add-resource"


def register_command(subparsers):
    parser = subparsers.add_parser(COMMAND, help="Create a new resource in a pool")
    parser.add_argument("pool", help="Name of the pool")
    parser.add_argument("name", help="Name of the resource")
    parser.add_argument("--parent", help="Parent resource as POOL/RESOURCE")
    return COMMAND


def execute_command(args):
    if not lib.check_pool(args.top_dir, args.pool):
        log.error("Pool %s does not exist" % args.pool)
        return 1
    parent = None
    if getattr(args, "parent", None):
        parts = args.parent.split("/")
        if len(parts) != 2 or any(part in ("", ".", "..") for part in parts):
            log.error("Parent must be POOL/RESOURCE")
            return 1
        parent = tuple(parts)
        if not lib.check_pool(args.top_dir, parent[0]):
            return 1

    with lib.resource_lock(args.top_dir):
        return add_resource(args.top_dir, args.pool, args.name, parent)


def add_resource(top_dir, pool, name, parent=None):
    """Add a resource while holding the resource lock."""
    path = lib.resource_path(top_dir, pool, name)
    reason = lib.read_reason(top_dir, pool, name)
    saved_parent = lib.get_parent(top_dir, pool, name)
    if parent and saved_parent and parent != saved_parent:
        log.error("Resource %s/%s already has parent %s/%s", pool, name, *saved_parent)
        return 1
    parent = parent or saved_parent
    if parent:
        if parent[0] == pool or not os.path.exists(lib.resource_path(top_dir, *parent)):
            log.error("Parent %s/%s must exist in another pool", *parent)
            return 1
        if lib.get_parent(top_dir, *parent):
            log.error("A child resource cannot be a parent")
            return 1
        if os.path.lexists(path) and not os.path.islink(path):
            log.error("Resource %s/%s already exists without a parent", pool, name)
            return 1
        if lib.children_of(top_dir, pool, name):
            log.error("A parent resource cannot become a child")
            return 1

    if not os.path.lexists(path):
        if parent:
            target = os.path.relpath(
                lib.resource_path(top_dir, *parent), os.path.dirname(path)
            )
            os.symlink(target, path)
        else:
            open(path, "w").close()

    if reason:
        os.unlink(lib.reason_path(top_dir, pool, name))
    lib.make_available(top_dir, pool, name)

    # Independently reserved children keep their own reason and mapping.
    for child_pool, child in lib.children_of(top_dir, pool, name):
        child_reason = lib.read_reason(top_dir, child_pool, child)
        if child_reason and child_reason.get("removed_by_parent"):
            add_resource(top_dir, child_pool, child)
        elif os.path.islink(lib.resource_path(top_dir, child_pool, child)):
            lib.make_available(top_dir, child_pool, child)
    return 0


# add_resource_cmd.py ends here
