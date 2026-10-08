import os
import sys

from tests.helpers import IsolatedCase
from white_rabbit import adapters

MR = "https://gitlab.com/arx-cf/atlas-api/-/merge_requests/189"


class GitLabTest(IsolatedCase):
    def gl(self, **gitlab):
        self.configure(gitlab=gitlab)
        return adapters.gitlab()

    def test_any_command_output_yields_its_merge_requests_once_in_order(self):
        out = "remote: View merge request:\nremote:   %s\n%s https://gitlab.com/g/ops/-/merge_requests/77" % (MR, MR)
        self.assertEqual(self.gl().mr_urls("git pushon feat/x", out),
                         [MR, "https://gitlab.com/g/ops/-/merge_requests/77"])

    def test_known_reads_are_ignored(self):
        for command in ("glab mr list", "glab mr view 189", "cd x && glab mr diff 3", "glab api projects/1"):
            self.assertEqual(self.gl().mr_urls(command, MR), [], command)

    def test_a_command_is_ignored_only_when_every_segment_is_a_read(self):
        gl = self.gl()
        self.assertEqual(gl.mr_urls("git pushon x 2>&1 | tail -5", MR), [MR])
        self.assertEqual(gl.mr_urls("git pushon x && glab api -X PUT projects/1", MR), [MR])
        self.assertEqual(gl.mr_urls("cat ~/.claude/r/a.json | jq .mrs", MR), [])
        self.assertEqual(gl.mr_urls("FOO=1 grep -r merge_requests notes/", MR), [])
        self.assertEqual(gl.mr_urls("cd repo && glab mr view 3", MR), [])

    def test_a_listed_tool_is_ignored(self):
        self.assertEqual(self.gl(ignore_commands=["gtlb"]).mr_urls("gtlb watch --once", MR), [])

    def test_new_and_diffs_urls_are_not_merge_requests(self):
        out = "https://gitlab.com/g/p/-/merge_requests/new?x=1 https://gitlab.com/g/p/-/merge_requests/12/diffs"
        self.assertEqual(self.gl().mr_urls("echo", out), [])

    def test_unlisted_hosts_are_ignored_and_listed_ones_kept(self):
        own = "https://git.example.org/team/app/-/merge_requests/5"
        self.assertEqual(self.gl().mr_urls("echo", own), [])
        self.assertEqual(self.gl(hosts=["git.example.org"]).mr_urls("echo", own), [own])

    def test_parse(self):
        self.assertEqual(self.gl().parse(MR), ("arx-cf/atlas-api", 189))
        self.assertIsNone(self.gl().parse("https://gitlab.com/x"))

    def test_disabled_adapter_is_none_and_not_imported(self):
        sys.modules.pop("white_rabbit.adapters._gitlab", None)
        self.configure(gitlab={"enabled": False})
        self.assertIsNone(adapters.gitlab())
        self.assertNotIn("white_rabbit.adapters._gitlab", sys.modules)


class NotesTest(IsolatedCase):
    def setUp(self):
        super().setUp()
        self.vault = os.path.join(self.root, "My Vault")
        os.makedirs(os.path.join(self.vault, "B. Areas"))

    def notes(self, **notes):
        self.configure(notes=dict({"enabled": True, "root": self.vault}, **notes))
        return adapters.notes()

    def write(self, *parts):
        path = os.path.join(self.vault, *parts)
        with open(path, "w") as fh:
            fh.write("x")
        return path

    def test_a_markdown_file_under_the_root_is_a_note(self):
        n = self.notes()
        self.assertTrue(n.is_note(self.write("B. Areas", "plan.md")))
        self.assertFalse(n.is_note(os.path.join(self.root, "elsewhere.md")))
        self.assertFalse(n.is_note(self.write("B. Areas", "data.json")))
        self.assertFalse(n.is_note(None))

    def test_root_with_tilde_trailing_slash_or_symlink(self):
        link = os.path.join(self.root, "link-to-vault")
        os.symlink(self.vault, link)
        path = self.write("B. Areas", "plan.md")
        for root in ("~/My Vault/", link):
            self.configure(notes={"enabled": True, "root": root})
            self.assertTrue(adapters.notes().is_note(path), root)

    def test_obsidian_link_encodes_and_drops_the_extension(self):
        path = self.write("B. Areas", "Été plan.md")
        self.assertEqual(self.notes(link="obsidian", vault="Omni").link(path),
                         "obsidian://open?vault=Omni&file=B.%20Areas%2F%C3%89t%C3%A9%20plan")

    def test_obsidian_vault_defaults_to_the_folder_name(self):
        self.assertTrue(self.notes(link="obsidian").link(self.write("a.md")).startswith(
            "obsidian://open?vault=My%20Vault&file="))

    def test_file_and_none_links(self):
        path = self.write("a.md")
        self.assertEqual(self.notes(link="file").link(path), "file://" + os.path.realpath(path).replace(" ", "%20"))
        self.assertIsNone(self.notes(link="none").link(path))

    def test_disabled_by_default(self):
        self.assertIsNone(adapters.notes())
