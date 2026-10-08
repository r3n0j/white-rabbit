"""Statusline : rendu des lignes MR / Notes / ToDo et lecture du payload de Claude Code."""
import json
import os
import re
import unittest
from unittest import mock

from tests.test_registry import MR1, MR2, SID, RegistryCase
from white_rabbit import registry as reg
from white_rabbit import statusline


class StatuslineTest(RegistryCase):
    def test_statusline_lines_mr_and_notes(self):
        reg.add_mr(SID, MR1)
        reg.add_mr(SID, MR2)
        reg.add_note(SID, self.note("B. Areas", "2026-09-30-claude-session-registry-design.md"), True)
        reg.add_note(SID, self.note("B. Areas", "plan.md"), False)
        data = reg.load(SID)
        data["mrs"][1]["state"] = "closed"
        self.assertEqual(self.plain(statusline.statusline_lines(data)), [
            "MR: atlas-api!189 · ops!77 (closed)",
            "Notes: claude-session-registry-design · plan",
        ])
        self.assertEqual(statusline.statusline_lines(reg.load("inconnue")), [])

    def test_statusline_lines_are_osc8_links(self):
        reg.add_mr(SID, MR1)
        note = self.note("B. Areas", "plan.md")
        reg.add_note(SID, note, True)
        with mock.patch.dict(os.environ, {"NO_COLOR": "1"}):
            mr_line, note_line = statusline.statusline_lines(reg.load(SID))
        self.assertIn(f"\033]8;;{MR1}\033\\atlas-api!189\033]8;;\033\\", mr_line)
        self.assertIn(f"\033]8;;{reg.note_link(note)}\033\\plan\033]8;;\033\\", note_line)

    def test_statusline_lines_truncate_titles_and_cap_notes(self):
        for i in range(8):
            reg.add_note(SID, self.note("B. Areas", f"note-{i}-{'x' * 40}.md"), True)
        (line,) = self.plain(statusline.statusline_lines(reg.load(SID)))
        titles = line[len("Notes: "):].split(" · ")
        self.assertEqual(len(titles), 7)
        self.assertEqual(titles[-1], "+2")
        self.assertTrue(all(len(t) <= statusline.STATUSLINE_TITLE_WIDTH for t in titles[:-1]))
        self.assertTrue(titles[0].endswith("…"))

    def test_statusline_lines_only_notes(self):
        reg.add_note(SID, self.note("B. Areas", "n.md"), True)
        self.assertEqual(self.plain(statusline.statusline_lines(reg.load(SID))), ["Notes: n"])

    def test_statusline_lines_todo_line_comes_last(self):
        reg.add_mr(SID, MR1)
        reg.set_todo_items(SID, ["Relire !5", "[next] Valider le plan 2", "Pousser main"])
        self.assertEqual(self.plain(statusline.statusline_lines(reg.load(SID))),
                         ["MR: atlas-api!189", "Next: ▸ Valider le plan 2 (+2)"])

    def test_statusline_lines_single_todo_has_no_counter_and_is_not_truncated(self):
        reg.set_todo_items(SID, ["y" * 80])
        line, = self.plain(statusline.statusline_lines(reg.load(SID)))
        self.assertEqual(line, "Next: ▸ " + "y" * 80)

    def test_statusline_lines_are_coloured(self):
        reg.add_mr(SID, MR2)
        reg.set_todo_items(SID, ["[next] Valider", "Relire"])
        data = reg.load(SID)
        data["mrs"][0]["state"] = "closed"
        with mock.patch.dict(os.environ, clear=False):
            os.environ.pop("NO_COLOR", None)
            mr_line, todo_line = statusline.statusline_lines(data)
        self.assertTrue(mr_line.startswith("\033[1;38;5;51mMR:\033[0m "))
        self.assertIn("\033[38;5;33mops!77\033[0m", mr_line)
        self.assertIn("\033[2m(closed)\033[0m", mr_line)
        self.assertTrue(todo_line.startswith("\033[1;38;5;51mNext:\033[0m "))
        self.assertIn("\033[1;97m▸ Valider\033[0m", todo_line)
        self.assertTrue(todo_line.endswith("\033[2m(+1)\033[0m"))

    def test_no_color_disables_the_colours(self):
        reg.add_mr(SID, MR1)
        reg.set_todo_items(SID, ["A", "B"])
        with mock.patch.dict(os.environ, {"NO_COLOR": "1"}):
            lines = statusline.statusline_lines(reg.load(SID))
        self.assertFalse(any("\033[" in line for line in lines))
        self.assertEqual(self.plain(lines), ["MR: atlas-api!189", "Next: ▸ A (+1)"])

    def test_statusline_lines_empty_or_malformed_todo_adds_no_line(self):
        reg.set_todo_items(SID, [])
        self.assertEqual(statusline.statusline_lines(reg.load(SID)), [])
        self.assertEqual(statusline.statusline_lines({"mrs": [], "notes": [], "todos": [{"next": True}]}), [])

    def test_deleted_note_is_not_rendered(self):
        kept = self.note("B. Areas", "kept.md")
        gone = self.note("B. Areas", "gone.md")
        reg.add_note(SID, kept, True)
        reg.add_note(SID, gone, True)
        os.remove(gone)
        data = reg.load(SID)
        self.assertEqual([n["title"] for n in reg.visible_notes(data)], ["kept"])
        self.assertEqual(self.plain(statusline.statusline_lines(data)), ["Notes: kept"])

    def plain(self, lines):
        return [re.sub(r"\033\]8;;[^\033]*\033\\|\033\[[\d;]*m", "", line) for line in lines]


    def test_render_reads_the_session_of_the_payload(self):
        reg.add_mr(SID, MR1)
        reg.add_note(SID, self.note("B. Areas", "n.md"), True)
        out = statusline.render(json.dumps({"session_id": SID, "model": {"id": "x"}}))
        plain = re.sub(r"\033\]8;;[^\033]*\033\\|\033\[[\d;]*m", "", out)
        self.assertEqual(plain.splitlines(), ["MR: atlas-api!189", "Notes: n"])

    def test_a_note_without_link_is_plain_text(self):
        self.configure(notes={"enabled": True, "root": self.vault, "link": "none"})
        reg.add_note(SID, self.note("B. Areas", "plan.md"), True)
        line = statusline.statusline_lines(reg.load(SID))[0]
        self.assertIn("plan", line)
        self.assertNotIn("\033]8;;", line)

    def test_render_survives_any_payload(self):
        for raw in ("", "not json", "[]", "{}", '{"session_id": "../etc"}', '{"session_id": 3}'):
            self.assertEqual(statusline.render(raw), "", raw)


if __name__ == "__main__":
    unittest.main()
