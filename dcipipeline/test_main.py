#
# Copyright (C) 2020-2025 Red Hat, Inc.
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

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from dcipipeline.main import (
    build_cmdline,
    build_launch_cmdline,
    convert_value_type,
    dci,
    extract_build_tags,
    extract_tags,
    filter_type_tags,
    generate_and_query_clause,
    generate_query,
    generate_query_from_tags,
    get_components,
    get_config,
    get_prev_jobdefs,
    load_jobdef_file,
    overload_dicts,
    post_process_jobdef,
    pre_process_jobdef,
    process_args,
    schedule_job,
    upload_cmdline_file,
    upload_junit_files_from_dir,
)


class TestMain(unittest.TestCase):
    def test_process_args_empty(self):
        args = ["dci-pipeline"]
        result, args, opts = process_args(args)
        self.assertEqual(args, [])
        self.assertEqual(result, [])
        self.assertEqual(opts["name"], "pipeline")

    def test_process_args_single(self):
        args = ["dci-pipeline", "jobdef:key=value"]
        result, args, _ = process_args(args)
        self.assertEqual(args, [])
        self.assertEqual(result, [{"jobdef": {"key": "value"}}])

    def test_process_args_list(self):
        args = ["dci-pipeline", "jobdef:key=value=toto,value2"]
        result, args, _ = process_args(args)
        self.assertEqual(args, [])
        self.assertEqual(result, [{"jobdef": {"key": ["value=toto", "value2"]}}])

    def test_process_args_dict(self):
        args = ["dci-pipeline", "jobdef:key=subkey:value", "jobdef:key=subkey2:value2"]
        result, args, _ = process_args(args)
        self.assertEqual(args, [])
        self.assertEqual(
            result,
            [
                {"jobdef": {"key": {"subkey": "value"}}},
                {"jobdef": {"key": {"subkey2": "value2"}}},
            ],
        )

    def test_process_args_dict_list(self):
        args = ["dci-pipeline", "jobdef:key=subkey:value,value2"]
        result, args, _ = process_args(args)
        self.assertEqual(args, [])
        self.assertEqual(result, [{"jobdef": {"key": {"subkey": ["value", "value2"]}}}])

    def test_process_args_list1(self):
        args = ["dci-pipeline", "jobdef:key=value=toto,"]
        result, args, _ = process_args(args)
        self.assertEqual(args, [])
        self.assertEqual(result, [{"jobdef": {"key": ["value=toto"]}}])

    def test_process_args_only_files(self):
        args = ["dci-pipeline", "file1", "file2"]
        result, args, _ = process_args(args)
        self.assertEqual(args, ["file1", "file2"])
        self.assertEqual(result, [])

    def test_process_args_http(self):
        args = ["dci-pipeline", "jobdef:key=http://lwn.net/"]
        result, args, _ = process_args(args)
        self.assertEqual(args, [])
        self.assertEqual(result, [{"jobdef": {"key": "http://lwn.net/"}}])

    def test_process_args_https(self):
        args = ["dci-pipeline", "jobdef:key=https://lwn.net/"]
        result, args, _ = process_args(args)
        self.assertEqual(args, [])
        self.assertEqual(result, [{"jobdef": {"key": "https://lwn.net/"}}])

    def test_process_args_json(self):
        args = ["dci-pipeline", 'jobdef:key={"subkey":"value"}']
        result, args, _ = process_args(args)
        self.assertEqual(result, [{"jobdef": {"key": {"subkey": "value"}}}])

    def test_process_args_pipeline_name(self):
        args = ["dci-pipeline", "@pipeline:name=my-pipeline"]
        _, _, opts = process_args(args)
        self.assertEqual(opts["name"], "my-pipeline")

    def test_process_args_pipeline_id(self):
        args = ["dci-pipeline", "@pipeline:pipeline_id=my_id"]
        _, _, opts = process_args(args)
        self.assertEqual(opts["pipeline_id"], "my_id")

    @mock.patch("dcipipeline.main.usage")
    def test_process_args_pipeline_invalid_name(self, m):
        args = ["dci-pipeline", "@name:name=my-pipeline"]
        _, _, opts = process_args(args)
        self.assertTrue(m.called)

    def test_process_args_boolean_true(self):
        args = ["dci-pipeline", "jobdef:debug=true"]
        result, _, _ = process_args(args)
        self.assertEqual(result, [{"jobdef": {"debug": True}}])

    def test_process_args_boolean_false(self):
        args = ["dci-pipeline", "jobdef:enabled=false"]
        result, _, _ = process_args(args)
        self.assertEqual(result, [{"jobdef": {"enabled": False}}])

    def test_process_args_integer(self):
        args = ["dci-pipeline", "jobdef:timeout=300"]
        result, _, _ = process_args(args)
        self.assertEqual(result, [{"jobdef": {"timeout": 300}}])

    def test_process_args_integer_zero(self):
        args = ["dci-pipeline", "jobdef:retries=0"]
        result, _, _ = process_args(args)
        self.assertEqual(result, [{"jobdef": {"retries": 0}}])
        self.assertIsInstance(result[0]["jobdef"]["retries"], int)

    def test_process_args_integer_one(self):
        args = ["dci-pipeline", "jobdef:count=1"]
        result, _, _ = process_args(args)
        self.assertEqual(result, [{"jobdef": {"count": 1}}])
        self.assertIsInstance(result[0]["jobdef"]["count"], int)

    def test_process_args_float(self):
        args = ["dci-pipeline", "jobdef:threshold=3.14"]
        result, _, _ = process_args(args)
        self.assertEqual(result, [{"jobdef": {"threshold": 3.14}}])

    def test_process_args_list_with_types(self):
        args = ["dci-pipeline", "jobdef:values=42,3.14,true,hello"]
        result, _, _ = process_args(args)
        self.assertEqual(result, [{"jobdef": {"values": [42, 3.14, True, "hello"]}}])

    def test_process_args_dict_with_int_value(self):
        args = ["dci-pipeline", "jobdef:config=timeout:300"]
        result, _, _ = process_args(args)
        self.assertEqual(result, [{"jobdef": {"config": {"timeout": 300}}}])

    def test_process_args_dict_with_bool_value(self):
        args = ["dci-pipeline", "jobdef:config=enabled:true"]
        result, _, _ = process_args(args)
        self.assertEqual(result, [{"jobdef": {"config": {"enabled": True}}}])

    def test_overload_dicts_add(self):
        jobdef = {"first": "value"}
        overload = {"key": ["value=toto", "value2"]}
        self.assertEqual(
            overload_dicts(overload, jobdef),
            {"first": "value", "key": ["value=toto", "value2"]},
        )

    def test_overload_dicts_replace_list(self):
        overload = {"components": ["ocp=12", "ose-tests"]}
        jobdef = {"components": ["ocp", "cnf-tests"], "topic": "OCP-4.4"}
        self.assertEqual(
            overload_dicts(overload, jobdef),
            {"components": ["ocp=12", "cnf-tests", "ose-tests"], "topic": "OCP-4.4"},
        )

    def test_overload_dicts_replace_list_search(self):
        overload = {"components": ["ocp?version:12", "ose-tests"]}
        jobdef = {"components": ["ocp", "cnf-tests"], "topic": "OCP-4.4"}
        self.assertEqual(
            overload_dicts(overload, jobdef),
            {
                "components": ["ocp?version:12", "cnf-tests", "ose-tests"],
                "topic": "OCP-4.4",
            },
        )

    def test_overload_dicts_replace_string(self):
        overload = {"components": "ocp=12"}
        jobdef = {"components": ["ocp", "cnf-tests"], "topic": "OCP-4.4"}
        self.assertEqual(
            overload_dicts(overload, jobdef),
            {"components": ["ocp=12", "cnf-tests"], "topic": "OCP-4.4"},
        )

    def test_overload_dicts_add_dict(self):
        overload = {"ansible_extravars": {"dci_comment": "universal answer"}}
        jobdef = {"ansible_extravars": {"answer": 42}}
        self.assertEqual(
            overload_dicts(overload, jobdef),
            {"ansible_extravars": {"answer": 42, "dci_comment": "universal answer"}},
        )

    def test_overload_dicts_add_list_in_dict(self):
        overload = {"ansible_extravars": {"dci_comment": "universal answer"}}
        jobdef = {"ansible_extravars": {"answer": 42}}
        self.assertEqual(
            overload_dicts(overload, jobdef),
            {"ansible_extravars": {"answer": 42, "dci_comment": "universal answer"}},
        )

    def test_overload_dicts_deep_merge(self):
        target = {
            "ansible_extravars": {
                "dci_gitops_policies_repo": {"url": "https://orig", "branch": "master"},
                "existing": "value",
            }
        }
        overload = {
            "ansible_extravars": {
                "dci_gitops_policies_repo": {"branch": "my-branch"},
                "dci_gitops_sites_repo": {"branch": "my-branch"},
            }
        }
        expected = {
            "ansible_extravars": {
                "dci_gitops_policies_repo": {
                    "url": "https://orig",
                    "branch": "my-branch",
                },
                "existing": "value",
                "dci_gitops_sites_repo": {"branch": "my-branch"},
            }
        }
        self.assertEqual(overload_dicts(overload, target), expected)

    def test_jobdef_without_component(self):
        jobdef = {}
        components, jobdef = get_components("context", jobdef, "topic_id", "tag")
        self.assertEqual(jobdef, {"components": []})

    def test_prev_jobdefs(self):
        jobdef1 = {"name": "1", "type": "ocp"}
        jobdef2 = {
            "name": "2",
            "type": "ocp-upgrade",
            "prev_stages": ["ocp-upgrade", "ocp"],
        }
        jobdef3 = {
            "name": "3",
            "type": "ocp-upgrade2",
            "prev_stages": ["ocp-upgrade", "ocp"],
        }
        jobdef4 = {"name": "4", "type": "cnf2"}
        pipeline = [jobdef1, jobdef2, jobdef3, jobdef4]
        prev_jobdefs = get_prev_jobdefs(jobdef3, pipeline)
        self.assertEqual(prev_jobdefs, [jobdef2, jobdef1])

    @mock.patch("dcipipeline.main.tempfile.mkdtemp")
    def test_pre_process_jobdef(self, m):
        jobdef = {"ansible_envvars": {"envvar": "/@tmpdir"}}
        m.return_value = "/tmp/tmppath"
        jobdef_metas, jobdef = pre_process_jobdef(jobdef)
        self.assertEqual(jobdef_metas["tmpdirs"][0]["path"], "/tmp/tmppath")

    @mock.patch("dcipipeline.main.shutil.rmtree")
    @mock.patch("dcipipeline.main.upload_junit_files_from_dir")
    def test_post_process_jobdef(self, m_upload_junit, m_rmtree):
        metas = {
            "tmpdirs": [{"name": "JUNIT_OUTPUT_DIR", "path": "/tmp/junit_tmppath"}]
        }
        post_process_jobdef("context", "jobdef", metas)
        m_upload_junit.assert_called_with("context", "jobdef", "/tmp/junit_tmppath")
        m_rmtree.assert_called_with("/tmp/junit_tmppath")

        m_upload_junit.reset_mock()
        m_rmtree.reset_mock()
        metas = {"tmpdirs": [{"name": "envvar1", "path": "/tmp/tmppath"}]}
        post_process_jobdef("context", "jobdef", metas)
        self.assertTrue(not m_upload_junit.called)
        m_rmtree.assert_called_with("/tmp/tmppath")

    @mock.patch("dcipipeline.main.dci_redact.should_redact", return_value=False)
    @mock.patch("dcipipeline.main.dci_file.create")
    def test_upload_junit_files_from_dir(self, m, m_should_redact):
        try:
            os.makedirs("/tmp/junit-tmppath")
        except Exception:
            pass
        open("/tmp/junit-tmppath/junit-tests.xml", "a+").close()
        jobdef = {"job_info": {"job": {"id": "1"}}}
        upload_junit_files_from_dir("context", jobdef, "/tmp/junit-tmppath")
        m.assert_called_with(
            "context",
            "junit-tests",
            file_path="/tmp/junit-tmppath/junit-tests.xml",
            mime="application/junit",
            job_id="1",
        )

    def test_get_config(self):
        basedir = os.path.dirname(__file__)
        fullpath = os.path.join(basedir, "comp.yml")
        fullpath2 = os.path.join(basedir, "comp2.yml")
        config_dir, jobdefs, _ = get_config(["prog", fullpath, fullpath2])
        self.assertEqual(len(jobdefs), 1)
        self.assertEqual(
            jobdefs[0]["components"],
            [
                "storage-plugin",
                "network-plugin",
                "ocp",
                "ose-tests",
                "cnf-tests",
            ],
        )
        self.assertEqual(jobdefs[0]["ansible_extravars"], {"var": 43, "var2": 42})

    def test_extract_tags(self):
        query = "tags:build:dev,daily&version:4.11.41".split("&")
        tags, others = extract_tags(query)
        self.assertEqual(others, ["version:4.11.41"])
        self.assertEqual(tags, ["build:dev,daily"])
        build_tags, other_tags = extract_build_tags(tags)
        self.assertEqual(build_tags, ["build:dev"])
        self.assertEqual(other_tags, ["daily"])

    def test_extract_tags2(self):
        query = "tags:ocp-vanilla-4.8-ok,build:dev&version:20200628".split("&")
        tags, others = extract_tags(query)
        self.assertEqual(others, ["version:20200628"])
        self.assertEqual(tags, ["ocp-vanilla-4.8-ok,build:dev"])
        build_tags, other_tags = extract_build_tags(tags)
        self.assertEqual(build_tags, ["build:dev"])
        self.assertEqual(other_tags, ["ocp-vanilla-4.8-ok"])

    def test_filter_type_tags(self):
        self.assertEqual(filter_type_tags(["ocp?toto"], "ocp"), ["toto"])

    def test_generate_and_query_clause_simple(self):
        self.assertEqual(
            generate_and_query_clause(["status:failure"]), ",eq(status,failure)"
        )

    def test_generate_and_query_clause_multiple(self):
        self.assertEqual(
            generate_and_query_clause(["status:failure", "state:active"]),
            ",eq(status,failure),eq(state,active)",
        )

    def test_generate_and_query_clause_none(self):
        self.assertEqual(generate_and_query_clause([]), "")

    def test_generate_and_query_clause_ilike(self):
        self.assertEqual(generate_and_query_clause(["name:ocp*"]), ",ilike(name,ocp%)")

        self.assertEqual(
            generate_and_query_clause(["status:failure", "name:ocp*"]),
            ",eq(status,failure),ilike(name,ocp%)",
        )

    def test_generate_query_from_tags_empty(self):
        self.assertEqual(generate_query_from_tags([], [], "ocp"), "")

    def test_generate_query_from_tags(self):
        self.assertEqual(
            generate_query_from_tags(["ocp?ocp_tag", "other_tag"], [], "ocp"),
            ",contains(tags,ocp_tag),contains(tags,other_tag)",
        )

    def test_generate_query_from_tags_duplicate(self):
        self.assertEqual(
            generate_query_from_tags(
                ["ocp?ocp_tag", "other_tag", "build:nightly"], ["build:dev"], "ocp"
            ),
            ",contains(tags,ocp_tag),contains(tags,other_tag),or(contains(tags,build:dev),contains(tags,build:candidate),contains(tags,build:ga))",
        )

    def test_generate_query(self):
        self.assertEqual(
            generate_query("ocp", []),
            "and(eq(state,active),eq(type,ocp))",
        )

    def test_generate_query_fallback(self):
        self.assertEqual(
            generate_query("ocp", ["fallback"]),
            "and(eq(state,active),eq(type,ocp),contains(tags,fallback))",
        )

    def test_dci_200(self):
        """dci returns 200 without retry."""
        resp = mock.Mock(status_code=200)
        func = mock.Mock(return_value=resp)
        self.assertEqual(dci(func), resp)
        func.assert_called_once()

    def test_dci_500(self):
        """dci retries on 5xx then returns the response."""
        resp_500 = mock.Mock(status_code=500)
        resp_200 = mock.Mock(status_code=200)
        func = mock.Mock(side_effect=[resp_500, resp_200])
        with mock.patch("dcipipeline.main.time.sleep"):
            result = dci(func)
        self.assertEqual(result, resp_200)
        self.assertEqual(func.call_count, 2)


class TestBuildCmdline(unittest.TestCase):
    @mock.patch(
        "dcipipeline.main.get_vault_client", return_value="/usr/bin/dci-vault-client"
    )
    def test_build_cmdline_default_vault(self, m):
        jobdef = {}
        cmd = build_cmdline(jobdef)
        self.assertTrue(cmd.startswith("--vault-id /usr/bin/dci-vault-client"))

    @mock.patch(
        "dcipipeline.main.get_vault_client", return_value="/usr/bin/dci-vault-client"
    )
    def test_build_cmdline_with_dci_vault_file(self, m):
        jobdef = {"dci_vault_file": "/path/to/vault-password.txt"}
        cmd = build_cmdline(jobdef)
        self.assertIn("--vault-password-file /path/to/vault-password.txt", cmd)
        self.assertNotIn("--vault-id", cmd)

    @mock.patch(
        "dcipipeline.main.get_vault_client", return_value="/usr/bin/dci-vault-client"
    )
    def test_build_cmdline_with_dci_vault_file_tilde(self, m):
        jobdef = {"dci_vault_file": "~/vault-password.txt"}
        cmd = build_cmdline(jobdef)
        self.assertIn("--vault-password-file", cmd)
        self.assertNotIn("~", cmd)
        self.assertNotIn("--vault-id", cmd)

    @mock.patch(
        "dcipipeline.main.get_vault_client", return_value="/usr/bin/dci-vault-client"
    )
    def test_build_cmdline_with_tags(self, m):
        jobdef = {"ansible_tags": ["tag1", "tag2"]}
        cmd = build_cmdline(jobdef)
        self.assertIn("--tags tag1,tag2", cmd)

    @mock.patch(
        "dcipipeline.main.get_vault_client", return_value="/usr/bin/dci-vault-client"
    )
    def test_build_cmdline_with_skip_tags(self, m):
        jobdef = {"ansible_skip_tags": ["skip1"]}
        cmd = build_cmdline(jobdef)
        self.assertIn("--skip-tags skip1", cmd)


class TestLoadJobdefFileVault(unittest.TestCase):
    @mock.patch("dcipipeline.main.load_credentials")
    @mock.patch("dcipipeline.main.CLI.setup_vault_secrets", return_value=[])
    def test_load_jobdef_file_with_dci_vault_file(self, m_vault, m_creds):
        basedir = os.path.dirname(__file__)
        fullpath = os.path.join(basedir, "comp.yml")
        m_creds.return_value = {"DCI_API_SECRET": "fake-secret"}
        load_jobdef_file(fullpath, basedir)
        m_vault.assert_called_once()
        call_kwargs = m_vault.call_args
        self.assertNotIn("vault_password_files", call_kwargs.kwargs)
        self.assertIn("vault_ids", call_kwargs.kwargs)

    @mock.patch("dcipipeline.main.load_credentials")
    @mock.patch("dcipipeline.main.CLI.setup_vault_secrets", return_value=[])
    def test_load_jobdef_file_with_vault_password_file(self, m_vault, m_creds):
        import tempfile

        basedir = os.path.dirname(__file__)
        m_creds.return_value = {"DCI_API_SECRET": "fake-secret"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as vf:
            vf.write("my-vault-password\n")
            vault_file = vf.name
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yml", dir=basedir, delete=False
            ) as tf:
                tf.write(
                    "---\n"
                    "  - name: test-job\n"
                    "    type: ocp\n"
                    "    dci_vault_file: %s\n"
                    "    ansible_playbook: agents/openshift-edge/agent.yml\n"
                    "    topic: OCP-4.8\n"
                    "    components:\n"
                    "      - ocp\n" % vault_file
                )
                tmp_pipeline = tf.name
            load_jobdef_file(tmp_pipeline, basedir)
            m_vault.assert_called_once()
            call_kwargs = m_vault.call_args
            self.assertIn("vault_password_files", call_kwargs.kwargs)
            self.assertEqual(call_kwargs.kwargs["vault_password_files"], [vault_file])
            self.assertEqual(call_kwargs.kwargs["vault_ids"], [])
        finally:
            os.unlink(vault_file)
            os.unlink(tmp_pipeline)


class TestConvertValueType(unittest.TestCase):
    def test_boolean_true_lowercase(self):
        self.assertEqual(convert_value_type("true"), True)

    def test_boolean_true_uppercase(self):
        self.assertEqual(convert_value_type("TRUE"), True)

    def test_boolean_true_mixedcase(self):
        self.assertEqual(convert_value_type("TrUe"), True)

    def test_boolean_yes(self):
        self.assertEqual(convert_value_type("yes"), True)
        self.assertEqual(convert_value_type("YES"), True)

    def test_boolean_on(self):
        self.assertEqual(convert_value_type("on"), True)
        self.assertEqual(convert_value_type("ON"), True)

    def test_boolean_false_lowercase(self):
        self.assertEqual(convert_value_type("false"), False)

    def test_boolean_false_uppercase(self):
        self.assertEqual(convert_value_type("FALSE"), False)

    def test_boolean_false_mixedcase(self):
        self.assertEqual(convert_value_type("FaLsE"), False)

    def test_boolean_no(self):
        self.assertEqual(convert_value_type("no"), False)
        self.assertEqual(convert_value_type("NO"), False)

    def test_boolean_off(self):
        self.assertEqual(convert_value_type("off"), False)
        self.assertEqual(convert_value_type("OFF"), False)

    def test_integer_zero(self):
        self.assertEqual(convert_value_type("0"), 0)
        self.assertIsInstance(convert_value_type("0"), int)

    def test_integer_one(self):
        self.assertEqual(convert_value_type("1"), 1)
        self.assertIsInstance(convert_value_type("1"), int)

    def test_integer_positive(self):
        self.assertEqual(convert_value_type("42"), 42)
        self.assertEqual(convert_value_type("300"), 300)

    def test_integer_negative(self):
        self.assertEqual(convert_value_type("-42"), -42)
        self.assertEqual(convert_value_type("-1"), -1)

    def test_float_positive(self):
        self.assertEqual(convert_value_type("3.14"), 3.14)
        self.assertIsInstance(convert_value_type("3.14"), float)

    def test_float_negative(self):
        self.assertEqual(convert_value_type("-2.5"), -2.5)
        self.assertIsInstance(convert_value_type("-2.5"), float)

    def test_float_zero(self):
        self.assertEqual(convert_value_type("0.0"), 0.0)
        self.assertIsInstance(convert_value_type("0.0"), float)

    def test_float_leading_zero(self):
        self.assertEqual(convert_value_type("0.5"), 0.5)

    def test_string_plain(self):
        self.assertEqual(convert_value_type("hello"), "hello")

    def test_string_with_spaces(self):
        self.assertEqual(convert_value_type("hello world"), "hello world")

    def test_string_url_http(self):
        self.assertEqual(convert_value_type("http://example.com"), "http://example.com")

    def test_string_url_https(self):
        self.assertEqual(
            convert_value_type("https://example.com"), "https://example.com"
        )

    def test_string_path(self):
        self.assertEqual(convert_value_type("/path/to/file"), "/path/to/file")

    def test_string_alphanumeric(self):
        self.assertEqual(convert_value_type("abc123"), "abc123")

    def test_non_string_int(self):
        self.assertEqual(convert_value_type(42), 42)

    def test_non_string_float(self):
        self.assertEqual(convert_value_type(3.14), 3.14)

    def test_non_string_bool(self):
        self.assertEqual(convert_value_type(True), True)
        self.assertEqual(convert_value_type(False), False)

    def test_non_string_list(self):
        lst = [1, 2, 3]
        self.assertEqual(convert_value_type(lst), lst)

    def test_non_string_dict(self):
        dct = {"key": "value"}
        self.assertEqual(convert_value_type(dct), dct)

    def test_empty_string(self):
        self.assertEqual(convert_value_type(""), "")

    def test_string_with_only_spaces(self):
        self.assertEqual(convert_value_type("   "), "   ")


class TestBuildLaunchCmdline(unittest.TestCase):
    def test_simple_command(self):
        self.assertEqual(
            build_launch_cmdline(["dci-pipeline", "my-pipeline.yml"]),
            "dci-pipeline my-pipeline.yml",
        )

    def test_argument_with_spaces(self):
        argv = ["dci-pipeline", "job:key=a b"]
        self.assertEqual(build_launch_cmdline(argv), "dci-pipeline 'job:key=a b'")
        self.assertEqual(shlex.split(build_launch_cmdline(argv)), argv)

    def test_argument_with_commas(self):
        argv = ["dci-pipeline", "job:components=ocp,ose-tests"]
        self.assertEqual(shlex.split(build_launch_cmdline(argv)), argv)

    def test_argument_with_dollar_sign(self):
        argv = ["dci-pipeline", "job:password=Pass123$"]
        self.assertEqual(
            build_launch_cmdline(argv), "dci-pipeline 'job:password=Pass123$'"
        )
        self.assertEqual(shlex.split(build_launch_cmdline(argv)), argv)

    def test_argument_with_double_quotes(self):
        argv = ["dci-pipeline", 'job:key=va"lue']
        self.assertEqual(shlex.split(build_launch_cmdline(argv)), argv)

    def test_argument_with_single_quote(self):
        argv = ["dci-pipeline", "job:key=va'lue"]
        self.assertEqual(shlex.split(build_launch_cmdline(argv)), argv)

    def test_argument_with_backslashes(self):
        argv = ["dci-pipeline", "job:key=C:\\path\\to\\file"]
        self.assertEqual(
            build_launch_cmdline(argv), "dci-pipeline 'job:key=C:\\path\\to\\file'"
        )
        self.assertEqual(shlex.split(build_launch_cmdline(argv)), argv)

    def test_empty_argument(self):
        argv = ["dci-pipeline", ""]
        self.assertEqual(build_launch_cmdline(argv), "dci-pipeline ''")
        self.assertEqual(shlex.split(build_launch_cmdline(argv)), ["dci-pipeline", ""])

    def test_inline_json(self):
        argv = ["dci-pipeline", 'job:ansible_extravars={"a":1,"b":[1,2]}']
        self.assertEqual(shlex.split(build_launch_cmdline(argv)), argv)

    def test_nested_json_recorded_verbatim(self):
        value = '{"b": 2, "a": {"c": [1, 2]}}'
        argv = ["dci-pipeline", "job:ansible_extravars=" + value]
        line = build_launch_cmdline(argv)
        recorded = shlex.split(line)[1]
        self.assertTrue(recorded.endswith(value))
        self.assertEqual(
            json.loads(recorded.split("=", 1)[1]), {"b": 2, "a": {"c": [1, 2]}}
        )

    def test_quotes_and_dollar_inside_json(self):
        value = '{"user":"jdoe","password":"it\'s Pass123$"}'
        argv = ["dci-pipeline", "job:ansible_extravars=" + value]
        self.assertEqual(shlex.split(build_launch_cmdline(argv)), argv)
        recorded = shlex.split(build_launch_cmdline(argv))[1]
        self.assertEqual(
            json.loads(recorded.split("=", 1)[1]),
            {"user": "jdoe", "password": "it's Pass123$"},
        )

    def test_shell_roundtrip(self):
        argv = [
            "-pipeline.yml",
            "job:key=a b",
            'job:ansible_extravars={"user":"jdoe","password":"Pass123$"}',
            "job:other=it's here",
            "",
            "job:path=C:\\tmp\\dir",
        ]
        prog = [
            sys.executable,
            "-c",
            "import json,sys;print(json.dumps(sys.argv[1:]))",
        ]
        line = build_launch_cmdline(prog + argv)
        output = subprocess.check_output(["sh", "-c", line], cwd=tempfile.gettempdir())
        self.assertEqual(json.loads(output.decode()), argv)


class TestUploadCmdlineFile(unittest.TestCase):
    def setUp(self):
        self.context = mock.MagicMock()

    @staticmethod
    def _file_list_response(files):
        return mock.MagicMock(
            status_code=200, json=mock.Mock(return_value={"files": files})
        )

    def test_upload_creates_one_cmdline_file(self):
        captured = {}

        def create(context, name, **kwargs):
            with open(kwargs["file_path"]) as f:
                captured["content"] = f.read()
            captured["args"] = (context, name)
            captured["kwargs"] = kwargs
            return mock.MagicMock(status_code=201)

        with mock.patch(
            "dcipipeline.main.dci_file.list",
            return_value=self._file_list_response([]),
        ), mock.patch(
            "dcipipeline.main.dci_file.create", side_effect=create
        ) as m_create, mock.patch(
            "dcipipeline.main.dci_redact.should_redact", return_value=False
        ):
            upload_cmdline_file(self.context, "job1", "dci-pipeline job:key=a b")

        m_create.assert_called_once()
        self.assertEqual(captured["args"], (self.context, "cmdline.txt"))
        self.assertEqual(captured["kwargs"]["mime"], "text/plain")
        self.assertEqual(captured["kwargs"]["job_id"], "job1")
        self.assertEqual(captured["content"], "dci-pipeline job:key=a b\n")

    def test_redaction_uploads_redacted_content(self):
        captured = {}
        created_dirs = []

        real_mkdtemp = tempfile.mkdtemp

        def fake_mkdtemp(prefix=None):
            d = real_mkdtemp(prefix=prefix)
            created_dirs.append(d)
            return d

        def redact_file(path, redacted_path):
            with open(path) as f:
                content = f.read()
            with open(redacted_path, "w") as f:
                f.write(content.replace("Pass123$", "***"))

        def create(context, name, **kwargs):
            with open(kwargs["file_path"]) as f:
                captured["content"] = f.read()
            return mock.MagicMock(status_code=201)

        with mock.patch(
            "dcipipeline.main.tempfile.mkdtemp", side_effect=fake_mkdtemp
        ), mock.patch(
            "dcipipeline.main.dci_file.list",
            return_value=self._file_list_response([]),
        ), mock.patch(
            "dcipipeline.main.dci_file.create", side_effect=create
        ) as m_create, mock.patch(
            "dcipipeline.main.dci_redact.should_redact", return_value=True
        ), mock.patch(
            "dcipipeline.main.dci_redact.redact_file", side_effect=redact_file
        ):
            upload_cmdline_file(
                self.context, "job1", "dci-pipeline job:password=Pass123$"
            )

        m_create.assert_called_once()
        self.assertEqual(captured["content"], "dci-pipeline job:password=***\n")
        self.assertNotIn("Pass123$", captured["content"])
        self.assertEqual(
            shlex.split(captured["content"]), ["dci-pipeline", "job:password=***"]
        )
        for d in created_dirs:
            self.assertFalse(os.path.exists(d))

    def test_idempotent_when_already_uploaded(self):
        with mock.patch(
            "dcipipeline.main.dci_file.list",
            return_value=self._file_list_response([{"name": "cmdline.txt"}]),
        ), mock.patch("dcipipeline.main.dci_file.create") as m_create, mock.patch(
            "dcipipeline.main.dci_redact.should_redact", return_value=False
        ):
            upload_cmdline_file(self.context, "job1", "dci-pipeline a-pipeline.yml")
        m_create.assert_not_called()

    def test_list_failure_still_uploads(self):
        with mock.patch(
            "dcipipeline.main.dci_file.list", side_effect=Exception("boom")
        ), mock.patch("dcipipeline.main.dci_file.create") as m_create, mock.patch(
            "dcipipeline.main.dci_redact.should_redact", return_value=False
        ):
            upload_cmdline_file(self.context, "job1", "dci-pipeline a-pipeline.yml")
        m_create.assert_called_once()

    def test_create_failure_only_warns(self):
        with mock.patch(
            "dcipipeline.main.dci_file.list",
            return_value=self._file_list_response([]),
        ), mock.patch(
            "dcipipeline.main.dci_file.create", side_effect=Exception("boom")
        ), mock.patch(
            "dcipipeline.main.dci_redact.should_redact", return_value=False
        ), self.assertLogs(
            "dcipipeline.main", level="WARNING"
        ):
            upload_cmdline_file(self.context, "job1", "dci-pipeline a-pipeline.yml")

    def test_no_cmdline_does_nothing(self):
        with mock.patch("dcipipeline.main.dci_file.list") as m_list, mock.patch(
            "dcipipeline.main.dci_file.create"
        ) as m_create:
            upload_cmdline_file(self.context, "job1", "")
        m_list.assert_not_called()
        m_create.assert_not_called()

    def test_none_cmdline_does_nothing(self):
        with mock.patch("dcipipeline.main.dci_file.list") as m_list, mock.patch(
            "dcipipeline.main.dci_file.create"
        ) as m_create:
            upload_cmdline_file(self.context, "job1", None)
        m_list.assert_not_called()
        m_create.assert_not_called()


class TestScheduleJobAttachesCmdline(unittest.TestCase):
    job_id = "job1"
    component_id = "c1"
    cmdline = "dci-pipeline my-pipeline.yml"

    def setUp(self):
        self.jobdef = {
            "name": "job1",
            "topic": "TOPIC",
            "components": [{"name": "ocp", "id": self.component_id}],
        }
        self.components = [{"name": "ocp", "id": self.component_id, "version": "v1"}]

    @staticmethod
    def _response(status_code, payload):
        return mock.MagicMock(
            status_code=status_code, json=mock.Mock(return_value=payload)
        )

    def _schedule(self, scheduled_components=None, files=None, create_error=None):
        """Run schedule_job() with all the DCI API calls mocked."""
        if scheduled_components is None:
            scheduled_components = [{"id": self.component_id, "name": "ocp"}]
        if files is None:
            files = []
        parent = mock.MagicMock()
        with mock.patch(
            "dcipipeline.main.get_topic_id", return_value="topic-id"
        ), mock.patch(
            "dcipipeline.main.get_components",
            return_value=(self.components, self.jobdef),
        ), mock.patch(
            "dcipipeline.main.get_data_dir"
        ), mock.patch(
            "dcipipeline.main.dci_job.create",
            return_value=self._response(201, {"job": {"id": self.job_id}}),
        ), mock.patch(
            "dcipipeline.main.dci_job.get",
            return_value=self._response(
                200,
                {
                    "job": {
                        "id": self.job_id,
                        "components": scheduled_components,
                    }
                },
            ),
        ), mock.patch(
            "dcipipeline.main.dci_jobstate.create"
        ) as m_state, mock.patch(
            "dcipipeline.main.dci_file.list",
            return_value=self._response(200, {"files": files}),
        ), mock.patch(
            "dcipipeline.main.dci_file.create", side_effect=create_error
        ) as m_create, mock.patch(
            "dcipipeline.main.dci_redact.should_redact", return_value=False
        ):
            parent.attach_mock(m_state, "jobstate_create")
            parent.attach_mock(m_create, "file_create")
            job_info = schedule_job(
                self.jobdef,
                mock.MagicMock(),
                None,
                cmdline=self.cmdline,
            )
            return job_info, m_state, m_create, parent

    def test_attach_happens_after_jobstate_creation(self):
        job_info, m_state, m_create, parent = self._schedule()
        self.assertEqual(job_info["job"]["id"], self.job_id)
        m_create.assert_called_once()
        args, kwargs = m_create.call_args
        self.assertEqual(args[1], "cmdline.txt")
        self.assertEqual(kwargs["mime"], "text/plain")
        self.assertEqual(kwargs["job_id"], self.job_id)
        names = [c[0] for c in parent.mock_calls]
        self.assertIn("jobstate_create", names)
        self.assertIn("file_create", names)
        self.assertLess(names.index("jobstate_create"), names.index("file_create"))

    def test_no_upload_when_file_already_present(self):
        _, _, m_create, _ = self._schedule(files=[{"name": "cmdline.txt"}])
        m_create.assert_not_called()

    def test_component_mismatch_early_return_still_uploads(self):
        job_info, _, m_create, _ = self._schedule(
            scheduled_components=[{"id": "other", "name": "other"}]
        )
        self.assertIsNone(job_info)
        m_create.assert_called_once()

    def test_upload_failure_does_not_change_outcome(self):
        with self.assertLogs("dcipipeline.main", level="WARNING"):
            job_info, _, m_create, _ = self._schedule(create_error=Exception("boom"))
        m_create.assert_called_once()
        self.assertEqual(job_info["job"]["id"], self.job_id)

    def test_no_cmdline_no_upload(self):
        with mock.patch(
            "dcipipeline.main.get_topic_id", return_value="topic-id"
        ), mock.patch(
            "dcipipeline.main.get_components",
            return_value=(self.components, self.jobdef),
        ), mock.patch(
            "dcipipeline.main.get_data_dir"
        ), mock.patch(
            "dcipipeline.main.dci_job.create",
            return_value=self._response(201, {"job": {"id": self.job_id}}),
        ), mock.patch(
            "dcipipeline.main.dci_job.get",
            return_value=self._response(
                200,
                {
                    "job": {
                        "id": self.job_id,
                        "components": [{"id": self.component_id, "name": "ocp"}],
                    }
                },
            ),
        ), mock.patch(
            "dcipipeline.main.dci_jobstate.create"
        ), mock.patch(
            "dcipipeline.main.dci_file.list"
        ) as m_list, mock.patch(
            "dcipipeline.main.dci_file.create"
        ) as m_create:
            job_info = schedule_job(
                self.jobdef,
                mock.MagicMock(),
                None,
            )
        self.assertIsNotNone(job_info)
        m_list.assert_not_called()
        m_create.assert_not_called()


if __name__ == "__main__":
    unittest.main()

# test_main.py ends here
