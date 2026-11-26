"""Mise en place de white-rabbit dans ~/.claude/settings.json : statusline et trois hooks,
avec le chemin absolu de l'exécutable (le PATH des hooks n'est pas garanti) ; avec `--panel`,
le panneau du paquet, par un lien stable déclaré dans CLAUDE_CODE_PLUGIN_DIRS."""
import json
import os
import shlex
import shutil
import sys

EVENTS = (
    ("PostToolUse", "Bash|Write|Edit", "hook capture", {"timeout": 10}),
    ("Stop", None, "hook refresh", {"async": True}),
    ("SessionStart", None, "hook start", {}),
)
STATUSLINE_REFRESH_S = 60
PANEL_LINK = "~/.claude/white-rabbit-panel"
KEYBINDINGS = "~/.claude/keybindings.json"
SHORTCUTS = {"alt+r": "command:rabbit", "alt+1": "command:rabbit-todo", "alt+2": "command:rabbit-mr",
             "alt+3": "command:rabbit-notes", "alt+4": "command:rabbit-git", "alt+5": "command:rabbit-help"}
PLUGIN_DIRS = "CLAUDE_CODE_PLUGIN_DIRS"


def panel_dir():
    """Le panneau livré avec le paquet."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "panel")


def panel_linked():
    return os.path.islink(os.path.expanduser(PANEL_LINK))


def _panel(data, changes):
    """Lien stable vers le panneau du paquet, déclaré dans CLAUDE_CODE_PLUGIN_DIRS ; renvoie
    l'action à faire sur le lien (None s'il est déjà bon)."""
    link = os.path.expanduser(PANEL_LINK)
    relink = None
    if not panel_linked() or os.path.realpath(link) != os.path.realpath(panel_dir()):
        relink = panel_dir()
        changes.append("+ panel: %s -> %s" % (PANEL_LINK, panel_dir()))
    env = data.setdefault("env", {})
    dirs = [d for d in (env.get(PLUGIN_DIRS) or "").split(os.pathsep) if d]
    if not any(os.path.expanduser(d) == link for d in dirs):
        env[PLUGIN_DIRS] = os.pathsep.join(dirs + [PANEL_LINK])
        changes.append("+ env %s: %s" % (PLUGIN_DIRS, PANEL_LINK))
    return relink


def _shortcuts(path, changes, notes):
    """Raccourcis alt du panneau, ajoutés au contexte Global de keybindings.json sans toucher
    une touche déjà prise ; renvoie le fichier à écrire, ou None s'il n'y a rien à changer."""
    try:
        with open(path) as fh:
            data = json.load(fh)
    except FileNotFoundError:
        data = {"$schema": "https://www.schemastore.org/claude-code-keybindings.json",
                "$docs": "https://code.claude.com/docs/en/keybindings", "bindings": []}
    except (OSError, ValueError) as exc:
        notes.append("cannot read %s: %s (shortcuts not added)" % (path, exc))
        return None
    blocks = data.setdefault("bindings", [])
    taken = {key: action for block in blocks if block.get("context") == "Global"
             for key, action in (block.get("bindings") or {}).items()}
    missing = {key: action for key, action in SHORTCUTS.items() if key not in taken}
    for key, action in SHORTCUTS.items():
        if key in taken and taken[key] != action:
            notes.append("%s is already bound to %s: kept" % (key, taken[key]))
    if not missing:
        return None
    target = next((block for block in blocks if block.get("context") == "Global"), None)
    if target is None:
        target = {"context": "Global", "bindings": {}}
        blocks.append(target)
    target.setdefault("bindings", {}).update(missing)
    changes.append("+ shortcuts in %s: %s" % (KEYBINDINGS, ", ".join(sorted(missing))))
    return data


def _link(target):
    link = os.path.expanduser(PANEL_LINK)
    os.makedirs(os.path.dirname(link), exist_ok=True)
    tmp = link + ".tmp"
    if os.path.lexists(tmp):
        os.remove(tmp)
    os.symlink(target, tmp)
    os.replace(tmp, link)


def _command():
    """Commande à écrire : l'exécutable `white-rabbit` du PATH, sinon le script lancé s'il est
    exécutable, sinon `<python> -m white_rabbit` (lancement par `python3 -m white_rabbit`)."""
    found = shutil.which("white-rabbit")
    if found:
        return shlex.quote(found)
    script = os.path.realpath(sys.argv[0])
    if os.access(script, os.X_OK) and not script.endswith(".py"):
        return shlex.quote(script)
    return "%s -m white_rabbit" % shlex.quote(sys.executable)


def _ours(command, action):
    return ("white-rabbit" in (command or "") or "white_rabbit" in (command or "")) and (command or "").endswith(action)


def run(args, settings_path=None, exe=None):
    dry, force = "--dry-run" in args, "--force" in args
    path = settings_path or os.path.expanduser("~/.claude/settings.json")
    exe = shlex.quote(exe) if exe else _command()
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
            data["statusLine"] = {"type": "command", "command": "%s statusline" % exe,
                                  "refreshInterval": STATUSLINE_REFRESH_S}
            changes.append("+ statusLine: %s statusline" % exe)
        else:
            refused = True
            print("a statusline is already set (%s): kept. Run with --force to replace it, or make it "
                  "print the output of `%s statusline` (same stdin)." % (current, exe))
    panel = "--panel" in args or panel_linked()
    relink = _panel(data, changes) if panel else None
    notes = []
    keys_path = os.path.expanduser(KEYBINDINGS) if settings_path is None else os.path.join(
        os.path.dirname(path), "keybindings.json")
    keys = _shortcuts(keys_path, changes, notes) if panel else None
    for line in notes:
        print(line)
    for line in changes or ["nothing to change"]:
        print(line)
    if dry:
        print("(dry run: nothing written)")
    elif changes:
        if relink:
            _link(relink)
        if keys is not None:
            os.makedirs(os.path.dirname(keys_path), exist_ok=True)
            with open(keys_path, "w") as fh:
                json.dump(keys, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
        if os.path.exists(path):
            shutil.copyfile(path, path + ".bak")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    return 1 if refused else 0
