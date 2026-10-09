"""Commande `white-rabbit` : hooks Claude Code, ToDo, statusline, mise en place."""
import json
import os
import sys

from white_rabbit import adapters, config, instructions, registry, statusline

USAGE = """\
usage: white-rabbit <command>
  hook capture|refresh|start   Claude Code hooks (payload on stdin)
  todo ["[next] action" ...]   replace this session's to-do list
  statusline                   render the statusline (payload on stdin)
  add-mr <url> [session]       add a merge request by hand
  instructions                 print the to-do and recap instructions given to Claude
  setup [--dry-run] [--force]  register the statusline and hooks in ~/.claude/settings.json"""


def _payload():
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _tool_output(response):
    if isinstance(response, dict):
        return "%s\n%s" % (response.get("stdout") or "", response.get("stderr") or "")
    return str(response or "")


def _capture(payload):
    sid, cwd = payload.get("session_id"), payload.get("cwd")
    tool, tool_input = payload.get("tool_name"), payload.get("tool_input") or {}
    response = payload.get("tool_response") or {}
    if tool == "Bash":
        gitlab = adapters.gitlab()
        if gitlab:
            for url in gitlab.mr_urls(tool_input.get("command") or "", _tool_output(response)):
                registry.add_mr(sid, url, cwd)
    elif tool in ("Write", "Edit"):
        created = tool == "Write" and isinstance(response, dict) and response.get("type") == "create"
        registry.add_note(sid, tool_input.get("file_path"), created, cwd)


def _hook(action):
    payload = _payload()
    if action == "capture":
        _capture(payload)
    elif action == "refresh":
        registry.refresh(payload.get("session_id"))
    elif action == "start":
        registry.purge()
        output = instructions.session_start_output(config.settings())
        if output:
            print(output)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    command, rest = (args[0], args[1:]) if args else ("", [])
    try:
        if command == "hook":
            _hook(rest[0] if rest else "")
        elif command == "todo":
            sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
            if sid:
                registry.set_todo_items(sid, rest, os.getcwd())
        elif command == "statusline":
            text = statusline.render(sys.stdin.read())
            if text:
                print(text)
        elif command == "add-mr" and rest:
            sid = rest[1] if len(rest) > 1 else os.environ.get("CLAUDE_CODE_SESSION_ID")
            if registry.add_mr(sid, rest[0]):
                print("merge request added to session %s" % sid)
        elif command == "instructions":
            print(instructions.render(config.settings()))
        elif command == "setup":
            from white_rabbit import setup
            return setup.run(rest)
        else:
            print(USAGE)
    except Exception as exc:
        config.log_error("cli %s" % command, exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
