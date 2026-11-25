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
    def test_render_asks_for_a_background_refresh(self):
        with mock.patch.object(reg, "spawn_refresh") as spawn:
            statusline.render(json.dumps({"session_id": SID}))
        spawn.assert_called_once_with()

    def test_statusline_lines_mr_and_notes(self):
        reg.add_mr(SID, MR1)
        reg.add_mr(SID, MR2)
        reg.add_note(SID, self.note("B. Areas", "2026-09-30-claude-session-registry-design.md"), True)
        reg.add_note(SID, self.note("B. Areas", "plan.md"), False)
        data = reg.load(SID)
        data["mrs"][1]["state"] = "closed"
        self.assertEqual(self.plain(statusline.statusline_lines(data)), [
            "MR: ● 1 to merge : atlas-api!189 · ops!77 (closed)",
            "Notes: claude-session-registry-design · ✎ 1 modified",
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

    def test_statusline_lines_truncate_titles_and_fit_notes_in_the_width(self):
        for i in range(8):
            reg.add_note(SID, self.note("B. Areas", f"note-{i}-{'x' * 40}.md"), True)
        (line,) = self.plain(statusline.statusline_lines(reg.load(SID)))
        titles = line[len("Notes: "):].split(" · ")
        self.assertEqual(len(titles), 3)
        self.assertEqual(titles[-1], "+6")
        self.assertTrue(all(len(t) <= statusline.STATUSLINE_TITLE_WIDTH for t in titles[:-1]))
        self.assertTrue(titles[0].endswith("…"))
        self.assertLessEqual(len(" · ".join(titles[:-1])), statusline.STATUSLINE_NOTES_WIDTH)

    def test_statusline_lines_name_the_created_notes_most_recent_first(self):
        for name, created in (("old", True), ("edited", False), ("new", True), ("touched", False)):
            reg.add_note(SID, self.note("B. Areas", f"{name}.md"), created)
        data = reg.load(SID)
        for note, stamp in zip(data["notes"], ("2026-11-20T10:00:00", "2026-11-21T10:00:00",
                                               "2026-11-22T10:00:00", "2026-11-23T10:00:00")):
            note["last_written"] = stamp
        self.assertEqual(self.plain(statusline.statusline_lines(data)), ["Notes: new · old · ✎ 2 modified"])

    def test_statusline_lines_name_the_modified_notes_when_none_is_created(self):
        reg.add_note(SID, self.note("B. Areas", "a.md"), False)
        reg.add_note(SID, self.note("B. Areas", "b.md"), False)
        data = reg.load(SID)
        data["notes"][1]["last_written"] = "2099-01-01T00:00:00"
        self.assertEqual(self.plain(statusline.statusline_lines(data)), ["Notes: b · a"])

    def test_statusline_lines_only_notes(self):
        reg.add_note(SID, self.note("B. Areas", "n.md"), True)
        self.assertEqual(self.plain(statusline.statusline_lines(reg.load(SID))), ["Notes: n"])

    def test_statusline_lines_todo_line_comes_last(self):
        reg.add_mr(SID, MR1)
        reg.set_todo_items(SID, ["Relire !5", "[next] Valider le plan 2", "Pousser main"])
        self.assertEqual(self.plain(statusline.statusline_lines(reg.load(SID))),
                         ["MR: ● 1 to merge : atlas-api!189", "Next: ▸ Valider le plan 2 (+2)"])

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

    def test_statusline_lines_count_merged_and_to_merge_mrs(self):
        data = {"mrs": [{"project": "g/atlas-api", "iid": 1, "url": "u1", "state": "merged"},
                        {"project": "g/crm-api", "iid": 2, "url": "u2", "state": "merged"},
                        {"project": "g/ops", "iid": 3, "url": "u3", "state": "opened"},
                        {"project": "g/dm-api", "iid": 4, "url": "u4", "state": "closed"}],
                "merged_seen": ["u1", "u2"], "notes": []}
        self.assertEqual(self.plain(statusline.statusline_lines(data)),
                         ["MR: ✓ 2 merged · ● 1 to merge : ops!3 · dm-api!4 (closed)"])

    def test_statusline_lines_keep_the_mr_line_once_all_are_merged(self):
        data = {"mrs": [{"project": "g/atlas-api", "iid": 1, "url": "u1", "state": "merged"}],
                "merged_seen": ["u1"], "notes": []}
        self.assertEqual(self.plain(statusline.statusline_lines(data)), ["MR: ✓ 1 merged"])

    def test_statusline_lines_list_the_mrs_merged_since_the_last_answer(self):
        data = {"mrs": [{"project": "g/atlas-api", "iid": 1, "url": "u1", "state": "merged"},
                        {"project": "g/atlas-api", "iid": 45, "url": "u45", "state": "merged"},
                        {"project": "g/ops", "iid": 3, "url": "u3", "state": "opened"}],
                "merged_seen": ["u1"], "notes": []}
        self.assertEqual(self.plain(statusline.statusline_lines(data)),
                         ["MR: ✓ 2 merged · atlas-api!45 · ● 1 to merge : ops!3"])
        with mock.patch.dict(os.environ, clear=False):
            os.environ.pop("NO_COLOR", None)
            (line,) = statusline.statusline_lines(data)
        self.assertIn("\033]8;;u45\033\\\033[9;38;5;42matlas-api!45\033[0m", line)

    def test_statusline_lines_only_closed_mrs_have_no_counter(self):
        data = {"mrs": [{"project": "g/ops", "iid": 3, "url": "u3", "state": "closed"}], "notes": []}
        self.assertEqual(self.plain(statusline.statusline_lines(data)), ["MR: ops!3 (closed)"])

    def test_statusline_lines_counter_dots_are_coloured(self):
        data = {"mrs": [{"project": "g/atlas-api", "iid": 1, "url": "u1", "state": "merged"},
                        {"project": "g/ops", "iid": 3, "url": "u3", "state": "opened"}],
                "notes": []}
        with mock.patch.dict(os.environ, clear=False):
            os.environ.pop("NO_COLOR", None)
            (line,) = statusline.statusline_lines(data)
        self.assertIn("\033[38;5;42m✓\033[0m 1 merged", line)
        self.assertIn("\033[38;5;214m●\033[0m 1 to merge", line)

    def test_no_color_disables_the_colours(self):
        reg.add_mr(SID, MR1)
        reg.set_todo_items(SID, ["A", "B"])
        with mock.patch.dict(os.environ, {"NO_COLOR": "1"}):
            lines = statusline.statusline_lines(reg.load(SID))
        self.assertFalse(any("\033[" in line for line in lines))
        self.assertEqual(self.plain(lines), ["MR: ● 1 to merge : atlas-api!189", "Next: ▸ A (+1)"])

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

    def test_statusline_lines_then_line_when_nothing_is_next(self):
        reg.set_todo_items(SID, ["[then] Lancer le lot B"])
        self.assertEqual(self.plain(statusline.statusline_lines(reg.load(SID))), ["Then: ◦ Lancer le lot B"])

    def test_statusline_lines_no_then_line_beside_a_next(self):
        data = {"mrs": [], "notes": [], "todos": [{"text": "Relire", "next": True}], "then": "Lancer B"}
        self.assertEqual(self.plain(statusline.statusline_lines(data)), ["Next: ▸ Relire"])

    def plain(self, lines):
        return [re.sub(r"\033\]8;;[^\033]*\033\\|\033\[[\d;]*m", "", line) for line in lines]


    def test_render_reads_the_session_of_the_payload(self):
        reg.add_mr(SID, MR1)
        reg.add_note(SID, self.note("B. Areas", "n.md"), True)
        out = statusline.render(json.dumps({"session_id": SID, "model": {"id": "x"}}))
        plain = re.sub(r"\033\]8;;[^\033]*\033\\|\033\[[\d;]*m", "", out)
        self.assertEqual(plain.splitlines(), ["MR: ● 1 to merge : atlas-api!189", "Notes: n"])

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
