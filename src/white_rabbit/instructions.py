"""Consigne ToDo injectée au SessionStart (cf. `white-rabbit instructions`)."""
import json

TEXT = """\
white-rabbit keeps this session's to-do list in the Claude Code statusline.
Whenever the list of actions expected from the user changes (an action is added, done,
dropped, or the next one changes), run:
  white-rabbit todo "[next] <the very next action>" "<another action>" ...
- one action per argument, the complete list on every call (it replaces the previous one);
- exactly one action prefixed with [next];
- concrete user actions only, never what you plan to do yourself; at most 10;
- run `white-rabbit todo` without arguments when nothing is expected from the user."""


def session_start_output():
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": TEXT}})
