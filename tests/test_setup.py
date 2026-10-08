import io
import json
import os
import sys
from unittest import mock

from tests.helpers import IsolatedCase
from white_rabbit import setup

EXE = "/home/u/.local/bin/white-rabbit"


class SetupTest(IsolatedCase):
    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.root, "settings.json")

    def run_setup(self, *args):
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            code = setup.run(list(args), settings_path=self.path, exe=EXE)
        return code, out.getvalue()

    def read(self):
        with open(self.path) as fh:
            return json.load(fh)

    def commands(self, data, event):
        return [h["command"] for g in data["hooks"].get(event, []) for h in g["hooks"]]

    def test_adds_the_statusline_and_three_hooks_with_the_absolute_path(self):
        self.assertEqual(self.run_setup()[0], 0)
        data = self.read()
        self.assertEqual(data["statusLine"], {"type": "command", "command": EXE + " statusline"})
        self.assertEqual(self.commands(data, "PostToolUse"), [EXE + " hook capture"])
        self.assertEqual(data["hooks"]["PostToolUse"][0]["matcher"], "Bash|Write|Edit")
        self.assertEqual(self.commands(data, "Stop"), [EXE + " hook refresh"])
        self.assertTrue(data["hooks"]["Stop"][0]["hooks"][0]["async"])
        self.assertEqual(self.commands(data, "SessionStart"), [EXE + " hook start"])

    def test_is_idempotent_and_keeps_other_settings(self):
        with open(self.path, "w") as fh:
            json.dump({"model": "opus", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "other"}]}]}}, fh)
        self.run_setup()
        self.run_setup()
        data = self.read()
        self.assertEqual(data["model"], "opus")
        self.assertEqual(self.commands(data, "Stop"), ["other", EXE + " hook refresh"])
        self.assertEqual(self.commands(data, "PostToolUse"), [EXE + " hook capture"])

    def test_backs_up_the_previous_file(self):
        with open(self.path, "w") as fh:
            fh.write('{"model": "opus"}')
        self.run_setup()
        with open(self.path + ".bak") as fh:
            self.assertEqual(json.load(fh), {"model": "opus"})

    def test_dry_run_writes_nothing(self):
        code, out = self.run_setup("--dry-run")
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(self.path))
        self.assertIn("hook capture", out)

    def test_a_foreign_statusline_is_kept_without_force(self):
        with open(self.path, "w") as fh:
            json.dump({"statusLine": {"type": "command", "command": "my-line"}}, fh)
        code, out = self.run_setup()
        self.assertEqual(code, 1)
        self.assertEqual(self.read()["statusLine"]["command"], "my-line")
        self.assertIn("--force", out)
        self.assertEqual(self.commands(self.read(), "Stop"), [EXE + " hook refresh"])
        self.run_setup("--force")
        self.assertEqual(self.read()["statusLine"]["command"], EXE + " statusline")

    def test_an_unreadable_file_is_left_alone(self):
        with open(self.path, "w") as fh:
            fh.write("{broken")
        self.assertEqual(self.run_setup()[0], 1)
        with open(self.path) as fh:
            self.assertEqual(fh.read(), "{broken")
