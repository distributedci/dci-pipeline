#!/usr/bin/env python3
#
# Copyright (C) 2026 Red Hat, Inc.
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

"""dci-github-stream - run DCI jobs from a stream of GitHub events.

The tool reads a stream of GitHub webhook payloads on its standard input,
one JSON object per line, and applies the rules described in a YAML
configuration file to every event. The default configuration file is
/etc/dci-pipeline/github-stream.yml and can be overridden with the
--config option or the GITHUB_STREAM_CONF environment variable.

The configuration is reloaded for every event so that the rules can be
changed without restarting the service reading the stream.

Every rule can run a shell command, post a comment on the pull request or
simply ignore the event. A shell command is executed with bash, and a few
helper functions are available to it:

  send_pending_msg "waiting for a DCI job"
  send_success_msg "SUCCESS"
  send_comment "some text"

Each helper only records the action to perform, and the actions are
replayed through the GitHub API once the command completed, in the order
they were recorded.

Example:

  $ tail -F /var/log/github-stream.log | dci-github-stream --config github-stream.yml

Use --dry-run to print the actions the tool would perform instead of
calling the GitHub API.
"""

import argparse
import json
import logging
import os
import re
import shlex
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

import yaml

LOG = logging.getLogger("dci-github-stream")

STATUS_CONTEXT = "DCI / DCI Job"
STATE_PENDING = "pending"
STATE_SUCCESS = "success"
DEFAULT_PENDING_DESCRIPTION = "waiting for a DCI job"
SUCCESS_DESCRIPTION = "SUCCESS"

DEFAULT_CONFIG_PATH = "/etc/dci-pipeline/github-stream.yml"
CONFIG_ENV = "GITHUB_STREAM_CONF"
TOKEN_ENV = "GITHUB_TOKEN"
TOKEN_CONFIG_PATH = "~/.config/dci-pipeline/config"
ACTIONS_ENV = "DCI_GITHUB_STREAM_ACTIONS"

API_URL = "https://api.github.com"
HTTP_TIMEOUT = 30
DEFAULT_COMMAND_TIMEOUT = 3600
HINT_TIMEOUT = 60
HINT_LIST_COMMAND = ("dci-auto-launch", "--list-sections")

KIND_COMMENT = "issue_comment"
KIND_PULL_REQUEST = "pull_request"

ACTION_RUN = "run"
ACTION_COMMENT = "comment"
ACTION_IGNORE = "ignore"
ACTIONS = (ACTION_RUN, ACTION_COMMENT, ACTION_IGNORE)

STDIN_NONE = "none"
STDIN_PR_BODY = "pr_body"
STDIN_VALUES = (STDIN_NONE, STDIN_PR_BODY)

# Template variables usable in the configuration values, expanded from the
# event being processed.
EVENT_TEMPLATE_VARS = (
    "@url",
    "@repo",
    "@org",
    "@name",
    "@number",
    "@sender",
    "@action",
    "@base_ref",
    "@head_ref",
    "@sha",
    "@hints",
)
# Variables that are expanded by other tools (dci-queue, dci-pipeline-check)
# and must be left untouched.
PASS_THROUGH_VARS = ("@QUEUE", "@RESOURCE")
KNOWN_TEMPLATE_VARS = frozenset(EVENT_TEMPLATE_VARS) | frozenset(PASS_THROUGH_VARS)
TEMPLATE_RE = re.compile(r"@[A-Za-z_][A-Za-z0-9_]*")
_NEVER_MATCH = re.compile(r"(?!)")

# Rule names are quoted in the refusal comments posted on pull requests.
REFUSAL_FORMAT = "{sender} unauthorized to call {command}"
REFUSAL_NO_SENDER_FORMAT = "unauthorized to call {command}: no login found"

TOP_LEVEL_KEYS = ("auth", "commands", "hint_command", "repos")
AUTH_KEYS = ("orgs", "collaborator")
REPO_KEYS = (
    "auth",
    "commands",
    "pending_description",
    "rules",
    "skip",
    "skip_labels",
    "voting",
)
RULE_KEYS = (
    "action",
    "auth",
    "base_ref",
    "command",
    "comment",
    "continue",
    "file_match",
    "ignore_files",
    "ignore_senders",
    "match",
    "match_label",
    "match_pr_body",
    "merged",
    "name",
    "no_match_pr_body",
    "only_if",
    "pending_description",
    "stdin",
)


class ConfigError(Exception):
    """raised when the configuration file is not valid"""


#
# Template expansion
#


_WARNED_TEMPLATES = set()


def check_template(value, where):
    """warn about the @tokens of value that are not known template variables.

    Only the variables of EVENT_TEMPLATE_VARS are expanded, any other
    token is left untouched so that legitimate shell values such as
    quay.io/x/y@sha256:... or ci@redhat.com are accepted verbatim.
    """
    for match in TEMPLATE_RE.finditer(value):
        token = match.group(0)
        if token in KNOWN_TEMPLATE_VARS:
            continue
        key = (where, token)
        if key in _WARNED_TEMPLATES:
            continue
        _WARNED_TEMPLATES.add(key)
        LOG.warning(
            "%s: '%s' is not a known template variable, it is left as is",
            where,
            token,
        )


def render(value, event, hints=()):
    """expand the template variables of value using the event.

    The substitution is done in a single pass, so the values of the event
    are never expanded again and a token that is not a known variable is
    left as is.
    """
    values = {
        "@url": event.get("url") or "",
        "@repo": event.get("repo") or "",
        "@org": event.get("org") or "",
        "@name": event.get("name") or "",
        "@number": str(event.get("number") or ""),
        "@sender": event.get("sender") or "",
        "@action": event.get("action") or "",
        "@base_ref": event.get("base_ref") or "",
        "@head_ref": event.get("head_ref") or "",
        "@sha": event.get("sha") or "",
        "@hints": "|".join(hints),
    }
    return TEMPLATE_RE.sub(
        lambda match: values.get(match.group(0), match.group(0)), value
    )


#
# Event parsing
#


def _login(value):
    "return the login of a GitHub user object"
    if isinstance(value, dict):
        return value.get("login") or ""
    return ""


def _labels(value):
    "return the label names of an issue or pull request object"
    labels = value.get("labels")
    if not isinstance(labels, list):
        return ()
    return tuple(label.get("name") or "" for label in labels if isinstance(label, dict))


def _base_event(payload, repository):
    "build the fields shared by all the events"
    full_name = repository.get("full_name") or ""
    owner = repository.get("owner") or {}
    org = owner.get("login") or (full_name.split("/")[0] if "/" in full_name else "")
    name = repository.get("name") or (full_name.split("/")[-1] if full_name else "")
    return {
        "action": payload.get("action") or "",
        "repo": full_name,
        "org": org,
        "name": name,
        "label": _label_name(payload),
    }


def _label_name(payload):
    "return the label name of a labeled or unlabeled event"
    label = payload.get("label")
    if isinstance(label, dict):
        return label.get("name") or ""
    return ""


def _parse_comment_event(payload):
    "normalize an issue_comment event"
    # Only a new comment triggers anything: an edited or deleted comment
    # still carries its body in the payload and would relaunch the job.
    action = payload.get("action") or ""
    if action != "created":
        LOG.debug("skipping issue_comment event with the action '%s'", action)
        return None
    issue = payload["issue"]
    comment = payload["comment"]
    pull_request = issue.get("pull_request")
    if not isinstance(pull_request, dict) or not pull_request.get("url"):
        LOG.debug("skipping comment on an issue that is not a pull request")
        return None
    body = comment.get("body") or ""
    if not body:
        LOG.debug("skipping comment without a body")
        return None
    repository = payload.get("repository") or {}
    event = _base_event(payload, repository)
    event.update(
        {
            "kind": KIND_COMMENT,
            "body": body,
            "url": pull_request.get("html_url") or "",
            "pulls_url": pull_request.get("url") or "",
            "comments_url": issue.get("comments_url") or "",
            "number": issue.get("number"),
            "labels": _labels(issue),
            "sender": _login(payload.get("sender")),
            "base_ref": "",
            "head_ref": "",
            "sha": "",
            "merged": False,
        }
    )
    return event


def _parse_pull_request_event(payload):
    "normalize a pull_request event"
    pull_request = payload["pull_request"]
    base = pull_request.get("base") or {}
    head = pull_request.get("head") or {}
    repository = payload.get("repository") or base.get("repo") or {}
    if not pull_request.get("url"):
        LOG.debug("skipping pull request event without an API URL")
        return None
    event = _base_event(payload, repository)
    event.update(
        {
            "kind": KIND_PULL_REQUEST,
            "body": pull_request.get("body") or "",
            "url": pull_request.get("html_url") or "",
            "pulls_url": pull_request.get("url") or "",
            "comments_url": pull_request.get("comments_url") or "",
            "number": pull_request.get("number"),
            "labels": _labels(pull_request),
            "sender": _login(payload.get("sender")),
            "base_ref": base.get("ref") or "",
            "head_ref": head.get("ref") or "",
            "sha": head.get("sha") or "",
            "merged": bool(pull_request.get("merged")),
        }
    )
    return event


def parse_event(line):
    """parse one line of the event stream.

    Return a normalized event dictionary or None when the line is not a
    supported event.
    """
    if isinstance(line, bytes):
        line = line.decode("utf-8", errors="replace")
    line = line.strip()
    if not line:
        return None
    try:
        payload = json.loads(line)
    except ValueError as exc:
        LOG.warning("skipping malformed event: %s", exc)
        return None
    if not isinstance(payload, dict):
        LOG.warning("skipping event that is not a JSON object")
        return None
    if isinstance(payload.get("issue"), dict) and isinstance(
        payload.get("comment"), dict
    ):
        return _parse_comment_event(payload)
    if isinstance(payload.get("pull_request"), dict):
        return _parse_pull_request_event(payload)
    LOG.debug("skipping event that is neither a comment nor a pull request event")
    return None


#
# Configuration
#


@dataclass(frozen=True)
class AuthSpec:
    "how the sender of an event is authorized"

    orgs: tuple = ()
    collaborator: bool = False

    @property
    def active(self):
        "return True if the specification restricts anything"
        return bool(self.orgs) or self.collaborator


@dataclass
class Rule:
    "a configuration rule"

    name: str
    index: int
    action: str = ACTION_RUN
    command: Optional[str] = None
    comment: Optional[str] = None
    stdin: str = STDIN_NONE
    pending_description: Optional[str] = None
    continue_after: bool = False
    match: Optional[str] = None
    match_pr_body: Optional[str] = None
    no_match_pr_body: Optional[str] = None
    file_match: Optional[str] = None
    ignore_files: Optional[str] = None
    ignore_senders: tuple = ()
    only_if: Optional[str] = None
    base_ref: Optional[str] = None
    match_label: Optional[str] = None
    merged: Optional[bool] = None
    auth: Optional[AuthSpec] = None


@dataclass
class RepoConfig:
    "the configuration of one repository"

    pattern: str
    regex: re.Pattern
    skip: bool = False
    skip_labels: tuple = ()
    voting: bool = True
    auth: Optional[AuthSpec] = None
    pending_description: str = DEFAULT_PENDING_DESCRIPTION
    commands: dict = field(default_factory=dict)
    rules: tuple = ()


@dataclass
class Config:
    "the whole configuration file"

    path: str
    auth: Optional[AuthSpec] = None
    commands: dict = field(default_factory=dict)
    hint_command: tuple = HINT_LIST_COMMAND
    repos: tuple = ()


def _check_keys(data, allowed, where):
    "raise ConfigError for every key that is not part of the schema"
    for key in data:
        if key not in allowed:
            raise ConfigError(f"{where}: unknown key '{key}'")


def _as_bool(value, where):
    "validate a boolean value"
    if not isinstance(value, bool):
        raise ConfigError(f"{where}: expected a boolean, got {value!r}")
    return value


def _as_str(value, where):
    "validate a string value"
    if not isinstance(value, str):
        raise ConfigError(f"{where}: expected a string, got {value!r}")
    return value


def _as_list(value, where):
    "validate a list value"
    if not isinstance(value, (list, tuple)):
        raise ConfigError(f"{where}: expected a list, got {value!r}")
    return list(value)


def _as_str_list(value, where):
    "validate a list of strings"
    return tuple(_as_str(item, where) for item in _as_list(value, where))


def _compile(pattern, where, what):
    "compile a regular expression of the configuration"
    _as_str(pattern, f"{where}: {what}")
    try:
        return re.compile(pattern, re.IGNORECASE | re.MULTILINE)
    except re.error as exc:
        raise ConfigError(f"{where}: invalid regular expression in {what}: {exc}")


def _load_auth(value, where):
    "validate an auth specification"
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ConfigError(f"{where}: expected a mapping with orgs/collaborator")
    _check_keys(value, AUTH_KEYS, where)
    orgs = _as_str_list(value.get("orgs", ()), f"{where}: orgs")
    collaborator = _as_bool(value.get("collaborator", False), f"{where}: collaborator")
    return AuthSpec(orgs=orgs, collaborator=collaborator)


def _load_commands(value, where):
    "validate the named commands of the configuration"
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{where}: expected a mapping of command name to script")
    commands = {}
    for name, script in value.items():
        _as_str(name, f"{where}: command name")
        commands[name] = _as_str(script, f"{where}: command '{name}'")
        check_template(commands[name], f"{where}: command '{name}'")
    return commands


def _load_rule(index, value, where, commands):
    "validate one rule"
    where = f"{where} rule #{index}"
    if not isinstance(value, dict):
        raise ConfigError(f"{where}: expected a mapping")
    name = value.get("name")
    if name is None:
        raise ConfigError(f"{where}: missing name")
    where = f"{where} ({name})"
    _check_keys(value, RULE_KEYS, where)
    rule = Rule(name=_as_str(name, f"{where}: name"), index=index)
    action = _as_str(value.get("action", ACTION_RUN), f"{where}: action")
    if action not in ACTIONS:
        raise ConfigError(
            f"{where}: unknown action '{action}' (expected one of {', '.join(ACTIONS)})"
        )
    rule.action = action
    if "stdin" in value:
        rule.stdin = _as_str(value["stdin"], f"{where}: stdin")
        if rule.stdin not in STDIN_VALUES:
            raise ConfigError(
                f"{where}: unknown stdin value '{rule.stdin}' "
                f"(expected one of {', '.join(STDIN_VALUES)})"
            )
    if "command" in value:
        rule.command = _as_str(value["command"], f"{where}: command")
        if rule.command not in commands:
            raise ConfigError(f"{where}: unknown command '{rule.command}'")
        if action != ACTION_RUN:
            raise ConfigError(f"{where}: command is only valid for the run action")
    if "comment" in value:
        rule.comment = _as_str(value["comment"], f"{where}: comment")
        check_template(rule.comment, f"{where}: comment")
    if "pending_description" in value:
        rule.pending_description = _as_str(
            value["pending_description"], f"{where}: pending_description"
        )
        check_template(rule.pending_description, f"{where}: pending_description")
    if "continue" in value:
        rule.continue_after = _as_bool(value["continue"], f"{where}: continue")
    if "merged" in value:
        rule.merged = _as_bool(value["merged"], f"{where}: merged")
    if "auth" in value:
        rule.auth = _load_auth(value["auth"], f"{where}: auth")
    if "ignore_senders" in value:
        rule.ignore_senders = _as_str_list(
            value["ignore_senders"], f"{where}: ignore_senders"
        )
    for key, attribute in (
        ("match", "match"),
        ("match_pr_body", "match_pr_body"),
        ("no_match_pr_body", "no_match_pr_body"),
        ("file_match", "file_match"),
        ("ignore_files", "ignore_files"),
        ("only_if", "only_if"),
        ("base_ref", "base_ref"),
        ("match_label", "match_label"),
    ):
        if key in value:
            check_template(_as_str(value[key], f"{where}: {key}"), f"{where}: {key}")
            _compile(value[key], where, key)
            setattr(rule, attribute, value[key])
    if action == ACTION_RUN and not rule.command:
        raise ConfigError(f"{where}: the run action requires a command")
    if action == ACTION_COMMENT and not rule.comment:
        raise ConfigError(f"{where}: the comment action requires a comment")
    return rule


def _load_repo(pattern, value, where, common_commands):
    "validate the configuration of one repository"
    # The pattern is matched against the whole <org>/<repo> name by
    # find_repo(), so "dci-labs/grout" does not capture "dci-labs/grout-config".
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise ConfigError(f"{where}: invalid repository pattern: {exc}")
    if not isinstance(value, dict):
        raise ConfigError(f"{where}: expected a mapping")
    _check_keys(value, REPO_KEYS, where)
    repo = RepoConfig(pattern=pattern, regex=regex)
    if "skip" in value:
        repo.skip = _as_bool(value["skip"], f"{where}: skip")
    if "skip_labels" in value:
        repo.skip_labels = _as_str_list(value["skip_labels"], f"{where}: skip_labels")
    if "voting" in value:
        repo.voting = _as_bool(value["voting"], f"{where}: voting")
    if "pending_description" in value:
        repo.pending_description = _as_str(
            value["pending_description"], f"{where}: pending_description"
        )
        check_template(repo.pending_description, f"{where}: pending_description")
    if "auth" in value:
        repo.auth = _load_auth(value["auth"], f"{where}: auth")
    commands = dict(common_commands)
    if "commands" in value:
        commands.update(_load_commands(value["commands"], f"{where}: commands"))
    repo.commands = commands
    raw_rules = _as_list(value.get("rules", ()), f"{where}: rules")
    rules = []
    for index, raw_rule in enumerate(raw_rules):
        rules.append(_load_rule(index, raw_rule, where, commands))
    repo.rules = tuple(rules)
    if repo.voting and not repo.skip:
        if not any(rule.action == ACTION_RUN for rule in rules):
            raise ConfigError(
                f"{where}: voting is enabled but no rule runs a command, "
                "set voting to false"
            )
    return repo


def load_config(path=None):
    """load and validate the configuration file.

    Raise ConfigError with the file name, the repository pattern and the
    rule index when something is wrong.
    """
    if path is None:
        path = default_config_path()
    path = os.path.expanduser(path)
    try:
        with open(path, encoding="utf-8") as fobj:
            data = yaml.safe_load(fobj)
    except FileNotFoundError:
        raise ConfigError(f"{path}: configuration file not found")
    except OSError as exc:
        raise ConfigError(f"{path}: cannot read the configuration file: {exc}")
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}")
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: the top level must be a mapping")
    _check_keys(data, TOP_LEVEL_KEYS, path)
    config = Config(path=path)
    config.auth = _load_auth(data.get("auth"), f"{path}: auth")
    config.commands = _load_commands(data.get("commands"), f"{path}: commands")
    if "hint_command" in data:
        value = data["hint_command"]
        if isinstance(value, str):
            hint_command = tuple(shlex.split(value))
        else:
            hint_command = _as_str_list(value, f"{path}: hint_command")
        config.hint_command = hint_command
    repos = data.get("repos") or {}
    if not isinstance(repos, dict):
        raise ConfigError(f"{path}: repos must be a mapping")
    config.repos = tuple(
        _load_repo(pattern, value, f"{path}: repository '{pattern}'", config.commands)
        for pattern, value in repos.items()
    )
    return config


def default_config_path():
    "return the configuration file to use"
    return os.environ.get(CONFIG_ENV) or DEFAULT_CONFIG_PATH


_HINTS_CACHE = {}


def list_hints(command=None):
    """return the list of the test hint names.

    The names come from the command given by the hint_command configuration
    key, dci-auto-launch --list-sections by default, and are cached.
    """
    if command is None:
        command = HINT_LIST_COMMAND
    key = (
        tuple(command) if not isinstance(command, str) else tuple(shlex.split(command))
    )
    if key in _HINTS_CACHE:
        return _HINTS_CACHE[key]
    hints = []
    try:
        proc = subprocess.run(
            list(key),
            capture_output=True,
            text=True,
            timeout=HINT_TIMEOUT,
            check=False,
        )
        if proc.returncode != 0:
            LOG.warning(
                "cannot list the test hints with '%s': %s",
                " ".join(key),
                proc.stderr.strip(),
            )
        hints = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.SubprocessError) as exc:
        LOG.error("cannot run '%s': %s", " ".join(key), exc)
    _HINTS_CACHE[key] = hints
    return hints


#
# GitHub API
#


def load_token():
    "read the GitHub token from the environment or from the configuration file"
    token = os.environ.get(TOKEN_ENV)
    if token:
        return token
    try:
        with open(os.path.expanduser(TOKEN_CONFIG_PATH), encoding="utf-8") as fobj:
            for line in fobj:
                line = line.strip()
                if line.startswith(f"{TOKEN_ENV}="):
                    return line.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        return ""
    return ""


class GitHubClient:
    "minimal GitHub API client, errors are logged and never raised"

    def __init__(
        self, token=None, dry_run=False, api_url=API_URL, timeout=HTTP_TIMEOUT
    ):
        self.token = load_token() if token is None else token
        self.dry_run = dry_run
        self.api_url = api_url
        self.timeout = timeout

    def _request(self, method, url, payload=None):
        "perform an API request and return (status code, decoded body)"
        if self.dry_run:
            print(f"+ {method} {url} {json.dumps(payload or {})}", file=sys.stderr)
            return 200, {}
        if not url:
            LOG.error("cannot %s an empty URL", method)
            return 0, {}
        if not self.token:
            LOG.error("%s %s: no GitHub token found", method, url)
            return 0, {}
        data = None
        if payload is not None:
            try:
                data = json.dumps(payload).encode("utf-8")
            except (TypeError, ValueError) as exc:
                LOG.error("%s %s: cannot serialize the payload: %s", method, url, exc)
                return 0, {}
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Accept", "application/vnd.github.v3+json")
        request.add_header("Authorization", f"token {self.token}")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
                return response.status, (json.loads(body) if body.strip() else {})
        except urllib.error.HTTPError as exc:
            LOG.error("%s %s: HTTP %s", method, url, exc.code)
            return exc.code, {}
        except (urllib.error.URLError, OSError, ValueError) as exc:
            LOG.error("%s %s: %s", method, url, exc)
            return 0, {}

    def get_json(self, url):
        "return the decoded body of a GET request"
        _, payload = self._request("GET", url)
        return payload if isinstance(payload, dict) else {}

    def post_comment(self, comments_url, body):
        "comment on a pull request"
        return self._request("POST", comments_url, {"body": body})

    def set_status(self, pulls_url, state, description, context=STATUS_CONTEXT):
        "set the commit status of the head of a pull request"
        payload = {
            "state": state,
            "description": description,
            "context": context,
        }
        if self.dry_run:
            return self._request("POST", pulls_url, payload)
        data = self.get_json(pulls_url)
        statuses_url = data.get("statuses_url")
        if not statuses_url:
            LOG.error(
                "cannot set the status to %s: no statuses_url for %s",
                state,
                pulls_url,
            )
            return 0, {}
        return self._request("POST", statuses_url, payload)

    def get_pr_body(self, pulls_url):
        "return the description of a pull request"
        return self.get_json(pulls_url).get("body") or ""

    def get_pr_files(self, repo, number):
        "return the list of the files changed by a pull request"
        if not repo or not number:
            return ()
        url = f"{self.api_url}/repos/{repo}/pulls/{number}/files"
        payload = self._request("GET", url)[1]
        if not isinstance(payload, list):
            return ()
        return tuple(
            item.get("filename") or "" for item in payload if isinstance(item, dict)
        )

    def is_org_member(self, org, user):
        "return True if the user is a public member of the organization"
        status, _ = self._request("GET", f"{self.api_url}/orgs/{org}/members/{user}")
        return status == 204

    def is_collaborator(self, org, repo, user):
        "return True if the user is a collaborator of the repository"
        status, _ = self._request(
            "GET", f"{self.api_url}/repos/{org}/{repo}/collaborators/{user}"
        )
        return status == 204


class AuthResolver:
    "resolve whether a sender is allowed by an auth specification"

    def __init__(self, client):
        self.client = client
        self.cache = {}

    def allowed(self, spec, org, repo, sender):
        "return True if the sender is allowed by the specification"
        if spec is None or not spec.active:
            return True
        if not sender:
            return False
        # The collaborator check is repository specific, so the cache key
        # must contain the organization and the repository: two
        # repositories configured with the same specification must never
        # share the result of the check.
        key = (spec, org, repo, sender)
        if key in self.cache:
            return self.cache[key]
        if self.client.dry_run:
            LOG.info("dry-run: assuming %s is allowed", sender)
            result = True
        else:
            result = False
            if spec.collaborator and self.client.is_collaborator(org, repo, sender):
                result = True
            if not result:
                for organization in spec.orgs:
                    if self.client.is_org_member(organization, sender):
                        result = True
                        break
        self.cache[key] = result
        return result


#
# Command execution
#


@dataclass
class CommandResult:
    "the result of a command"

    rc: int
    stdout: str = ""
    stderr: str = ""
    actions: tuple = ()
    timed_out: bool = False


BASH_PRELUDE = r"""# dci-github-stream prelude: record the actions to replay later
_dci_json_escape() {
    sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' <<< "${1:-}" \
        | sed -e ':a' -e 'N' -e '$!ba' -e 's/\n/\\n/g'
}

_dci_emit() {
    local kind="${1:-}"
    local msg="${2:-}"
    printf '{"action": "%s", "description": "%s"}\n' \
        "$kind" "$(_dci_json_escape "$msg")" >> "${DCI_GITHUB_STREAM_ACTIONS:?}"
}

send_pending_msg() {
    _dci_emit pending "${1:-}"
}

send_success_msg() {
    _dci_emit success "${1:-}"
}

send_comment() {
    _dci_emit comment "${1:-}"
}
"""


def read_actions(text):
    "decode the actions emitted by a command"
    actions = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            action = json.loads(line)
        except ValueError as exc:
            LOG.warning("ignoring malformed action %r: %s", line, exc)
            continue
        if not isinstance(action, dict) or "action" not in action:
            LOG.warning("ignoring action without an action key: %r", line)
            continue
        actions.append(action)
    return tuple(actions)


class CommandRunner:
    "run the commands of the configuration with bash"

    def __init__(self, timeout=DEFAULT_COMMAND_TIMEOUT):
        self.timeout = timeout

    def command(self, code, timeout=None):
        "run a command without anything on its standard input"
        return self._run(code, None, timeout)

    def command_pr_body(self, code, pr_body, timeout=None):
        "run a command with the description of the pull request on its input"
        return self._run(code, pr_body, timeout)

    def _run(self, code, stdin, timeout):
        script = f"{BASH_PRELUDE}\n{code}\n"
        with tempfile.NamedTemporaryFile(
            mode="w+", prefix="dci-github-stream-", suffix=".jsonl"
        ) as actions_file:
            env = dict(os.environ)
            env[ACTIONS_ENV] = actions_file.name
            LOG.debug("running command: %s", code)
            try:
                proc = subprocess.run(
                    ["bash", "-e", "-c", script],
                    input=stdin,
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=timeout or self.timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                LOG.error("command timed out: %s", code)
                return CommandResult(rc=-1, timed_out=True)
            except OSError as exc:
                LOG.error("cannot run the command %r: %s", code, exc)
                return CommandResult(rc=-1, stderr=str(exc))
            actions_file.seek(0)
            actions = read_actions(actions_file.read())
        result = CommandResult(
            rc=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            actions=actions,
        )
        if result.rc != 0:
            LOG.warning(
                "command %r exited with %s: %s", code, result.rc, result.stderr.strip()
            )
        return result


#
# Rule engine
#


class Engine:
    "apply the configuration to the events"

    def __init__(self, config, client, runner, auth, hints=()):
        self.config = config
        self.client = client
        self.runner = runner
        self.auth = auth
        self.hints = tuple(hints)
        self._pr_body_cache = {}
        self._files_cache = {}
        self._pattern_cache = {}

    def process(self, event):
        "apply the rules of the configuration to an event"
        results = []
        self._pr_body_cache.clear()
        self._files_cache.clear()
        repo = self.find_repo(event)
        if repo is None:
            LOG.debug("no configuration for the repository '%s'", event.get("repo"))
            return results
        if repo.skip:
            LOG.info("%s: ignored by the configuration", event.get("repo"))
            return results
        skip_labels = set(repo.skip_labels)
        if skip_labels and skip_labels.intersection(event.get("labels") or ()):
            LOG.info(
                "%s#%s: ignored because of the label(s) %s",
                event.get("repo"),
                event.get("number"),
                ", ".join(sorted(skip_labels.intersection(event.get("labels") or ()))),
            )
            return results
        for rule in repo.rules:
            if not self.matches(rule, event):
                continue
            if not self.authorized(rule, repo, event):
                return results
            results.extend(self.apply(rule, repo, event))
            if not rule.continue_after:
                break
        return results

    def find_repo(self, event):
        """return the first repository block matching the event.

        The keys of the configuration are regular expressions matched
        against the whole <org>/<repo> name, so that "dci-labs/grout" does
        not capture "dci-labs/grout-config".
        """
        repo_name = event.get("repo") or ""
        for repo in self.config.repos:
            if repo.regex.fullmatch(repo_name):
                return repo
        return None

    def pattern(self, rule, attribute, event):
        "return the regular expression of a selector, expanded for the event"
        source = render(getattr(rule, attribute), event, self.hints)
        key = (attribute, source)
        compiled = self._pattern_cache.get(key)
        if compiled is None:
            try:
                compiled = re.compile(source, re.IGNORECASE | re.MULTILINE)
            except re.error as exc:
                LOG.error(
                    "invalid regular expression '%s' for %s: %s", source, rule.name, exc
                )
                compiled = _NEVER_MATCH
            self._pattern_cache[key] = compiled
        return compiled

    def matches(self, rule, event):
        "return True if all the selectors of the rule match the event"
        sender = (event.get("sender") or "").lower()
        if rule.ignore_senders:
            ignored = {name.lower() for name in rule.ignore_senders}
            if sender in ignored:
                return False
        if rule.only_if is not None and not self.pattern(rule, "only_if", event).search(
            event.get("action") or ""
        ):
            return False
        if rule.base_ref is not None and not self.pattern(
            rule, "base_ref", event
        ).search(event.get("base_ref") or ""):
            return False
        if rule.merged is not None and bool(event.get("merged")) != rule.merged:
            return False
        if rule.match_label is not None:
            label = event.get("label") or ""
            if not label or not self.pattern(rule, "match_label", event).search(label):
                return False
        if rule.match is not None and not self.pattern(rule, "match", event).search(
            event.get("body") or ""
        ):
            return False
        if rule.match_pr_body is not None or rule.no_match_pr_body is not None:
            pr_body = self.pr_body(event)
            if rule.match_pr_body is not None and not self.pattern(
                rule, "match_pr_body", event
            ).search(pr_body):
                return False
            if rule.no_match_pr_body is not None and self.pattern(
                rule, "no_match_pr_body", event
            ).search(pr_body):
                return False
        if rule.file_match is not None or rule.ignore_files is not None:
            files = self.files(event)
            if rule.ignore_files is not None:
                ignore = self.pattern(rule, "ignore_files", event)
                files = [name for name in files if not ignore.search(name)]
            if rule.file_match is not None:
                match = self.pattern(rule, "file_match", event)
                if not any(match.search(name) for name in files):
                    return False
        return True

    def authorized(self, rule, repo, event):
        "check the authorization of the sender of a comment event"
        if event.get("kind") != KIND_COMMENT:
            return True
        spec = rule.auth or repo.auth or self.config.auth
        if spec is None or not spec.active:
            return True
        sender = event.get("sender") or ""
        if self.auth.allowed(spec, event.get("org"), event.get("name"), sender):
            return True
        self.refuse(rule, event, sender)
        return False

    def refuse(self, rule, event, sender):
        "comment on the pull request to explain that the sender is not allowed"
        if sender:
            body = REFUSAL_FORMAT.format(sender=sender, command=rule.name)
        else:
            body = REFUSAL_NO_SENDER_FORMAT.format(command=rule.name)
        LOG.info(
            "%s#%s: refusing %s for %s",
            event.get("repo"),
            event.get("number"),
            rule.name,
            sender or "an unknown sender",
        )
        self.client.post_comment(event.get("comments_url") or "", body)

    def apply(self, rule, repo, event):
        "apply the action of a rule"
        results = [{"rule": rule.name, "action": rule.action}]
        if rule.action == ACTION_IGNORE:
            LOG.debug("%s: nothing to do", rule.name)
            return results
        if rule.action == ACTION_COMMENT:
            self.client.post_comment(
                event.get("comments_url") or "",
                render(rule.comment or "", event, self.hints),
            )
            return results
        if rule.comment:
            self.client.post_comment(
                event.get("comments_url") or "", render(rule.comment, event, self.hints)
            )
        code = render(repo.commands[rule.command], event, self.hints)
        if rule.stdin == STDIN_PR_BODY:
            result = self.runner.command_pr_body(code, self.pr_body(event))
        else:
            result = self.runner.command(code)
        results.append({"rule": rule.name, "action": "command", "rc": result.rc})
        description = self.pending_description(rule, repo, event)
        emitted_success = self.replay(
            rule,
            event,
            result.actions,
            description,
            emit_statuses=repo.voting and result.rc == 0,
        )
        if repo.voting and result.rc == 0 and not emitted_success:
            self.client.set_status(
                event.get("pulls_url") or "", STATE_PENDING, description
            )
            results.append(
                {"rule": rule.name, "action": "status", "state": STATE_PENDING}
            )
        return results

    def pending_description(self, rule, repo, event):
        "return the pending status description of a rule, expanded for the event"
        source = rule.pending_description or repo.pending_description
        return (
            render(source or DEFAULT_PENDING_DESCRIPTION, event, self.hints)
            or DEFAULT_PENDING_DESCRIPTION
        )

    def replay(self, rule, event, actions, description, emit_statuses=True):
        """send the actions recorded by a command, return True if one succeeded.

        The commit statuses are only posted when the command succeeded and
        when the repository is voting, so that a command failing after a
        send_pending_msg cannot leave a permanent pending status. The
        comments are always posted.
        """
        emitted_success = False
        pulls_url = event.get("pulls_url") or ""
        comments_url = event.get("comments_url") or ""
        for action in actions:
            kind = action.get("action")
            text = action.get("description") or ""
            if kind == "pending":
                if emit_statuses:
                    self.client.set_status(
                        pulls_url, STATE_PENDING, text or description
                    )
                else:
                    LOG.debug("not posting the pending status of %s", rule.name)
            elif kind == "success":
                emitted_success = True
                if emit_statuses:
                    self.client.set_status(
                        pulls_url, STATE_SUCCESS, text or SUCCESS_DESCRIPTION
                    )
                else:
                    LOG.debug("not posting the success status of %s", rule.name)
            elif kind == "comment":
                self.client.post_comment(comments_url, text)
            else:
                LOG.warning("ignoring the unknown action '%s' of %s", kind, rule.name)
        return emitted_success

    def pr_body(self, event):
        "return the description of the pull request of the event"
        key = event.get("pulls_url") or ""
        if key not in self._pr_body_cache:
            if event.get("kind") == KIND_PULL_REQUEST:
                body = event.get("body") or ""
            else:
                body = self.client.get_pr_body(key) or ""
            self._pr_body_cache[key] = body
        return self._pr_body_cache[key]

    def files(self, event):
        "return the files changed by the pull request of the event"
        key = event.get("pulls_url") or ""
        if key not in self._files_cache:
            self._files_cache[key] = tuple(
                self.client.get_pr_files(event.get("repo") or "", event.get("number"))
            )
        return self._files_cache[key]


#
# Main loop
#


def process_stream(lines, config_path, client, runner, auth):
    "process a stream of events, never raising for a single event"
    for line in lines:
        event = parse_event(line)
        if event is None:
            continue
        try:
            config = load_config(config_path)
        except ConfigError as exc:
            LOG.error("%s", exc)
            continue
        engine = Engine(config, client, runner, auth, list_hints(config.hint_command))
        try:
            results = engine.process(event)
        except Exception as exc:  # noqa: BLE001 - the stream must survive anything
            LOG.exception("error while processing an event: %s", exc)
            continue
        if results:
            LOG.info(
                "%s#%s: %s",
                event.get("repo"),
                event.get("number"),
                ", ".join(item.get("action", "") for item in results),
            )


def main(argv=None):
    """main entry point"""
    if argv is None:
        argv = sys.argv
    parser = argparse.ArgumentParser(
        prog=os.path.basename(argv[0]),
        description="run DCI jobs from a stream of GitHub events",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--config",
        default=None,
        help=f"configuration file (default: ${CONFIG_ENV} or {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the actions instead of calling the GitHub API",
    )
    parser.add_argument(
        "infile",
        nargs="?",
        type=argparse.FileType("r"),
        default=sys.stdin,
        help="stream of GitHub events, one JSON object per line (default: STDIN)",
    )
    args = parser.parse_args(argv[1:])

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    client = GitHubClient(dry_run=args.dry_run)
    process_stream(
        args.infile,
        args.config,
        client,
        CommandRunner(),
        AuthResolver(client),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

# github_stream.py ends here
