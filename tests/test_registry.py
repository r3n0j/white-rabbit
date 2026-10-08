"""Registre de session : stockage, MR, notes, ToDo, purge, rafraîchissement.

Contrôle de contrat glab réel (optionnel) :
  SESSION_REGISTRY_CONTRACT_MR=<url d'une MR existante> python3 -m unittest tests.test_registry
"""
import json
import os
import re
import threading
import time
import unittest
from unittest import mock

from tests.helpers import IsolatedCase
from white_rabbit import adapters
from white_rabbit import registry as reg

SID = "11111111-2222-3333-4444-555555555555"
MR1 = "https://gitlab.com/arx-cf/atlas-api/-/merge_requests/189"
MR2 = "https://gitlab.com/arx-cf/ops/-/merge_requests/77"


def NOTES(vault):
    return {"enabled": True, "root": vault, "link": "obsidian", "vault": "Omniscience"}


class RegistryCase(IsolatedCase):
    def setUp(self):
        super().setUp()
        self.vault = os.path.join(self.root, "Omniscience")
        os.makedirs(os.path.join(self.vault, "B. Areas", "Claude Code"))
        self.configure(notes=NOTES(self.vault))
        self.addCleanup(os.environ.pop, "STUB_GLAB_RESPONSES", None)

    def note(self, *parts):
        path = os.path.join(self.vault, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write("x")
        return path


class LibraryTest(RegistryCase):
    def test_unknown_session_is_empty(self):
        data = reg.load(SID)
        self.assertEqual(data["mrs"], [])
        self.assertEqual(data["notes"], [])

    def test_add_mr_parses_project_and_dedups(self):
        self.assertTrue(reg.add_mr(SID, MR1, "/repo"))
        self.assertFalse(reg.add_mr(SID, MR1, "/repo"))
        mrs = reg.load(SID)["mrs"]
        self.assertEqual(len(mrs), 1)
        self.assertEqual(mrs[0]["project"], "arx-cf/atlas-api")
        self.assertEqual(mrs[0]["iid"], 189)
        self.assertEqual(mrs[0]["state"], "opened")
        self.assertIsNone(mrs[0]["checked_at"])

    def test_add_note_only_inside_vault(self):
        inside = self.note("B. Areas", "Claude Code", "x.md")
        outside = os.path.join(self.root, "y.md")
        self.assertTrue(reg.add_note(SID, inside, True))
        self.assertFalse(reg.add_note(SID, outside, True))
        self.assertFalse(reg.add_note(SID, self.note("B. Areas", "a.txt"), True))
        self.assertEqual([n["title"] for n in reg.load(SID)["notes"]], ["x"])

    def test_created_note_stays_created(self):
        path = self.note("B. Areas", "Claude Code", "x.md")
        reg.add_note(SID, path, True)
        reg.add_note(SID, path, False)
        notes = reg.load(SID)["notes"]
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["action"], "created")

    def test_vault_name_comes_from_the_settings(self):
        self.configure(notes={"enabled": True, "root": self.vault, "link": "obsidian", "vault": "TeamVault"})
        self.assertTrue(reg.note_link(self.note("x.md")).startswith("obsidian://open?vault=TeamVault&"))

    def test_obsidian_uri_encodes_spaces_and_accents(self):
        path = self.note("B. Areas", "Claude Code", "Décision réseau.md")
        self.assertEqual(
            reg.note_link(path),
            "obsidian://open?vault=Omniscience&file="
            "B.%20Areas%2FClaude%20Code%2FD%C3%A9cision%20r%C3%A9seau",
        )

    def test_merged_mrs_are_hidden(self):
        reg.add_mr(SID, MR1)
        reg.add_mr(SID, MR2)
        data = reg.load(SID)
        data["mrs"][0]["state"] = "merged"
        self.assertEqual([mr["iid"] for mr in reg.visible_mrs(data)], [77])
        data["mrs"][1]["state"] = "merged"
        self.assertEqual(reg.visible_mrs(data), [])

    def test_corrupted_file_is_treated_as_empty(self):
        os.makedirs(self.dir)
        with open(os.path.join(self.dir, f"{SID}.json"), "w") as fh:
            fh.write('{"mrs": [')
        self.assertEqual(reg.load(SID)["mrs"], [])
        self.assertTrue(reg.add_mr(SID, MR1))
        self.assertEqual(len(reg.load(SID)["mrs"]), 1)

    def test_concurrent_captures_lose_nothing(self):
        urls = [f"https://gitlab.com/arx-cf/r{i}/-/merge_requests/{i}" for i in range(20)]
        threads = [threading.Thread(target=reg.add_mr, args=(SID, u)) for u in urls]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(reg.load(SID)["mrs"]), 20)

    def test_unsafe_session_id_writes_nothing(self):
        self.assertFalse(reg.add_mr("../evil", MR1))
        self.assertFalse(reg.add_mr(None, MR1))
        self.assertFalse(os.path.exists(os.path.join(self.root, "evil.json")))

    def test_todo_items_flags_the_marked_item(self):
        self.assertEqual(reg.todo_items(["Relire !5", "[next] Valider le plan 2"]), [
            {"text": "Relire !5", "next": False}, {"text": "Valider le plan 2", "next": True}])

    def test_todo_items_defaults_next_to_first_and_keeps_first_marked(self):
        self.assertEqual([t["next"] for t in reg.todo_items(["A", "B"])], [True, False])
        self.assertEqual([t["next"] for t in reg.todo_items(["A", "[NEXT] B", "[next] C"])],
                         [False, True, False])

    def test_todo_items_normalize_labels_and_skip_empty_ones(self):
        self.assertEqual(reg.todo_items(["- Nouveau   item", "  ", "[next]"]),
                         [{"text": "Nouveau item", "next": True}])
        self.assertEqual(reg.todo_items([]), [])

    def test_todo_items_cap_count_and_length(self):
        self.assertEqual(len(reg.todo_items(["item %d" % i for i in range(15)])), reg.TODO_MAX_ITEMS)
        long = reg.todo_items(["x" * 300])[0]["text"]
        self.assertEqual(len(long), reg.TODO_MAX_CHARS)
        self.assertTrue(long.endswith("…"))

    def test_todo_items_keep_a_next_beyond_the_cap(self):
        todos = reg.todo_items(["item %d" % i for i in range(12)] + ["[next] la vraie"])
        self.assertEqual(len(todos), reg.TODO_MAX_ITEMS)
        self.assertEqual(todos[-1], {"text": "la vraie", "next": True})
        self.assertEqual(sum(t["next"] for t in todos), 1)

    def test_todo_items_reject_non_lists_of_strings(self):
        self.assertIsNone(reg.todo_items("A"))
        self.assertIsNone(reg.todo_items(None))
        self.assertIsNone(reg.todo_items(["A", 3]))
        self.assertFalse(reg.set_todo_items(SID, {"x": 1}))

    def test_set_todo_items_replaces_and_keeps_mrs_and_notes(self):
        reg.add_mr(SID, MR1)
        self.assertTrue(reg.set_todo_items(SID, ["A", "B"]))
        self.assertTrue(reg.set_todo_items(SID, ["[next] C"]))
        self.assertFalse(reg.set_todo_items(SID, ["[next] C"]))
        data = reg.load(SID)
        self.assertEqual(data["todos"], [{"text": "C", "next": True}])
        self.assertTrue(data["todos_updated"])
        self.assertEqual([m["url"] for m in data["mrs"]], [MR1])

    def test_empty_items_clear_the_list(self):
        reg.set_todo_items(SID, ["A"])
        self.assertTrue(reg.set_todo_items(SID, []))
        self.assertEqual(reg.load(SID)["todos"], [])
        self.assertIsNone(reg.next_todo(reg.load(SID)))

    def test_old_registry_without_todos_reads_as_empty(self):
        os.makedirs(self.dir, exist_ok=True)
        with open(os.path.join(self.dir, SID + ".json"), "w") as fh:
            json.dump({"session_id": SID, "mrs": [], "notes": []}, fh)
        data = reg.load(SID)
        self.assertEqual(reg.visible_todos(data), [])
        self.assertIsNone(reg.next_todo(data))
        self.assertEqual(reg.load("inconnue")["todos"], [])

    def test_visible_todos_skips_malformed_items(self):
        data = {"todos": [{"text": "A", "next": True}, {"next": False}, "x", None]}
        self.assertEqual(reg.visible_todos(data), [{"text": "A", "next": True}])
        self.assertEqual(reg.visible_todos({"todos": "pas une liste"}), [])

    def test_set_todo_items_with_unsafe_session_id_writes_nothing(self):
        self.assertFalse(reg.set_todo_items("../x", ["A"]))
        self.assertFalse(reg.set_todo_items(None, ["A"]))
        self.assertFalse(os.path.exists(self.dir) and os.listdir(self.dir))

    def test_mrs_are_ignored_when_gitlab_is_disabled(self):
        self.configure(gitlab={"enabled": False})
        self.assertFalse(reg.add_mr(SID, MR1))
        self.assertEqual(reg.load(SID)["mrs"], [])

    def test_notes_are_ignored_when_notes_are_disabled(self):
        self.configure(notes={"enabled": False})
        self.assertFalse(reg.add_note(SID, self.note("B. Areas", "x.md"), True))

    def test_note_link_is_none_without_notes(self):
        self.configure(notes={"enabled": False})
        self.assertIsNone(reg.note_link("/x/a.md"))

    def test_registry_files_live_in_the_data_dir(self):
        reg.add_mr(SID, MR1)
        self.assertTrue(os.path.exists(os.path.join(self.dir, SID + ".json")))

    def test_purge_removes_old_files_only(self):
        reg.add_mr(SID, MR1)
        reg.add_mr("old", MR1)
        old = time.time() - 31 * 86400
        for name in ("old.json", "old.lock"):
            os.utime(os.path.join(self.dir, name), (old, old))
        reg.purge(30)
        self.assertTrue(os.path.exists(os.path.join(self.dir, f"{SID}.json")))
        self.assertFalse(os.path.exists(os.path.join(self.dir, "old.json")))
        self.assertFalse(os.path.exists(os.path.join(self.dir, "old.lock")))


STUB_GLAB = r'''#!/usr/bin/env python3
import json, os, sys, time
responses = json.load(open(os.environ["STUB_GLAB_RESPONSES"]))
iid = sys.argv[-1].rsplit("/", 1)[-1]
entry = responses.get(iid)
if entry is None:
    sys.exit(1)
time.sleep(entry.pop("_sleep", 0))
print(json.dumps(entry))
'''


class GlabStubCase(RegistryCase):
    def setUp(self):
        super().setUp()
        self.glab = os.path.join(self.root, "glab")
        with open(self.glab, "w") as fh:
            fh.write(STUB_GLAB)
        os.chmod(self.glab, 0o755)
        self.responses = os.path.join(self.root, "responses.json")
        os.environ["STUB_GLAB_RESPONSES"] = self.responses
        self.configure(notes=NOTES(self.vault), gitlab={"glab": self.glab})

    def respond(self, mapping):
        with open(self.responses, "w") as fh:
            json.dump(mapping, fh)


class RefreshTest(GlabStubCase):
    def test_refresh_updates_state_and_branches(self):
        reg.add_mr(SID, MR1)
        self.respond({"189": {"state": "merged", "title": "feat: x",
                              "source_branch": "feat/x", "target_branch": "develop"}})
        self.assertTrue(reg.needs_refresh(SID))
        reg.refresh(SID)
        mr = reg.load(SID)["mrs"][0]
        self.assertEqual(mr["state"], "merged")
        self.assertEqual(mr["source_branch"], "feat/x")
        self.assertIsNotNone(mr["checked_at"])
        self.assertFalse(reg.needs_refresh(SID))

    def test_merged_is_never_rechecked(self):
        reg.add_mr(SID, MR1)
        self.respond({"189": {"state": "merged"}})
        reg.refresh(SID)
        self.assertFalse(reg.needs_refresh(SID))
        self.respond({"189": {"state": "opened"}})
        reg.REFRESH_TTL = 0
        try:
            reg.refresh(SID)
        finally:
            reg.REFRESH_TTL = 120
        self.assertEqual(reg.load(SID)["mrs"][0]["state"], "merged")

    def test_failure_keeps_previous_state(self):
        reg.add_mr(SID, MR1)
        self.respond({})
        reg.refresh(SID)
        mr = reg.load(SID)["mrs"][0]
        self.assertEqual(mr["state"], "opened")
        self.assertIsNone(mr["checked_at"])
        self.assertTrue(reg.needs_refresh(SID))

    def test_slow_glab_respects_timeout(self):
        reg.add_mr(SID, MR1)
        reg.add_mr(SID, MR2)
        self.respond({"189": {"state": "merged", "_sleep": 10},
                      "77": {"state": "closed", "_sleep": 10}})
        start = time.time()
        reg.refresh(SID, timeout=1)
        self.assertLess(time.time() - start, 3)
        self.assertEqual([m["state"] for m in reg.load(SID)["mrs"]], ["opened", "opened"])

    def test_timeout_holds_beyond_eight_mrs(self):
        responses = {}
        for i in range(20):
            reg.add_mr(SID, f"https://gitlab.com/arx-cf/r{i}/-/merge_requests/{i + 1}")
            responses[str(i + 1)] = {"state": "merged", "_sleep": 10}
        self.respond(responses)
        start = time.time()
        reg.refresh(SID, timeout=1)
        self.assertLess(time.time() - start, 2.5)


@unittest.skipUnless(os.environ.get("SESSION_REGISTRY_CONTRACT_MR"), "contrôle de contrat glab réel")
class GlabContractTest(unittest.TestCase):
    def test_real_glab_api_returns_expected_fields(self):
        url = os.environ["SESSION_REGISTRY_CONTRACT_MR"]
        result = adapters.gitlab().fetch_state(url, 10)
        self.assertIn(result["state"], {"opened", "closed", "merged", "locked"})
        self.assertTrue(result["source_branch"])
        self.assertTrue(result["target_branch"])
        self.assertTrue(result["title"])


if __name__ == "__main__":
    unittest.main()
