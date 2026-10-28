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

import json
import logging
import os
import subprocess
import sys

from dciqueue import lib, remove_resource_cmd

if sys.version_info[0] == 2:
    FileNotFoundError = OSError

log = logging.getLogger(__name__)

COMMAND = "run"

EXT = ".exec"
RET_CODE = {}


def register_command(subparsers):
    parser = subparsers.add_parser(COMMAND, help="Run a command from a pool")
    parser.add_argument("pool", help="Name of the pool")
    parser.add_argument(
        "-C",
        "--command-output",
        action="store_true",
        help="Command output to the console",
    )
    return COMMAND


def execute_command(args):
    if not lib.check_pool(args.top_dir, args.pool):
        return 1

    commands = []
    removal_failed = False
    skipped_jobs = set()  # Track jobs that have been skipped to avoid infinite loop

    while True:
        booked_resources = []

        # First, peek at the next job to check resource requirements
        to_exec, idx = peek_next_command(args)

        if not to_exec:
            log.debug("No command to run in pool %s" % args.pool)
            break
        else:
            # Check if we've already skipped this job to avoid infinite loop
            if idx in skipped_jobs:
                log.debug("All remaining jobs have been skipped, breaking loop")
                break

            with open(to_exec) as f:
                data = json.load(f)

            log.debug("Checking command %s" % data)

            # Check if extra resources are available BEFORE booking any resources
            extra_resources_available = True
            for pool in data["extra_pools"]:
                if not has_available_resource(args.top_dir, pool):
                    log.debug("No available resource in pool %s" % pool)
                    extra_resources_available = False
                    break

            # If extra resources are not available, skip this job
            if not extra_resources_available:
                log.debug("Skipping job due to unavailable extra resources")
                skipped_jobs.add(idx)
                continue

            # Keep booking and its .exec record together. Parent removal cannot
            # restore a child between taking its link and recording its booking.
            with lib.resource_lock(args.top_dir):
                res = _book_resource(args.top_dir, args.pool)
                if res is None:
                    log.debug("No available resource anymore in pool %s" % args.pool)
                    break
                booked_resources.append((res, args.pool))

                extra_booking_failed = False
                for pool in data["extra_pools"]:
                    extra_res = _book_resource(args.top_dir, pool)
                    if extra_res is None:
                        log.debug("No available resource anymore in pool %s" % pool)
                        for name, booked_pool in booked_resources:
                            lib.make_available(args.top_dir, booked_pool, name)
                        extra_booking_failed = True
                        break
                    booked_resources.append((extra_res, pool))

                if not extra_booking_failed:
                    to_exec, command_idx = get_command(args, expected_idx=idx)
                    if to_exec is None:
                        for name, booked_pool in booked_resources:
                            lib.make_available(args.top_dir, booked_pool, name)
                    else:
                        idx = command_idx
                        data["real_cmd"] = [
                            c.replace("@RESOURCE", res) for c in data["cmd"]
                        ]
                        data["resource"] = res
                        data["jobid"] = idx
                        data["booked"] = booked_resources
                        parents = [
                            lib.get_parent(args.top_dir, pool, name)
                            for name, pool in booked_resources
                        ]
                        with open(to_exec, "w") as f:
                            json.dump(data, f)

            if extra_booking_failed:
                skipped_jobs.add(idx)
                continue
            if to_exec is None:
                continue

            if data.get("remove"):
                reason = data.get("remove_reason")
                if remove_resource_cmd.remove_resource(
                    args.top_dir,
                    args.pool,
                    res,
                    reason if reason is not None else "",
                    force=reason is None,
                ):
                    log.error(
                        "Unable to remove resource %s from pool %s", res, args.pool
                    )
                    free_resources(booked_resources, args.top_dir)
                    os.remove(to_exec)
                    free_resources(booked_resources, args.top_dir)
                    removal_failed = True
                    continue

            out_fd = None
            try:
                log.info("Running command %s (wd: %s)" % (data["cmd"], data["wd"]))
                os.chdir(data["wd"])
                job_env = os.environ.copy()
                job_env["DCI_QUEUE"] = args.pool
                job_env["DCI_QUEUE_RES"] = res
                job_env["DCI_QUEUE_ID"] = str(idx)
                job_env["DCI_QUEUE_JOBID"] = "%s.%d" % (args.pool, idx)
                for key in list(job_env):
                    if key.startswith("DCI_QUEUE_PARENT"):
                        del job_env[key]
                num = 1
                for (r, p), parent in zip(booked_resources, parents):
                    job_env[f"DCI_QUEUE{num}"] = p
                    job_env[f"DCI_QUEUE_RES{num}"] = r
                    if parent:
                        job_env[f"DCI_QUEUE_PARENT{num}"] = parent[0]
                        job_env[f"DCI_QUEUE_PARENT_RES{num}"] = parent[1]
                        if num == 1:
                            job_env["DCI_QUEUE_PARENT"] = parent[0]
                            job_env["DCI_QUEUE_PARENT_RES"] = parent[1]
                    num += 1
                if not args.command_output:
                    out_fd = open(
                        os.path.join(args.top_dir, "log", args.pool, str(idx)), "w"
                    )
                    # log environment variables
                    out_fd.write(f'+ DCI_QUEUE={job_env["DCI_QUEUE"]}\n')
                    out_fd.write(f'+ DCI_QUEUE_RES={job_env["DCI_QUEUE_RES"]}\n')
                    out_fd.write(f'+ DCI_QUEUE_ID={job_env["DCI_QUEUE_ID"]}\n')
                    out_fd.write(f'+ DCI_QUEUE_JOBID={job_env["DCI_QUEUE_JOBID"]}\n')
                    for env_idx in range(1, num):
                        out_fd.write(
                            f'+ DCI_QUEUE{env_idx}={job_env[f"DCI_QUEUE{env_idx}"]}\n'
                        )
                        out_fd.write(
                            f'+ DCI_QUEUE_RES{env_idx}={job_env[f"DCI_QUEUE_RES{env_idx}"]}\n'
                        )
                        if f"DCI_QUEUE_PARENT{env_idx}" in job_env:
                            parent_pool = job_env[f"DCI_QUEUE_PARENT{env_idx}"]
                            parent_res = job_env[f"DCI_QUEUE_PARENT_RES{env_idx}"]
                            out_fd.write(f"+ DCI_QUEUE_PARENT{env_idx}={parent_pool}\n")
                            out_fd.write(
                                f"+ DCI_QUEUE_PARENT_RES{env_idx}={parent_res}\n"
                            )
                    out_fd.write("+ cd " + data["wd"] + "\n")
                    out_fd.write("+ " + " ".join(data["real_cmd"]) + "\n")
                    out_fd.flush()
                    proc = subprocess.Popen(
                        data["real_cmd"], stdout=out_fd, stderr=out_fd, env=job_env
                    )
                else:
                    out_fd = None
                    proc = subprocess.Popen(data["real_cmd"], env=job_env)
                if proc:
                    data["pid"] = proc.pid
                    commands.append(
                        [booked_resources, proc, out_fd, data["real_cmd"], idx, to_exec]
                    )
                with lib.resource_lock(args.top_dir):
                    with open(to_exec, "w") as f:
                        json.dump(data, f)
            except Exception:
                log.exception("Unable to execute command")
                if out_fd:
                    out_fd.close()
                log.debug("Removing %s" % to_exec)
                os.remove(to_exec)
                free_resources(booked_resources, args.top_dir)

    if commands != []:
        log.info("Waiting for commands: %s" % commands)

        number = len(commands)
        while number > 0:
            log.debug("Waiting %d commands" % number)
            status = os.wait()
            for booked, proc, fd, cmd, idx, to_exec in commands:
                if proc and proc.pid == status[0]:
                    number -= 1
                    break
            else:
                continue
            if proc:
                proc.wait()
                if fd:
                    fd.close()
                log.info("%s returned %d" % (cmd, os.WEXITSTATUS(status[1])))
                RET_CODE[idx] = os.WEXITSTATUS(status[1])
                log.debug("Removing %s" % to_exec)
                try:
                    os.remove(to_exec)
                except FileNotFoundError:
                    pass
            if booked != [] and args:
                free_resources(booked, args.top_dir)
    return 1 if removal_failed else 0


def book_resource(top_dir, pool):
    """Book a resource from the pool.

    Removing the first symlink from the available directory.
    """
    with lib.resource_lock(top_dir):
        return _book_resource(top_dir, pool)


def _book_resource(top_dir, pool):
    """Book a resource while holding the resource lock."""
    available_dir = os.path.join(top_dir, "available", pool)
    for res in os.listdir(available_dir):
        filename = os.path.join(available_dir, res)
        if os.path.islink(filename) and os.path.exists(filename):
            os.unlink(filename)
            return res
    return None


def free_resource(res, top_dir, pool):
    try:
        with lib.resource_lock(top_dir):
            lib.make_available(top_dir, pool, res)
    except FileNotFoundError:
        # The queue itself may have been removed while a job was finishing.
        if os.path.isdir(top_dir):
            raise


def free_resources(resources, top_dir):
    log.debug("Freeing resources: %s" % resources)
    for r, pool in resources:
        free_resource(r, top_dir, pool)


def peek_next_command(args):
    """Peek at the next command without consuming it from the queue."""
    seq = lib.Seq(args)

    seq.lock()
    first, next = seq.get()

    to_exec = None
    index = None
    pri = -1
    # first pass to find the highest priority job
    for idx in range(first, next):
        cmdfile = os.path.join(args.top_dir, "queue", args.pool, str(idx))
        if os.path.exists(cmdfile):
            log.debug("getting priority for %s" % cmdfile)
            with open(cmdfile) as cmdfd:
                data = json.load(cmdfd)
                priority = data["priority"] if "priority" in data else 0
                if priority > pri:
                    log.debug("top priority so far %s => %d" % (cmdfile, priority))
                    index = idx
                    pri = priority
    if index is not None:
        cmdfile = os.path.join(args.top_dir, "queue", args.pool, str(index))
        to_exec = cmdfile  # Don't move the file, just return the path

    seq.unlock()
    log.debug("peek_next_command %s %s" % (to_exec, index))
    return to_exec, index


def has_available_resource(top_dir, pool):
    """Check if there's at least one available resource in the pool."""
    available_dir = os.path.join(top_dir, "available", pool)
    if not os.path.exists(available_dir):
        return False

    resources = [
        f
        for f in os.listdir(available_dir)
        if os.path.islink(os.path.join(available_dir, f))
        and os.path.exists(os.path.join(available_dir, f))
    ]
    return len(resources) > 0


def get_command(args, expected_idx=None):
    """Get the next command to execute from the queue."""
    seq = lib.Seq(args)

    seq.lock()
    first, next = seq.get()

    to_exec = None
    index = None
    pri = -1
    if expected_idx is not None:
        cmdfile = os.path.join(args.top_dir, "queue", args.pool, str(expected_idx))
        if os.path.exists(cmdfile):
            index = expected_idx
    else:
        # first pass to find the highest priority job
        for idx in range(first, next):
            cmdfile = os.path.join(args.top_dir, "queue", args.pool, str(idx))
            if os.path.exists(cmdfile):
                log.debug("getting priority for %s" % cmdfile)
                with open(cmdfile) as cmdfd:
                    data = json.load(cmdfd)
                    priority = data["priority"] if "priority" in data else 0
                    if priority > pri:
                        log.debug("top priority so far %s => %d" % (cmdfile, priority))
                        index = idx
                        pri = priority
    if index is not None:
        cmdfile = os.path.join(args.top_dir, "queue", args.pool, str(index))
        movedfile = cmdfile + EXT
        os.rename(cmdfile, movedfile)
        to_exec = movedfile
        if index == first:
            seq.set(index + 1, next)

    seq.unlock()
    log.debug("get_command %s %s" % (to_exec, index))
    return to_exec, index


# run_cmd.py ends here
