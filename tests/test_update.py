import io
import json
import os
import sys
from unittest import mock

from tests.helpers import IsolatedCase
from white_rabbit import statusline, update

TAGS = "a\trefs/tags/v0.5.0\nb\trefs/tags/v0.10.1\nc\trefs/tags/v0.9.9\nd\trefs/tags/beta\n"


def ls_remote(out=TAGS):
    return mock.patch("subprocess.run", return_value=mock.Mock(stdout=out, returncode=0))


class UpdateTest(IsolatedCase):
    def cache(self, tag):
        os.makedirs(self.dir, exist_ok=True)
        with open(os.path.join(self.dir, "latest.json"), "w") as fh:
            json.dump({"tag": tag}, fh)

    def run_update(self, *args):
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            code = update.run(list(args))
        return code, out.getvalue()

    def test_latest_tag_compares_versions_as_numbers(self):
        with ls_remote():
            self.assertEqual(update.latest_tag(), "v0.10.1")

    def test_only_a_newer_cached_tag_is_announced(self):
        self.cache("v999.0.0")
        self.assertEqual(update.cached_latest(), "v999.0.0")
        self.cache("v0.0.1")
        self.assertIsNone(update.cached_latest())

    def test_the_statusline_announces_a_newer_release_first(self):
        self.cache("v999.0.0")
        lines = statusline.statusline_lines({"mrs": [], "notes": [], "todos": [], "then": None})
        self.assertIn("white-rabbit 999.0.0 · white-rabbit update", lines[0])

    def test_check_keeps_the_latest_tag(self):
        with ls_remote(), mock.patch.object(update, "__version__", "0.6.0"):
            update.check()
            self.assertEqual(update.cached_latest(), "v0.10.1")

    def test_up_to_date_installs_nothing(self):
        with ls_remote("x\trefs/tags/v0.0.1\n") as run:
            code, out = self.run_update()
        self.assertEqual((code, run.call_count), (0, 1))
        self.assertIn("is up to date", out)

    def test_a_copy_outside_pipx_is_told_to_pull(self):
        with ls_remote("x\trefs/tags/v999.0.0\n"), mock.patch.object(update, "_from_pipx", return_value=False):
            code, out = self.run_update()
        self.assertEqual(code, 1)
        self.assertIn("git pull", out)

    def test_installs_the_tag_then_runs_setup_with_the_panel_when_linked(self):
        calls = []

        def fake(argv, **kwargs):
            calls.append(argv)
            return mock.Mock(stdout="x\trefs/tags/v999.0.0\n", returncode=0)

        with mock.patch("subprocess.run", side_effect=fake), \
             mock.patch.object(update, "_from_pipx", return_value=True), \
             mock.patch("shutil.which", side_effect=lambda name: "/bin/" + name), \
             mock.patch.object(update.setup, "panel_linked", return_value=True):
            code, _ = self.run_update()
        self.assertEqual(code, 0)
        self.assertEqual(calls[1], ["pipx", "install", "--force", "git+%s@v999.0.0" % update.REPO])
        self.assertEqual(calls[2], ["/bin/white-rabbit", "setup", "--panel"])
