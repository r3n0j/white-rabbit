import json
import os

from tests.helpers import IsolatedCase
from white_rabbit import config, instructions


class RenderTest(IsolatedCase):
    def render(self, **sections):
        self.configure(**sections)
        return instructions.render(config.settings())

    def test_defaults_give_the_todo_and_the_recap(self):
        text = self.render()
        self.assertIn("white-rabbit todo", text)
        self.assertIn("> ✅ **Done**", text)
        self.assertIn("same action as the `[next]`", text)

    def test_recap_only(self):
        text = self.render(todo={"instructions": False})
        self.assertNotIn("white-rabbit todo", text)
        self.assertIn("**Next**", text)
        self.assertNotIn("[next]", text)

    def test_todo_only(self):
        text = self.render(recap={"enabled": False})
        self.assertIn("white-rabbit todo", text)
        self.assertNotIn("**Done**", text)

    def test_nothing_when_both_are_off(self):
        self.assertEqual(self.render(todo={"instructions": False}, recap={"enabled": False}), "")

    def test_no_note_line_without_notes(self):
        self.assertNotIn("**Note**", self.render())

    def test_no_note_line_when_notes_have_no_link(self):
        self.assertNotIn("**Note**", self.render(notes={"enabled": True, "link": "none"}))

    def test_obsidian_note_line_gives_the_exact_link(self):
        root = os.path.join(self.root, "vault")
        text = self.render(notes={"enabled": True, "root": root, "link": "obsidian", "vault": "Brain"})
        self.assertIn("**Note**", text)
        self.assertIn("obsidian://open?vault=Brain&file=", text)
        self.assertIn(os.path.realpath(root), text)

    def test_file_note_line(self):
        root = os.path.join(self.root, "notes")
        text = self.render(notes={"enabled": True, "root": root, "link": "file"})
        self.assertIn("file://", text)
        self.assertIn(os.path.realpath(root), text)

    def test_no_team_or_personal_names(self):
        text = self.render().lower()
        for name in ("arx", "matrix", "signal", "tank", "neb", "omniscience"):
            self.assertNotIn(name, text)

    def test_session_start_output_carries_the_text(self):
        cfg = config.settings()
        body = json.loads(instructions.session_start_output(cfg))["hookSpecificOutput"]
        self.assertEqual(body["hookEventName"], "SessionStart")
        self.assertEqual(body["additionalContext"], instructions.render(cfg))

    def test_session_start_output_is_none_when_the_variable_is_off(self):
        os.environ["WHITE_RABBIT_INSTRUCTIONS"] = "off"
        self.assertIsNone(instructions.session_start_output(config.settings()))

    def test_session_start_output_is_none_when_empty(self):
        self.configure(todo={"instructions": False}, recap={"enabled": False})
        self.assertIsNone(instructions.session_start_output(config.settings()))
