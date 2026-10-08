"""Mise en place de white-rabbit dans ~/.claude/settings.json : statusline et trois hooks,
avec le chemin absolu de l'exécutable (le PATH des hooks n'est pas garanti)."""
import json
import os
import shutil
import sys

EVENTS = (
    ("PostToolUse", "Bash|Write|Edit", "hook capture", {"timeout": 10}),
    ("Stop", None, "hook refresh", {"async": True}),
    ("SessionStart", None, "hook start", {}),
)


def _ours(command, action):
    return "white-rabbit" in (command or "") and (command or "").endswith(action)


def run(args, settings_path=None, exe=None):
    dry, force = "--dry-run" in args, "--force" in args
    path = settings_path or os.path.expanduser("~/.claude/settings.json")
    exe = exe or shutil.which("white-rabbit") or os.path.realpath(sys.argv[0])
    try:
        with open(path) as fh:
            data = json.load(fh)
    except FileNotFoundError:
        data = {}
    except (OSError, ValueError) as exc:
        print("cannot read %s: %s (nothing changed)" % (path, exc))
        return 1
    changes = []
    hooks = data.setdefault("hooks", {})
    for event, matcher, action, extra in EVENTS:
        groups = hooks.setdefault(event, [])
        if any(_ours(h.get("command"), action) for g in groups for h in g.get("hooks", [])):
            continue
        group = {"hooks": [dict({"type": "command", "command": "%s %s" % (exe, action)}, **extra)]}
        if matcher:
            group = dict({"matcher": matcher}, **group)
        groups.append(group)
        changes.append("+ %s hook: %s %s" % (event, exe, action))
    refused = False
    current = (data.get("statusLine") or {}).get("command")
    if not _ours(current, "statusline"):
        if current is None or force:
            data["statusLine"] = {"type": "command", "command": "%s statusline" % exe}
            changes.append("+ statusLine: %s statusline" % exe)
        else:
            refused = True
            print("a statusline is already set (%s): kept. Run with --force to replace it, or make it "
                  "print the output of `%s statusline` (same stdin)." % (current, exe))
    for line in changes or ["nothing to change"]:
        print(line)
    if dry:
        print("(dry run: nothing written)")
    elif changes:
        if os.path.exists(path):
            shutil.copyfile(path, path + ".bak")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    return 1 if refused else 0
