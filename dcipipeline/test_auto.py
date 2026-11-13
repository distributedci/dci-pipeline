#
# Copyright (C) 2023 Red Hat, Inc.
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

import os
import tempfile
import unittest
from unittest import mock

from dcipipeline import auto


class TestAuto(unittest.TestCase):
    def test_parse_desctription(self):
        description = "TestFoo: bar"
        self.assertEqual(auto.parse_description(description), {"Foo": ["bar"]})

    def test_cleanup(self):
        self.assertEqual(auto.cleanup("foo; bar"), "foo bar")
        self.assertEqual(auto.cleanup("foo& bar"), "foo bar")

    def test_list_sections(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "auto.conf")
            with open(path, "w", encoding="utf-8") as fobj:
                fobj.write("[Lab]\ncmd = dci-pipeline-check @URL -p pool\n")
                fobj.write("[Workload]\ncmd = dci-queue schedule wrkld\n")
            self.assertEqual(
                auto.list_sections(auto.load_config(path)), ["Lab", "Workload"]
            )

    def test_list_sections_empty(self):
        self.assertEqual(
            auto.list_sections(auto.load_config("/nonexistent/auto.conf")), []
        )

    def test_main_list_sections(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "auto.conf")
            with open(path, "w", encoding="utf-8") as fobj:
                fobj.write("[Lab]\ncmd = dci-pipeline-check @URL -p pool\n")
            with mock.patch.object(auto, "CONFIG_PATH", path):
                with mock.patch("sys.stdout") as stdout:
                    self.assertEqual(
                        auto.main(["dci-auto-launch", "--list-sections"]), 0
                    )
            self.assertEqual(
                [call.args[0] for call in stdout.write.call_args_list],
                ["Lab", "\n"],
            )

    def test_main_list_sections_does_not_launch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "auto.conf")
            with open(path, "w", encoding="utf-8") as fobj:
                fobj.write("[Lab]\ncmd = dci-pipeline-check @URL -p pool\n")
            with mock.patch.object(auto, "CONFIG_PATH", path):
                with mock.patch("sys.stdout"):
                    with mock.patch("subprocess.check_call") as check_call:
                        auto.main(["dci-auto-launch", "--list-sections"])
        check_call.assert_not_called()

    def test_main_requires_url(self):
        with mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit) as exc:
                auto.main(["dci-auto-launch"])
        self.assertEqual(exc.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

# test_auto.py ends here
