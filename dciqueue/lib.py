# -*- coding: utf-8 -*-
#
# Copyright (C) 2020-2022, 2025 Red Hat, Inc
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

import fcntl
import json
import logging
import os
import sys
import time
from contextlib import contextmanager

log = logging.getLogger(__name__)

DIRS = ("pool", "queue", "available", "log", "reason")
CRONTAB_LINE_FMT = "  *  *  *  *  *         dci-queue%s run %s"
CRONTAB_CLEAN_LINE_FMT = "  @reboot               dci-queue%s clean %s"


@contextmanager
def resource_lock(top_dir):
    """Serialize changes to resource links and availability across pools."""
    with open(os.path.join(top_dir, ".resources.lck"), "a+") as fd:
        fcntl.lockf(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.lockf(fd, fcntl.LOCK_UN)


def resource_path(top_dir, pool, name):
    return os.path.join(top_dir, "pool", pool, name)


def reason_path(top_dir, pool, name):
    return os.path.join(top_dir, "reason", pool, name)


def read_reason(top_dir, pool, name):
    path = reason_path(top_dir, pool, name)
    if not os.path.isfile(path):
        return None
    with open(path) as fd:
        return json.load(fd)


def get_parent(top_dir, pool, name):
    """Return (pool, resource) for an active or soft-removed child."""
    path = resource_path(top_dir, pool, name)
    if os.path.islink(path):
        target = os.path.abspath(os.path.join(os.path.dirname(path), os.readlink(path)))
        parts = os.path.relpath(target, os.path.join(top_dir, "pool")).split(os.sep)
        if len(parts) == 2 and all(part not in (".", "..") for part in parts):
            return tuple(parts)
    reason = read_reason(top_dir, pool, name)
    if reason and isinstance(reason.get("parent"), dict):
        parent = reason["parent"]
        return parent["pool"], parent["resource"]
    return None


def children_of(top_dir, pool, name):
    """Include both active children and children reserved in their own pool."""
    result = set()
    for child_pool in os.listdir(os.path.join(top_dir, "pool")):
        if child_pool == pool:
            continue
        for directory in ("pool", "reason"):
            path = os.path.join(top_dir, directory, child_pool)
            if not os.path.isdir(path):
                continue
            for child in os.listdir(path):
                if get_parent(top_dir, child_pool, child) == (pool, name):
                    result.add((child_pool, child))
    return sorted(result)


def resource_in_use(top_dir, pool, name):
    """Check running bookings, including resources booked as extra pools."""
    queue_root = os.path.join(top_dir, "queue")
    for command_pool in os.listdir(queue_root):
        queue_dir = os.path.join(queue_root, command_pool)
        for filename in os.listdir(queue_dir):
            if not filename.endswith(".exec"):
                continue
            try:
                with open(os.path.join(queue_dir, filename)) as fd:
                    data = json.load(fd)
            except (FileNotFoundError, json.JSONDecodeError):
                continue
            if (name, pool) in (tuple(item) for item in data.get("booked", [])):
                return True
            if command_pool == pool and data.get("resource") == name:
                return True
    return False


def make_available(top_dir, pool, name):
    path = resource_path(top_dir, pool, name)
    link = os.path.join(top_dir, "available", pool, name)
    if (
        os.path.exists(path)
        and not os.path.lexists(link)
        and not resource_in_use(top_dir, pool, name)
    ):
        os.symlink(path, link)


class Seq(object):
    def __init__(self, args):
        self.seqfile = os.path.join(args.top_dir, "queue", args.pool, ".seq")

    def exists(self):
        return os.path.exists(self.seqfile)

    def lock(self):
        self.lock_fd = open(self.seqfile + ".lck", "w")
        while True:
            try:
                fcntl.lockf(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except IOError:
                log.debug("Another instance is already running, waiting 1 sec...")
                time.sleep(1)

    def unlock(self):
        fcntl.lockf(self.lock_fd, fcntl.LOCK_UN)
        self.lock_fd.close()

    def get(self):
        with open(self.seqfile) as f:
            seq = json.load(f)
        log.debug("Read seq file %s: %s" % (self.seqfile, seq))
        return seq["first"], seq["next"]

    def set(self, first, next):
        with open(self.seqfile, "w") as f:
            json.dump({"first": first, "next": next}, f)
        log.debug("Updated seq file %s to %d, %d" % (self.seqfile, first, next))


def get_seq(args):
    seq_obj = Seq(args)
    seq_obj.lock()
    first, next = seq_obj.get()
    seq_obj.unlock()
    return first, next


def check_pool(top_dir, pool):
    for key in ("pool", "queue", "available", "log"):
        d = os.path.join(top_dir, key, pool)
        if not os.path.exists(d):
            msg = "Directory %s doesn't exist. Use add-pool to create it." % (d,)
            log.error(msg)
            print(msg, file=sys.stderr)
            return False
    return True


# lib.py ends here
