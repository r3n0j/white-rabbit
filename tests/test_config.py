import os

from tests.helpers import IsolatedCase
from white_rabbit import config


class SettingsTest(IsolatedCase):
    def test_defaults_without_a_file(self):
        s = config.settings()
        self.assertTrue(s["gitlab"]["enabled"])
        self.assertEqual(s["gitlab"]["hosts"], ["gitlab.com"])
        self.assertIn("git push", s["gitlab"]["capture_commands"])
        self.assertFalse(s["notes"]["enabled"])
        self.assertEqual(s["notes"]["link"], "file")
        self.assertTrue(s["todo"]["instructions"])
        self.assertTrue(s["recap"]["enabled"])
        self.assertEqual(s["data_dir"], self.dir)

    def test_a_file_overrides_only_its_keys(self):
        self.configure(notes={"enabled": True, "root": "~/vault", "link": "obsidian"})
        s = config.settings()
        self.assertTrue(s["notes"]["enabled"])
        self.assertEqual(s["notes"]["root"], os.path.join(self.root, "vault"))
        self.assertEqual(s["notes"]["link"], "obsidian")
        self.assertEqual(s["notes"]["extensions"], [".md"])
        self.assertTrue(s["gitlab"]["enabled"])

    def test_a_wrong_type_keeps_the_default_and_is_logged(self):
        self.configure(gitlab={"hosts": "gitlab.com", "enabled": "yes"}, notes={"link": "web"})
        s = config.settings()
        self.assertEqual(s["gitlab"]["hosts"], ["gitlab.com"])
        self.assertTrue(s["gitlab"]["enabled"])
        self.assertEqual(s["notes"]["link"], "file")
        self.assertIn("gitlab.hosts", self.errors())
        self.assertIn("notes.link", self.errors())

    def test_a_malformed_file_gives_defaults_and_is_logged(self):
        with open(self.config_file, "w") as fh:
            fh.write("{not json")
        self.assertEqual(config.settings()["gitlab"]["hosts"], ["gitlab.com"])
        self.assertIn("config", self.errors())

    def test_environment_wins_over_the_file(self):
        self.configure(data_dir="~/elsewhere", gitlab={"glab": "/opt/glab"})
        os.environ["SESSION_REGISTRY_GLAB"] = "/usr/bin/glab"
        s = config.settings()
        self.assertEqual(s["data_dir"], self.dir)
        self.assertEqual(s["gitlab"]["glab"], "/usr/bin/glab")

    def test_data_dir_from_the_file_when_no_environment(self):
        del os.environ["WHITE_RABBIT_DIR"]
        self.configure(data_dir="~/.claude/session-registry")
        self.assertEqual(config.data_dir(), os.path.join(self.root, ".claude", "session-registry"))

    def test_legacy_vault_variables_enable_obsidian_notes(self):
        os.environ["SESSION_REGISTRY_VAULT"] = "/v/Omniscience"
        os.environ["SESSION_REGISTRY_VAULT_NAME"] = "Omni"
        s = config.settings()["notes"]
        self.assertEqual((s["enabled"], s["root"], s["link"], s["vault"]), (True, "/v/Omniscience", "obsidian", "Omni"))

    def test_instructions_variable_turns_todo_and_recap_off(self):
        os.environ["WHITE_RABBIT_INSTRUCTIONS"] = "off"
        s = config.settings()
        self.assertEqual((s["todo"]["instructions"], s["recap"]["enabled"]), (False, False))

    def test_instructions_variable_keeps_the_file_otherwise(self):
        os.environ["WHITE_RABBIT_INSTRUCTIONS"] = "on"
        s = config.settings()
        self.assertEqual((s["todo"]["instructions"], s["recap"]["enabled"]), (True, True))

    def test_log_error_never_raises(self):
        os.environ["WHITE_RABBIT_DIR"] = "/proc/forbidden/dir"
        config.log_error("ctx", ValueError("x"))

    def test_a_wrong_value_is_logged_once_until_the_file_changes(self):
        self.configure(gitlab={"hosts": "gitlab.com"})
        for _ in range(5):
            config.settings()
        self.assertEqual(self.errors().count("gitlab.hosts"), 1)
        self.configure(gitlab={"hosts": ["git.example.org"]})
        self.assertEqual(config.settings()["gitlab"]["hosts"], ["git.example.org"])

