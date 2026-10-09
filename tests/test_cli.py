import io
import json
import os
import subprocess
import sys
from unittest import mock

from tests.test_registry import MR1, SID, RegistryCase
from white_rabbit import cli, config, instructions
from white_rabbit import registry as reg

ROOT = os.path.join(os.path.dirname(__file__), "..")


def run(argv, payload=None, env=None):
    stdin = io.StringIO(json.dumps(payload) if isinstance(payload, dict) else (payload or ""))
    out = io.StringIO()
    with mock.patch.object(sys, "stdin", stdin), mock.patch.object(sys, "stdout", out), \
         mock.patch.dict(os.environ, env or {}):
        code = cli.main(argv)
    return code, out.getvalue()


class HookCaptureTest(RegistryCase):
    def bash(self, command, stdout="", stderr=""):
        return {"session_id": SID, "cwd": "/r", "tool_name": "Bash", "tool_input": {"command": command},
                "tool_response": {"stdout": stdout, "stderr": stderr}}

    def test_a_merge_request_in_any_output_is_captured(self):
        self.assertEqual(run(["hook", "capture"], self.bash("git pushon feat/x", stderr="remote: " + MR1))[0], 0)
        self.assertEqual([m["url"] for m in reg.load(SID)["mrs"]], [MR1])

    def test_a_read_command_captures_nothing(self):
        run(["hook", "capture"], self.bash("glab mr view 189", stdout=MR1))
        self.assertEqual(reg.load(SID)["mrs"], [])

    def test_write_and_edit_capture_notes(self):
        path = self.note("B. Areas", "plan.md")
        run(["hook", "capture"], {"session_id": SID, "tool_name": "Write", "tool_input": {"file_path": path},
                                  "tool_response": {"type": "create"}})
        self.assertEqual(reg.load(SID)["notes"][0]["action"], "created")

    def test_garbage_payload_exits_zero(self):
        for payload in ("", "not json", "[]"):
            self.assertEqual(run(["hook", "capture"], payload)[0], 0)
        self.assertEqual(run(["hook", "nope"], "{}")[0], 0)


class HookStartTest(RegistryCase):
    def test_injects_the_instructions(self):
        code, out = run(["hook", "start"], {"session_id": SID, "source": "startup"})
        self.assertEqual(code, 0)
        body = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(body["hookEventName"], "SessionStart")
        self.assertEqual(body["additionalContext"], instructions.render(config.settings()))

    def test_recap_alone_is_still_injected(self):
        self.configure(todo={"instructions": False})
        body = json.loads(run(["hook", "start"], {"session_id": SID})[1])["hookSpecificOutput"]
        self.assertIn("**Done**", body["additionalContext"])

    def test_nothing_when_todo_and_recap_are_off(self):
        self.configure(todo={"instructions": False}, recap={"enabled": False})
        self.assertEqual(run(["hook", "start"], {"session_id": SID})[1], "")

    def test_start_purges_old_registries(self):
        reg.add_mr(SID, MR1)
        old = os.path.join(self.dir, SID + ".json")
        os.utime(old, (0, 0))
        run(["hook", "start"], {"session_id": SID})
        self.assertFalse(os.path.exists(old))


class TodoTest(RegistryCase):
    def test_sets_the_todo_of_the_current_session(self):
        run(["todo", "[next] Relire !5", "Merger"], env={"CLAUDE_CODE_SESSION_ID": SID})
        self.assertEqual([t["text"] for t in reg.load(SID)["todos"]], ["Relire !5", "Merger"])

    def test_without_arguments_clears_the_list(self):
        run(["todo", "a"], env={"CLAUDE_CODE_SESSION_ID": SID})
        run(["todo"], env={"CLAUDE_CODE_SESSION_ID": SID})
        self.assertEqual(reg.load(SID)["todos"], [])

    def test_without_session_writes_nothing(self):
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        self.assertEqual(run(["todo", "a"])[0], 0)
        self.assertFalse(os.path.exists(self.dir) and os.listdir(self.dir))


class OtherCommandsTest(RegistryCase):
    def test_add_mr_defaults_to_the_current_session(self):
        code, out = run(["add-mr", MR1], env={"CLAUDE_CODE_SESSION_ID": SID})
        self.assertEqual(code, 0)
        self.assertIn(SID, out)
        self.assertEqual(len(reg.load(SID)["mrs"]), 1)

    def test_statusline_reads_stdin(self):
        reg.add_mr(SID, MR1)
        self.assertIn("atlas-api!189", run(["statusline"], {"session_id": SID})[1])

    def test_instructions_prints_the_text(self):
        self.assertEqual(run(["instructions"])[1].strip(), instructions.render(config.settings()).strip())

    def test_the_launcher_runs_without_installation(self):
        out = subprocess.run([os.path.join(ROOT, "bin", "white-rabbit"), "instructions"],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0)
        self.assertIn("white-rabbit todo", out.stdout)
