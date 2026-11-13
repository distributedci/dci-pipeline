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

"""tests for dci-github-stream

The GitHub client, the command runner and the authorization resolver are
replaced by fakes so that the tests never touch the network nor run a
command, except for the tests of the command runner itself.
"""

import json
import pathlib

import pytest
import yaml

from dcipipeline import github_stream

PR_URL = "https://api.github.com/repos/dci-labs/grout/pulls/42"
PR_HTML_URL = "https://github.com/dci-labs/grout/pull/42"
COMMENTS_URL = f"{PR_URL}/comments"
REPO = "dci-labs/grout"


#
# fakes
#


class FakeClient:
    "fake GitHub client recording the calls"

    dry_run = False

    def __init__(self, pr_body="", files=(), member_orgs=(), collaborators=()):
        self.calls = []
        self.reads = []
        self.pr_body = pr_body
        self.files = tuple(files)
        self.member_orgs = set(member_orgs)
        self.collaborators = set(collaborators)

    def post_comment(self, comments_url, body):
        self.calls.append(("comment", comments_url, body))
        return 201, {}

    def set_status(self, pulls_url, state, description, context=None):
        self.calls.append(("status", state, description))
        return 201, {}

    def get_pr_body(self, pulls_url):
        self.reads.append(("get_pr_body", pulls_url))
        return self.pr_body

    def get_pr_files(self, repo, number):
        self.reads.append(("get_pr_files", repo, number))
        return self.files

    def is_org_member(self, org, user):
        self.reads.append(("is_org_member", org, user))
        return (org, user) in self.member_orgs

    def is_collaborator(self, org, repo, user):
        self.reads.append(("is_collaborator", org, repo, user))
        return (org, repo, user) in self.collaborators

    def kinds(self):
        "return the kinds of the recorded calls"
        return [call[0] for call in self.calls]

    def read_kinds(self):
        "return the kinds of the recorded reads"
        return [call[0] for call in self.reads]


class FakeRunner:
    "fake command runner returning scripted results"

    def __init__(self, results=None):
        self.results = list(results or [])
        self.calls = []

    def _next(self):
        if self.results:
            return self.results.pop(0)
        return github_stream.CommandResult(rc=0)

    def command(self, code, timeout=None):
        self.calls.append((code, None))
        return self._next()

    def command_pr_body(self, code, pr_body, timeout=None):
        self.calls.append((code, pr_body))
        return self._next()


class FakeAuth:
    "fake authorization resolver"

    def __init__(self, allowed=True):
        self.value = allowed
        self.requests = []

    def allowed(self, spec, org, repo, sender):
        self.requests.append((spec, org, repo, sender))
        return self.value


#
# helpers
#


def repo_payload(repo=REPO):
    "return the repository part of a payload"
    org, name = repo.split("/")
    return {"full_name": repo, "name": name, "owner": {"login": org}}


def comment_payload(
    body="/dci-rerun",
    repo=REPO,
    sender="alice",
    action="created",
    labels=(),
):
    "build an issue_comment payload"
    return {
        "action": action,
        "comment": {"body": body},
        "issue": {
            "number": 42,
            "comments_url": COMMENTS_URL,
            "pull_request": {"url": PR_URL, "html_url": PR_HTML_URL},
            "labels": [{"name": label} for label in labels],
        },
        "repository": repo_payload(repo),
        "sender": {"login": sender} if sender is not None else {},
    }


def pr_payload(
    action="opened",
    repo=REPO,
    body="",
    base_ref="main",
    sender="alice",
    labels=(),
    merged=False,
    label=None,
    number=42,
):
    "build a pull_request payload"
    payload = {
        "action": action,
        "pull_request": {
            "number": number,
            "html_url": PR_HTML_URL,
            "url": PR_URL,
            "comments_url": COMMENTS_URL,
            "body": body,
            "base": {"ref": base_ref, "repo": repo_payload(repo)},
            "head": {"ref": "feature", "sha": "deadbeef"},
            "labels": [{"name": item} for item in labels],
            "merged": merged,
        },
        "repository": repo_payload(repo),
        "sender": {"login": sender},
    }
    if label is not None:
        payload["label"] = {"name": label}
    return payload


def make_event(payload):
    "parse a payload the way the stream does"
    return github_stream.parse_event(json.dumps(payload))


def write_config(tmp_path, text, name="github-stream.yml"):
    "write a configuration file and return its path"
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def build(tmp_path, text, client=None, runner=None, auth=None, hints=()):
    "build an engine from a configuration text"
    config = github_stream.load_config(str(write_config(tmp_path, text)))
    client = client if client is not None else FakeClient()
    runner = runner if runner is not None else FakeRunner()
    auth = auth if auth is not None else FakeAuth()
    engine = github_stream.Engine(config, client, runner, auth, hints)
    return engine, client, runner, auth


SIMPLE_CONFIG = """
commands:
  launch: dci-auto-launch @url
  no-check: |
    send_pending_msg "waiting for a DCI job"
    send_success_msg "SUCCESS"
    send_comment "no check (not a code change)"
repos:
  "dci-labs/grout":
    voting: true
    rules:
      - name: dci-rerun
        match: '(?i)^\\s*/dci-rerun'
        action: run
        command: launch
        stdin: pr_body
"""


#
# AC1: event parsing
#


def test_parse_comment_event():
    event = make_event(comment_payload(body="recheck", sender="alice"))
    assert event["kind"] == github_stream.KIND_COMMENT
    assert event["repo"] == REPO
    assert event["org"] == "dci-labs"
    assert event["name"] == "grout"
    assert event["number"] == 42
    assert event["body"] == "recheck"
    assert event["url"] == PR_HTML_URL
    assert event["pulls_url"] == PR_URL
    assert event["comments_url"] == COMMENTS_URL
    assert event["sender"] == "alice"
    assert event["action"] == "created"


def test_parse_pull_request_event():
    event = make_event(pr_payload(body="TestLab: ocp", action="synchronize"))
    assert event["kind"] == github_stream.KIND_PULL_REQUEST
    assert event["repo"] == REPO
    assert event["action"] == "synchronize"
    assert event["body"] == "TestLab: ocp"
    assert event["base_ref"] == "main"
    assert event["head_ref"] == "feature"
    assert event["sha"] == "deadbeef"
    assert event["labels"] == ()


def test_parse_event_skips_malformed_lines():
    assert github_stream.parse_event("not json") is None
    assert github_stream.parse_event("[1, 2, 3]") is None
    assert github_stream.parse_event("") is None
    assert github_stream.parse_event("{}") is None
    assert github_stream.parse_event(json.dumps({"action": "created"})) is None
    # a comment on an issue that is not a pull request
    payload = comment_payload()
    del payload["issue"]["pull_request"]
    assert github_stream.parse_event(json.dumps(payload)) is None
    # a pull request event without an API URL
    payload = pr_payload()
    del payload["pull_request"]["url"]
    assert github_stream.parse_event(json.dumps(payload)) is None


def test_parse_event_accepts_bytes():
    event = github_stream.parse_event(json.dumps(comment_payload()).encode())
    assert event["body"] == "/dci-rerun"


def test_parse_event_skips_edited_and_deleted_comments():
    for action in ("edited", "deleted"):
        payload = comment_payload(body="/dci-rerun", action=action)
        assert github_stream.parse_event(json.dumps(payload)) is None


def test_edited_comment_does_not_dispatch_a_job(tmp_path):
    text = "hint_command: ['true']\n" + SIMPLE_CONFIG
    path = write_config(tmp_path, text)
    client = FakeClient()
    runner = FakeRunner()
    events = [
        json.dumps(comment_payload(body="/dci-rerun", action=action))
        for action in ("edited", "deleted")
    ]
    github_stream.process_stream(events, str(path), client, runner, FakeAuth())
    assert runner.calls == []
    assert client.calls == []


#
# AC3: strict configuration
#


def test_config_rejects_unknown_top_level_key(tmp_path):
    path = write_config(tmp_path, "unknown: 1\n")
    with pytest.raises(github_stream.ConfigError) as excinfo:
        github_stream.load_config(str(path))
    assert "unknown key 'unknown'" in str(excinfo.value)
    assert str(path) in str(excinfo.value)


def test_config_rejects_unknown_repo_key(tmp_path):
    text = "repos:\n  'dci-labs/grout':\n    unknown: 1\n"
    path = write_config(tmp_path, text)
    with pytest.raises(github_stream.ConfigError) as excinfo:
        github_stream.load_config(str(path))
    assert "dci-labs/grout" in str(excinfo.value)
    assert "unknown key 'unknown'" in str(excinfo.value)


def test_config_rejects_unknown_rule_key_and_names_the_rule(tmp_path):
    text = """
repos:
  "dci-labs/grout":
    skip: true
    rules:
      - name: first
        action: ignore
      - name: culprit
        action: ignore
        unknown: 1
"""
    path = write_config(tmp_path, text)
    with pytest.raises(github_stream.ConfigError) as excinfo:
        github_stream.load_config(str(path))
    message = str(excinfo.value)
    assert "rule #1" in message
    assert "culprit" in message


def test_config_rejects_unknown_command(tmp_path):
    text = """
repos:
  "dci-labs/grout":
    voting: false
    rules:
      - name: recheck
        action: run
        command: missing
"""
    path = write_config(tmp_path, text)
    with pytest.raises(github_stream.ConfigError) as excinfo:
        github_stream.load_config(str(path))
    assert "unknown command 'missing'" in str(excinfo.value)


def test_config_rejects_bad_regex(tmp_path):
    text = """
repos:
  "dci-labs/grout":
    voting: false
    rules:
      - name: recheck
        match: '([a-z'
        action: ignore
"""
    path = write_config(tmp_path, text)
    with pytest.raises(github_stream.ConfigError) as excinfo:
        github_stream.load_config(str(path))
    assert "invalid regular expression" in str(excinfo.value)


def test_config_rejects_unknown_action(tmp_path):
    text = """
repos:
  "dci-labs/grout":
    voting: false
    rules:
      - name: recheck
        action: explode
"""
    path = write_config(tmp_path, text)
    with pytest.raises(github_stream.ConfigError) as excinfo:
        github_stream.load_config(str(path))
    assert "unknown action 'explode'" in str(excinfo.value)


def test_config_rejects_malformed_auth(tmp_path):
    text = """
auth:
  group: dci-labs
repos: {}
"""
    path = write_config(tmp_path, text)
    with pytest.raises(github_stream.ConfigError) as excinfo:
        github_stream.load_config(str(path))
    assert "unknown key 'group'" in str(excinfo.value)

    text = """
auth:
  orgs: dci-labs
repos: {}
"""
    path = write_config(tmp_path, text)
    with pytest.raises(github_stream.ConfigError) as excinfo:
        github_stream.load_config(str(path))
    assert "expected a list" in str(excinfo.value)


def test_config_accepts_at_tokens_that_are_not_templates(tmp_path):
    text = """
commands:
  digest: podman pull quay.io/x/y@sha256:abc123
  email: git -c user.email=ci@redhat.com commit -m @url
repos:
  "dci-labs/grout":
    voting: false
    rules:
      - name: recheck
        action: run
        command: digest
      - name: mail
        action: run
        command: email
"""
    config = github_stream.load_config(str(write_config(tmp_path, text)))
    commands = config.repos[0].commands
    assert commands["digest"] == "podman pull quay.io/x/y@sha256:abc123"
    assert commands["email"].startswith("git -c user.email=ci@redhat.com")


def test_render_only_expands_the_known_variables():
    event = {"url": "u", "sha": "deadbeef", "org": "dci-labs"}
    rendered = github_stream.render(
        "pull quay.io/x/y@sha256:abc && echo @sha @org @nope ci@redhat.com", event
    )
    assert rendered == (
        "pull quay.io/x/y@sha256:abc && echo deadbeef dci-labs @nope ci@redhat.com"
    )


def test_config_accepts_pass_through_variables(tmp_path):
    text = """
commands:
  launch: dci-queue schedule mypool -- env TOKEN=@RESOURCE dci-pipeline-check @url -p @QUEUE
repos:
  "dci-labs/grout":
    voting: false
    rules:
      - name: recheck
        action: run
        command: launch
"""
    config = github_stream.load_config(str(write_config(tmp_path, text)))
    assert config.repos[0].commands["launch"].startswith("dci-queue schedule")


def test_config_rejects_voting_without_effect(tmp_path):
    text = """
repos:
  "dci-labs/grout":
    rules:
      - name: recheck
        action: comment
        comment: hello
"""
    path = write_config(tmp_path, text)
    with pytest.raises(github_stream.ConfigError) as excinfo:
        github_stream.load_config(str(path))
    assert "voting is enabled but no rule runs a command" in str(excinfo.value)


def test_config_rejects_missing_file(tmp_path):
    with pytest.raises(github_stream.ConfigError) as excinfo:
        github_stream.load_config(str(tmp_path / "missing.yml"))
    assert "configuration file not found" in str(excinfo.value)


def test_config_rejects_invalid_yaml(tmp_path):
    path = write_config(tmp_path, "repos: [\n")
    with pytest.raises(github_stream.ConfigError) as excinfo:
        github_stream.load_config(str(path))
    assert "invalid YAML" in str(excinfo.value)


def test_config_parses_hint_command(tmp_path):
    text = """
hint_command: "printf 'Lab\\nWorkload\\n'"
repos: {}
"""
    config = github_stream.load_config(str(write_config(tmp_path, text)))
    assert config.hint_command == ("printf", "Lab\nWorkload\n")


def test_config_default_hint_command(tmp_path):
    config = github_stream.load_config(str(write_config(tmp_path, "repos: {}\n")))
    assert config.hint_command == github_stream.HINT_LIST_COMMAND


def test_load_config_uses_environment(tmp_path, monkeypatch):
    path = write_config(tmp_path, "repos: {}\n")
    monkeypatch.setenv(github_stream.CONFIG_ENV, str(path))
    assert github_stream.load_config().path == str(path)


#
# AC4/AC5: rule and repository ordering
#


FIRST_MATCH_CONFIG = """
commands:
  first: echo first
  second: echo second
repos:
  "dci-labs/grout":
    voting: false
    rules:
      - name: first
        match: recheck
        action: run
        command: first
      - name: second
        match: recheck
        action: run
        command: second
"""

CONTINUE_CONFIG = """
commands:
  first: echo first
  second: echo second
repos:
  "dci-labs/grout":
    voting: false
    rules:
      - name: first
        match: recheck
        action: run
        command: first
        continue: true
      - name: second
        match: recheck
        action: run
        command: second
"""


def test_first_match_wins(tmp_path):
    engine, client, runner, _ = build(tmp_path, FIRST_MATCH_CONFIG)
    engine.process(make_event(comment_payload(body="recheck")))
    assert runner.calls == [("echo first", None)]


def test_continue_runs_the_next_rules(tmp_path):
    engine, client, runner, _ = build(tmp_path, CONTINUE_CONFIG)
    engine.process(make_event(comment_payload(body="recheck")))
    assert runner.calls == [("echo first", None), ("echo second", None)]


def test_first_matching_repository_wins(tmp_path):
    text = """
commands:
  first: echo first
  second: echo second
repos:
  "dci-labs/.*":
    voting: false
    rules:
      - name: first
        action: run
        command: first
  "dci-labs/grout":
    voting: false
    rules:
      - name: second
        action: run
        command: second
"""
    engine, _, runner, _ = build(tmp_path, text)
    engine.process(make_event(comment_payload()))
    assert runner.calls == [("echo first", None)]


def test_repo_skip_is_evaluated_before_the_rules(tmp_path):
    text = """
repos:
  "dci-labs/grout":
    skip: true
    rules:
      - name: recheck
        action: ignore
"""
    engine, client, runner, auth = build(tmp_path, text)
    assert engine.process(make_event(comment_payload())) == []
    assert client.calls == []
    assert runner.calls == []
    assert auth.requests == []


def test_repo_skip_labels(tmp_path):
    text = """
commands:
  launch: echo launch
repos:
  "dci-labs/grout":
    voting: false
    skip_labels: [dci-disable]
    rules:
      - name: recheck
        action: run
        command: launch
"""
    engine, client, runner, _ = build(tmp_path, text)
    assert engine.process(make_event(parallel_payload(labels=("dci-disable",)))) == []
    assert runner.calls == []
    engine.process(make_event(parallel_payload(labels=("other",))))
    assert runner.calls == [("echo launch", None)]


def parallel_payload(labels=()):
    "return a pull request payload with labels"
    return pr_payload(body="recheck", labels=labels)


def test_unconfigured_repository_is_ignored(tmp_path):
    engine, client, runner, _ = build(tmp_path, SIMPLE_CONFIG)
    assert engine.process(make_event(comment_payload(repo="someone/else"))) == []
    assert client.calls == []


def test_catch_all_organization_pattern(tmp_path):
    text = """
repos:
  "dci-labs/grout":
    voting: false
    rules:
      - name: recheck
        action: ignore
  "(dci-labs|distributedci)/.*":
    skip: true
"""
    engine, _, _, _ = build(tmp_path, text)
    assert engine.find_repo(
        make_event(comment_payload(repo="distributedci/other"))
    ).skip
    assert engine.find_repo(
        make_event(comment_payload(repo="dci-labs/grout"))
    ).pattern == ("dci-labs/grout")


def test_repository_keys_must_match_the_whole_name(tmp_path):
    text = """
repos:
  "dci-labs/grout":
    voting: false
    rules:
      - name: recheck
        action: ignore
  "(dci-labs|distributedci)/.*":
    skip: true
"""
    engine, _, _, _ = build(tmp_path, text)
    # "dci-labs/grout" must not capture "dci-labs/grout-config"
    assert engine.find_repo(
        make_event(comment_payload(repo="dci-labs/grout-config"))
    ).skip
    # nor the same repository name in another organization
    assert engine.find_repo(make_event(comment_payload(repo="someone-else/grout"))) is None


def test_reference_example_reaches_the_second_repository():
    path = ROOT / "examples" / "github-stream.yml"
    config = github_stream.load_config(str(path))
    engine = github_stream.Engine(config, FakeClient(), FakeRunner(), FakeAuth())
    # "dci-labs/example" must not capture "dci-labs/example-bis"
    assert (
        engine.find_repo({"repo": "dci-labs/example"}).pattern == "dci-labs/example"
    )
    assert (
        engine.find_repo({"repo": "dci-labs/example-bis"}).pattern
        == "dci-labs/example-bis"
    )


#
# AC6: selectors
#


SELECTOR_CONFIG = """
commands:
  run: echo run
repos:
  "dci-labs/grout":
    voting: false
    rules:
      - name: match
        match: '^\\s*recheck\\s*$'
        action: run
        command: run
"""


def test_selector_match(tmp_path):
    engine, _, runner, _ = build(tmp_path, SELECTOR_CONFIG)
    engine.process(make_event(comment_payload(body="recheck")))
    assert runner.calls == [("echo run", None)]


def test_selector_match_is_case_insensitive_and_multiline(tmp_path):
    engine, _, runner, _ = build(tmp_path, SELECTOR_CONFIG)
    engine.process(make_event(comment_payload(body="thanks\n  ReCheck\nplease")))
    assert runner.calls == [("echo run", None)]


def test_selector_only_if(tmp_path):
    text = """
commands:
  run: echo run
repos:
  "dci-labs/grout":
    voting: false
    rules:
      - name: opened
        only_if: '^opened$'
        action: run
        command: run
"""
    engine, _, runner, _ = build(tmp_path, text)
    engine.process(make_event(pr_payload(action="synchronize")))
    assert runner.calls == []
    engine.process(make_event(pr_payload(action="opened")))
    assert runner.calls == [("echo run", None)]


def test_selector_base_ref(tmp_path):
    text = """
commands:
  run: echo run
repos:
  "dci-labs/grout":
    voting: false
    rules:
      - name: main
        base_ref: '^(main|master)$'
        action: run
        command: run
"""
    engine, _, runner, _ = build(tmp_path, text)
    engine.process(make_event(pr_payload(base_ref="stable")))
    assert runner.calls == []
    engine.process(make_event(pr_payload(base_ref="master")))
    assert runner.calls == [("echo run", None)]


def test_selector_ignore_senders(tmp_path):
    text = """
commands:
  run: echo run
repos:
  "dci-labs/grout":
    voting: false
    rules:
      - name: bot
        ignore_senders: [Grout-Bot]
        action: run
        command: run
      - name: other
        action: run
        command: run
"""
    engine, _, runner, _ = build(tmp_path, text)
    engine.process(make_event(pr_payload(sender="grout-bot")))
    assert runner.calls == [("echo run", None)]


def test_selector_match_pr_body(tmp_path):
    text = """
commands:
  run: echo run
repos:
  "dci-labs/grout":
    voting: false
    rules:
      - name: hints
        match_pr_body: '^Test(Lab|Workload):'
        action: run
        command: run
"""
    engine, _, runner, _ = build(tmp_path, text)
    engine.process(make_event(pr_payload(body="nothing")))
    assert runner.calls == []
    engine.process(make_event(pr_payload(body="TestLab: ocp-vanilla")))
    assert runner.calls == [("echo run", None)]


def test_selector_match_pr_body_fetches_the_description_of_a_comment(tmp_path):
    text = """
commands:
  run: echo run
repos:
  "dci-labs/grout":
    voting: false
    rules:
      - name: hints
        match_pr_body: '^TestLab:'
        action: run
        command: run
"""
    client = FakeClient(pr_body="TestLab: ocp-vanilla")
    engine, client, runner, _ = build(tmp_path, text, client=client)
    engine.process(make_event(comment_payload(body="/dci-rerun")))
    assert ("get_pr_body", PR_URL) in client.reads
    assert runner.calls == [("echo run", None)]


def test_selector_no_match_pr_body(tmp_path):
    text = """
commands:
  run: echo run
repos:
  "dci-labs/grout":
    voting: false
    rules:
      - name: launch
        no_match_pr_body: '(?i)^Test-Hints?:\\s*no-check'
        action: run
        command: run
"""
    engine, _, runner, _ = build(tmp_path, text)
    engine.process(make_event(pr_payload(body="Test-Hint: no-check")))
    assert runner.calls == []
    engine.process(make_event(pr_payload(body="a real change")))
    assert runner.calls == [("echo run", None)]


def test_selector_file_match_and_ignore_files(tmp_path):
    text = """
commands:
  run: echo run
repos:
  "dci-labs/grout":
    voting: false
    rules:
      - name: roles
        file_match: 'roles/preflight'
        ignore_files: '\\.md$'
        action: run
        command: run
"""
    client = FakeClient(files=["roles/preflight/tasks/main.yml"])
    engine, client, runner, _ = build(tmp_path, text, client=client)
    engine.process(make_event(pr_payload()))
    assert runner.calls == [("echo run", None)]

    client = FakeClient(files=["roles/preflight/README.md"])
    engine, client, runner, _ = build(tmp_path, text, client=client)
    engine.process(make_event(pr_payload()))
    assert runner.calls == []


def test_selector_match_label_and_merged(tmp_path):
    text = """
commands:
  run: echo run
repos:
  "dci-labs/grout":
    voting: false
    rules:
      - name: merged
        only_if: '^closed$'
        merged: true
        action: run
        command: run
      - name: unlabeled
        only_if: '^unlabeled$'
        match_label: '^dci-disable$'
        action: run
        command: run
"""
    engine, _, runner, _ = build(tmp_path, text)
    engine.process(make_event(pr_payload(action="closed", merged=False)))
    assert runner.calls == []
    engine.process(make_event(pr_payload(action="closed", merged=True)))
    assert len(runner.calls) == 1
    engine.process(make_event(pr_payload(action="unlabeled", label="dci-disable")))
    assert len(runner.calls) == 2
    engine.process(make_event(pr_payload(action="unlabeled", label="other")))
    assert len(runner.calls) == 2


#
# AC7: authorization
#


AUTH_CONFIG = """
auth:
  orgs: [dci-labs]
commands:
  launch: echo launch
repos:
  "dci-labs/grout":
    voting: false
    rules:
      - name: dci-rerun
        match: '(?i)^\\s*/dci-rerun'
        action: run
        command: launch
"""


def test_authorized_sender_dispatches(tmp_path):
    engine, client, runner, auth = build(tmp_path, AUTH_CONFIG)
    engine.process(make_event(comment_payload(sender="alice")))
    assert len(auth.requests) == 1
    assert runner.calls == [("echo launch", None)]
    assert client.calls == []


def test_unauthorized_sender_is_refused_with_one_comment(tmp_path):
    engine, client, runner, _ = build(tmp_path, AUTH_CONFIG, auth=FakeAuth(False))
    results = engine.process(make_event(comment_payload(sender="mallory")))
    assert client.calls == [
        ("comment", COMMENTS_URL, "mallory unauthorized to call dci-rerun")
    ]
    assert runner.calls == []
    assert [item["action"] for item in results] == []
    assert client.kinds() == ["comment"]


def test_unauthorized_sender_without_login(tmp_path):
    engine, client, _, _ = build(tmp_path, AUTH_CONFIG, auth=FakeAuth(False))
    engine.process(make_event(comment_payload(sender=None)))
    assert client.calls == [
        ("comment", COMMENTS_URL, "unauthorized to call dci-rerun: no login found")
    ]


def test_auth_is_not_checked_for_pull_request_events(tmp_path):
    text = """
auth:
  orgs: [dci-labs]
commands:
  launch: echo launch
repos:
  "dci-labs/grout":
    voting: false
    rules:
      - name: opened
        only_if: '^opened$'
        action: run
        command: launch
"""
    engine, client, runner, auth = build(tmp_path, text, auth=FakeAuth(False))
    engine.process(make_event(pr_payload(action="opened", sender="mallory")))
    assert auth.requests == []
    assert runner.calls == [("echo launch", None)]
    assert client.calls == []


def test_rule_level_auth_overrides_the_repository_auth(tmp_path):
    text = """
commands:
  launch: echo launch
repos:
  "dci-labs/grout":
    voting: false
    auth:
      collaborator: true
    rules:
      - name: dci-rerun
        match: '/dci-rerun'
        auth:
          orgs: [dci-labs, redhatci]
        action: run
        command: launch
"""
    engine, client, runner, auth = build(tmp_path, text, auth=FakeAuth(True))
    engine.process(make_event(comment_payload(body="/dci-rerun")))
    spec = auth.requests[0][0]
    assert spec.orgs == ("dci-labs", "redhatci")
    assert spec.collaborator is False


def test_auth_resolver_uses_orgs_and_caches(tmp_path):
    client = FakeClient(member_orgs=(("dci-labs", "alice"),))
    resolver = github_stream.AuthResolver(client)
    spec = github_stream.AuthSpec(orgs=("distributedci", "dci-labs"))
    assert resolver.allowed(spec, "dci-labs", "grout", "alice") is True
    assert resolver.allowed(spec, "dci-labs", "grout", "alice") is True
    assert client.read_kinds().count("is_org_member") == 2
    assert resolver.allowed(spec, "dci-labs", "grout", "mallory") is False
    assert resolver.allowed(spec, "dci-labs", "grout", "") is False


def test_auth_resolver_collaborator():
    client = FakeClient(collaborators=(("dci-labs", "grout", "alice"),))
    resolver = github_stream.AuthResolver(client)
    spec = github_stream.AuthSpec(collaborator=True)
    assert resolver.allowed(spec, "dci-labs", "grout", "alice") is True
    assert resolver.allowed(spec, "dci-labs", "grout", "mallory") is False


def test_auth_resolver_does_not_share_the_cache_between_repositories():
    client = FakeClient(collaborators=(("dci-labs", "grout", "alice"),))
    resolver = github_stream.AuthResolver(client)
    spec = github_stream.AuthSpec(collaborator=True)
    assert resolver.allowed(spec, "dci-labs", "grout", "alice") is True
    # same specification, other repository: the collaborator check is
    # repository specific and must not be served from the cache.
    assert resolver.allowed(spec, "dci-labs", "grout-config", "alice") is False
    assert client.read_kinds().count("is_collaborator") == 2


def test_auth_resolver_inactive_spec():
    client = FakeClient()
    resolver = github_stream.AuthResolver(client)
    assert resolver.allowed(github_stream.AuthSpec(), "o", "r", "anybody") is True
    assert client.calls == []


def test_auth_resolver_dry_run_allows_everything():
    client = FakeClient()
    client.dry_run = True
    resolver = github_stream.AuthResolver(client)
    assert resolver.allowed(github_stream.AuthSpec(orgs=("dci-labs",)), "o", "r", "x")


#
# AC8: voting invariant and status ordering
#


def test_pending_is_posted_after_a_successful_launch(tmp_path):
    engine, client, runner, _ = build(tmp_path, SIMPLE_CONFIG)
    engine.process(make_event(comment_payload(body="/dci-rerun")))
    assert client.calls == [("status", "pending", "waiting for a DCI job")]


def test_no_pending_when_not_voting(tmp_path):
    text = SIMPLE_CONFIG.replace("voting: true", "voting: false")
    engine, client, runner, _ = build(tmp_path, text)
    engine.process(make_event(comment_payload(body="/dci-rerun")))
    assert client.calls == []


def test_no_pending_when_the_command_fails(tmp_path):
    runner = FakeRunner([github_stream.CommandResult(rc=1, stderr="boom")])
    engine, client, _, _ = build(tmp_path, SIMPLE_CONFIG, runner=runner)
    engine.process(make_event(comment_payload(body="/dci-rerun")))
    assert client.calls == []


def test_no_pending_when_the_command_reported_a_success(tmp_path):
    text = SIMPLE_CONFIG.replace("command: launch", "command: no-check")
    runner = FakeRunner(
        [
            github_stream.CommandResult(
                rc=0,
                actions=(
                    {"action": "pending", "description": "waiting for a DCI job"},
                    {"action": "success", "description": "SUCCESS"},
                    {"action": "comment", "description": "no check"},
                ),
            )
        ]
    )
    engine, client, _, _ = build(tmp_path, text, runner=runner)
    engine.process(make_event(comment_payload(body="/dci-rerun")))
    assert client.calls == [
        ("status", "pending", "waiting for a DCI job"),
        ("status", "success", "SUCCESS"),
        ("comment", COMMENTS_URL, "no check"),
    ]


def test_pending_description_can_be_configured(tmp_path):
    text = SIMPLE_CONFIG.replace(
        "        stdin: pr_body",
        "        stdin: pr_body\n        pending_description: queued for the lab",
    )
    engine, client, _, _ = build(tmp_path, text)
    engine.process(make_event(comment_payload(body="/dci-rerun")))
    assert client.calls == [("status", "pending", "queued for the lab")]


def test_pending_description_is_expanded(tmp_path):
    text = SIMPLE_CONFIG.replace(
        "        stdin: pr_body",
        "        stdin: pr_body\n        pending_description: waiting for @org",
    )
    engine, client, _, _ = build(tmp_path, text)
    engine.process(make_event(comment_payload(body="/dci-rerun")))
    assert client.calls == [("status", "pending", "waiting for dci-labs")]


def test_no_status_when_a_failing_command_reported_statuses(tmp_path):
    # a command that calls send_pending_msg and then fails must not leave a
    # permanent pending status, but its comments are still posted.
    runner = FakeRunner(
        [
            github_stream.CommandResult(
                rc=1,
                stderr="boom",
                actions=(
                    {"action": "pending", "description": "waiting for a DCI job"},
                    {"action": "success", "description": "SUCCESS"},
                    {"action": "comment", "description": "the lab is down"},
                ),
            )
        ]
    )
    engine, client, _, _ = build(tmp_path, SIMPLE_CONFIG, runner=runner)
    engine.process(make_event(comment_payload(body="/dci-rerun")))
    assert client.calls == [("comment", COMMENTS_URL, "the lab is down")]


def test_no_status_for_a_command_of_a_non_voting_repository(tmp_path):
    text = SIMPLE_CONFIG.replace("voting: true", "voting: false")
    runner = FakeRunner(
        [
            github_stream.CommandResult(
                rc=0,
                actions=(
                    {"action": "pending", "description": "waiting for a DCI job"},
                    {"action": "success", "description": "SUCCESS"},
                    {"action": "comment", "description": "done"},
                ),
            )
        ]
    )
    engine, client, _, _ = build(tmp_path, text, runner=runner)
    engine.process(make_event(comment_payload(body="/dci-rerun")))
    assert client.calls == [("comment", COMMENTS_URL, "done")]


def test_unknown_action_from_a_command_is_ignored(tmp_path):
    runner = FakeRunner(
        [github_stream.CommandResult(rc=0, actions=({"action": "nonsense"},))]
    )
    engine, client, _, _ = build(tmp_path, SIMPLE_CONFIG, runner=runner)
    engine.process(make_event(comment_payload(body="/dci-rerun")))
    assert client.calls == [("status", "pending", "waiting for a DCI job")]


def test_comment_of_a_run_rule_is_posted_before_the_status(tmp_path):
    text = SIMPLE_CONFIG.replace(
        "        stdin: pr_body",
        "        stdin: pr_body\n        comment: launching the check",
    )
    engine, client, _, _ = build(tmp_path, text)
    engine.process(make_event(comment_payload(body="/dci-rerun")))
    assert client.kinds() == ["comment", "status"]


def test_comment_action(tmp_path):
    text = """
repos:
  "dci-labs/grout":
    voting: false
    rules:
      - name: help
        match: '(?i)^/dci-help'
        action: comment
        comment: "see @url for the details"
"""
    engine, client, _, _ = build(tmp_path, text)
    engine.process(make_event(comment_payload(body="/dci-help")))
    assert client.calls == [
        ("comment", COMMENTS_URL, f"see {PR_HTML_URL} for the details")
    ]


def test_stdin_pr_body(tmp_path):
    runner = FakeRunner()
    engine, _, _, _ = build(tmp_path, SIMPLE_CONFIG, runner=runner)
    engine.process(make_event(comment_payload(body="/dci-rerun")))
    assert runner.calls == [("dci-auto-launch " + PR_HTML_URL, "")]


def test_stdin_pr_body_uses_the_description_for_a_comment_event(tmp_path):
    runner = FakeRunner()
    client = FakeClient(pr_body="TestLab: ocp-vanilla")
    engine, _, _, _ = build(tmp_path, SIMPLE_CONFIG, client=client, runner=runner)
    engine.process(make_event(comment_payload(body="/dci-rerun")))
    assert runner.calls == [("dci-auto-launch " + PR_HTML_URL, "TestLab: ocp-vanilla")]


#
# AC9: the shell helpers of the command runner
#


def test_command_runner_records_the_actions_in_order():
    runner = github_stream.CommandRunner(timeout=60)
    result = runner.command(
        'send_pending_msg "waiting for a DCI job"\n'
        "send_success_msg SUCCESS\n"
        'send_comment "no check (not a code change)"\n'
    )
    assert result.rc == 0
    assert result.timed_out is False
    assert [action["action"] for action in result.actions] == [
        "pending",
        "success",
        "comment",
    ]
    assert result.actions[0]["description"] == "waiting for a DCI job"
    assert result.actions[2]["description"] == "no check (not a code change)"


def test_command_runner_escapes_the_messages():
    runner = github_stream.CommandRunner(timeout=60)
    result = runner.command("""send_comment 'a "quoted" \\ backslash'""")
    assert result.actions[0]["description"] == 'a "quoted" \\ backslash'


def test_command_runner_pr_body_on_stdin():
    runner = github_stream.CommandRunner(timeout=60)
    result = runner.command_pr_body("cat", "TestLab: ocp-vanilla\n")
    assert result.rc == 0
    assert result.stdout == "TestLab: ocp-vanilla\n"


def test_command_runner_returns_the_exit_code():
    runner = github_stream.CommandRunner(timeout=60)
    assert runner.command("exit 3").rc == 3
    result = runner.command("send_success_msg OK\nexit 1")
    assert result.rc == 1
    assert [action["action"] for action in result.actions] == ["success"]


def test_command_runner_timeout():
    runner = github_stream.CommandRunner(timeout=1)
    result = runner.command("sleep 5")
    assert result.timed_out is True
    assert result.rc == -1


def test_read_actions_skips_malformed_lines():
    text = '{"action": "pending", "description": "x"}\nnot json\n{"no": "action"}\n'
    actions = github_stream.read_actions(text)
    assert actions == ({"action": "pending", "description": "x"},)


#
# AC10: GitHub client
#


def test_client_without_token_logs_and_does_not_raise(caplog):
    client = github_stream.GitHubClient(token="")
    assert client.post_comment(COMMENTS_URL, "hello") == (0, {})
    assert "no GitHub token found" in caplog.text


def test_client_dry_run(capsys):
    client = github_stream.GitHubClient(token="token", dry_run=True)
    client.post_comment(COMMENTS_URL, "hello")
    client.set_status(PR_URL, "pending", "waiting for a DCI job")
    err = capsys.readouterr().err
    assert f"+ POST {COMMENTS_URL}" in err
    assert '"body": "hello"' in err
    assert '"state": "pending"' in err


def test_client_dry_run_does_not_need_a_token(capsys):
    client = github_stream.GitHubClient(token="", dry_run=True)
    client.set_status(PR_URL, "success", "SUCCESS")
    assert "+ POST" in capsys.readouterr().err


def test_client_serializes_json_bodies(monkeypatch):
    payloads = []

    class Response:
        status = 201

        def read(self):
            return b'{"ok": true}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout=None):
        payloads.append((request.get_method(), request.full_url, request.data))
        return Response()

    monkeypatch.setattr(github_stream.urllib.request, "urlopen", fake_urlopen)
    client = github_stream.GitHubClient(token="token")
    assert client.post_comment(COMMENTS_URL, 'a "quoted" body') == (201, {"ok": True})
    method, url, data = payloads[0]
    assert (method, url) == ("POST", COMMENTS_URL)
    assert json.loads(data) == {"body": 'a "quoted" body'}


def test_client_handles_api_errors(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise github_stream.urllib.error.HTTPError(
            request.full_url, 404, "Not Found", {}, None
        )

    monkeypatch.setattr(github_stream.urllib.request, "urlopen", fake_urlopen)
    client = github_stream.GitHubClient(token="token")
    assert client.post_comment(COMMENTS_URL, "hello")[0] == 404
    assert client.is_org_member("dci-labs", "alice") is False
    assert client.get_pr_files("dci-labs/grout", 42) == ()


def test_load_token_from_environment(monkeypatch):
    monkeypatch.setenv(github_stream.TOKEN_ENV, "from-env")
    assert github_stream.load_token() == "from-env"


def test_load_token_from_config(tmp_path, monkeypatch):
    monkeypatch.delenv(github_stream.TOKEN_ENV, raising=False)
    config = tmp_path / "config"
    config.write_text('OTHER=1\nGITHUB_TOKEN="from-file"\n', encoding="utf-8")
    monkeypatch.setattr(github_stream, "TOKEN_CONFIG_PATH", str(config))
    assert github_stream.load_token() == "from-file"


def test_load_token_without_config(tmp_path, monkeypatch):
    monkeypatch.delenv(github_stream.TOKEN_ENV, raising=False)
    monkeypatch.setattr(github_stream, "TOKEN_CONFIG_PATH", str(tmp_path / "missing"))
    assert github_stream.load_token() == ""


#
# hint names
#


def test_list_hints_is_cached(monkeypatch):
    github_stream._HINTS_CACHE.clear()
    calls = []

    class Proc:
        returncode = 0
        stdout = "Lab\nWorkload\n"
        stderr = ""

    monkeypatch.setattr(
        github_stream.subprocess,
        "run",
        lambda *args, **kwargs: calls.append(args) or Proc(),
    )
    command = ("dci-auto-launch", "--list-sections")
    assert github_stream.list_hints(command) == ["Lab", "Workload"]
    assert github_stream.list_hints(command) == ["Lab", "Workload"]
    assert len(calls) == 1


def test_list_hints_failure(monkeypatch, caplog):
    github_stream._HINTS_CACHE.clear()

    class Proc:
        returncode = 1
        stdout = ""
        stderr = "not installed"

    monkeypatch.setattr(github_stream.subprocess, "run", lambda *args, **kwargs: Proc())
    assert github_stream.list_hints(("missing-command",)) == []
    assert "cannot list the test hints" in caplog.text


def test_hint_names_are_expanded_in_the_rules(tmp_path):
    text = """
commands:
  run: echo run
repos:
  "dci-labs/grout":
    voting: false
    rules:
      - name: hints
        match_pr_body: '^Test(@hints):'
        action: run
        command: run
"""
    engine, _, runner, _ = build(tmp_path, text, hints=["Lab", "Workload"])
    engine.process(make_event(pr_payload(body="TestWorkload: workload")))
    assert runner.calls == [("echo run", None)]
    runner.calls.clear()
    engine.process(make_event(pr_payload(body="TestNothing: nope")))
    assert runner.calls == []


def test_render_keeps_the_pass_through_variables():
    event = {"url": "u", "repo": "o/r"}
    rendered = github_stream.render(
        "dci-queue schedule p -- env T=@RESOURCE @url @QUEUE", event
    )
    assert rendered == "dci-queue schedule p -- env T=@RESOURCE u @QUEUE"


#
# AC13/AC14: stream processing
#


def test_process_stream_reloads_the_configuration(tmp_path):
    path = write_config(tmp_path, SIMPLE_CONFIG)
    client = FakeClient()
    runner = FakeRunner()

    def lines():
        yield json.dumps(comment_payload(body="/dci-rerun"))
        path.write_text(
            'repos:\n  "dci-labs/grout":\n    voting: false\n'
            "    rules:\n      - name: help\n        action: comment\n"
            '        comment: "hello"\n',
            encoding="utf-8",
        )
        yield json.dumps(comment_payload(body="/dci-rerun"))

    github_stream.process_stream(lines(), str(path), client, runner, FakeAuth())

    assert runner.calls == [("dci-auto-launch " + PR_HTML_URL, "")]
    assert client.calls == [
        ("status", "pending", "waiting for a DCI job"),
        ("comment", COMMENTS_URL, "hello"),
    ]


def test_process_stream_survives_malformed_events_and_config(tmp_path, caplog):
    path = write_config(tmp_path, SIMPLE_CONFIG)
    client = FakeClient()
    runner = FakeRunner()

    def lines():
        yield "this is not json"
        yield json.dumps(comment_payload(body="/dci-rerun"))
        path.write_text("repos: [\n", encoding="utf-8")
        yield json.dumps(comment_payload(body="/dci-rerun"))
        path.write_text("unknown: 1\n", encoding="utf-8")
        yield json.dumps(comment_payload(body="/dci-rerun"))
        yield "{}"

    github_stream.process_stream(lines(), str(path), client, runner, FakeAuth())

    assert runner.calls == [("dci-auto-launch " + PR_HTML_URL, "")]
    assert "skipping malformed event" in caplog.text
    assert "invalid YAML" in caplog.text
    assert "unknown key 'unknown'" in caplog.text


def test_process_stream_survives_a_client_error(tmp_path, caplog):
    class BrokenClient(FakeClient):
        def set_status(self, pulls_url, state, description, context=None):
            raise RuntimeError("API is down")

    path = write_config(tmp_path, SIMPLE_CONFIG)
    client = BrokenClient()

    def lines():
        yield json.dumps(comment_payload(body="/dci-rerun"))
        yield json.dumps(comment_payload(body="/dci-rerun"))

    github_stream.process_stream(lines(), str(path), client, FakeRunner(), FakeAuth())
    assert "error while processing an event" in caplog.text


def test_main_dry_run_on_synthetic_payloads(tmp_path, capsys):
    text = """
commands:
  launch: echo @url | wc -c
repos:
  "dci-labs/grout":
    voting: true
    rules:
      - name: dci-rerun
        match: '(?i)^\\s*/dci-rerun'
        action: run
        command: launch
"""
    path = write_config(tmp_path, text)
    stream = tmp_path / "events.jsonl"
    stream.write_text(
        "\n".join(
            [
                "garbage",
                json.dumps(comment_payload(body="/dci-rerun")),
                json.dumps(pr_payload(body="TestLab: ocp")),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert (
        github_stream.main(
            ["dci-github-stream", "--config", str(path), "--dry-run", str(stream)]
        )
        == 0
    )
    err = capsys.readouterr().err
    assert "+ POST" in err
    assert "no GitHub token" not in err


#
# AC15: packaging, examples and documentation
#


ROOT = pathlib.Path(github_stream.__file__).resolve().parent.parent


def test_no_reference_to_the_legacy_configuration():
    paths = [ROOT / "dcipipeline" / "github_stream.py"]
    paths.extend(sorted((ROOT / "examples").glob("github-stream*.yml")))
    assert len(paths) > 3
    for path in paths:
        assert "auto.conf" not in path.read_text(encoding="utf-8"), path


def test_examples_are_valid_configurations():
    paths = sorted((ROOT / "examples").glob("github-stream*.yml"))
    assert [path.name for path in paths] == [
        "github-stream-bos2.yml",
        "github-stream-vcp.yml",
        "github-stream.yml",
    ]
    for path in paths:
        config = github_stream.load_config(str(path))
        assert config.repos, path


def test_examples_are_yaml():
    for path in sorted((ROOT / "examples").glob("github-stream*.yml")):
        assert isinstance(yaml.safe_load(path.read_text(encoding="utf-8")), dict)


def test_console_script_is_declared():
    setup_py = (ROOT / "setup.py").read_text(encoding="utf-8")
    assert "dci-github-stream=dcipipeline.github_stream:main" in setup_py


def test_rpm_spec_lists_the_console_script():
    spec = (ROOT / "dci-pipeline.spec").read_text(encoding="utf-8")
    assert "%{_bindir}/dci-github-stream" in spec


def test_examples_are_packaged():
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    assert "include examples/*" in manifest


def test_readme_documents_the_tool():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "## dci-github-stream" in readme
    for expected in (
        "GITHUB_STREAM_CONF",
        "--dry-run",
        "send_pending_msg",
        "DCI / DCI Job",
    ):
        assert expected in readme


# test_github_stream.py ends here
