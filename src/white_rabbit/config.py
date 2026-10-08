"""Réglages de white-rabbit : variables d'environnement > config.json > défauts.

Une valeur du mauvais type ou un fichier illisible n'empêchent rien : la valeur par
défaut est gardée et le problème est consigné dans errors.log."""
import copy
import datetime
import json
import os

DEFAULTS = {
    "data_dir": "~/.claude/white-rabbit",
    "gitlab": {
        "enabled": True,
        "hosts": ["gitlab.com"],
        "ignore_commands": ["glab mr list", "glab mr view", "glab mr diff", "glab api",
                            "cat", "jq", "grep", "rg", "curl", "head", "tail", "less"],
        "glab": "glab",
    },
    "notes": {"enabled": False, "root": "~/notes", "link": "file", "vault": "", "extensions": [".md"]},
    "todo": {"instructions": True},
}
CHOICES = {("notes", "link"): ("obsidian", "file", "none")}
PATHS = (("notes", "root"),)


def config_path():
    if os.environ.get("WHITE_RABBIT_CONFIG"):
        return os.environ["WHITE_RABBIT_CONFIG"]
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "white-rabbit", "config.json")


def _same_type(value, default):
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, list):
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    return isinstance(value, type(default))


def _read_file(problems):
    try:
        with open(config_path()) as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        problems.append(("config %s" % config_path(), exc))
        return {}
    if not isinstance(raw, dict):
        problems.append(("config %s" % config_path(), TypeError("not an object")))
        return {}
    return raw


def _merge(raw, problems):
    merged = copy.deepcopy(DEFAULTS)
    for key, default in DEFAULTS.items():
        if key not in raw:
            continue
        if isinstance(default, dict):
            section = raw[key] if isinstance(raw[key], dict) else {}
            for sub, sub_default in default.items():
                if sub not in section:
                    continue
                value = section[sub]
                allowed = CHOICES.get((key, sub))
                if not _same_type(value, sub_default) or (allowed and value not in allowed):
                    problems.append(("config %s.%s" % (key, sub), ValueError(repr(value))))
                    continue
                merged[key][sub] = value
        elif _same_type(raw[key], default):
            merged[key] = raw[key]
        else:
            problems.append(("config %s" % key, ValueError(repr(raw[key]))))
    return merged


def _environment(merged):
    env = os.environ
    if env.get("WHITE_RABBIT_DIR") or env.get("SESSION_REGISTRY_DIR"):
        merged["data_dir"] = env.get("WHITE_RABBIT_DIR") or env["SESSION_REGISTRY_DIR"]
    if env.get("SESSION_REGISTRY_GLAB"):
        merged["gitlab"]["glab"] = env["SESSION_REGISTRY_GLAB"]
    if env.get("SESSION_REGISTRY_VAULT"):
        merged["notes"].update(enabled=True, root=env["SESSION_REGISTRY_VAULT"], link="obsidian")
    if env.get("SESSION_REGISTRY_VAULT_NAME"):
        merged["notes"]["vault"] = env["SESSION_REGISTRY_VAULT_NAME"]


ENV_KEYS = ("WHITE_RABBIT_DIR", "WHITE_RABBIT_CONFIG", "XDG_CONFIG_HOME", "HOME", "SESSION_REGISTRY_DIR",
            "SESSION_REGISTRY_GLAB", "SESSION_REGISTRY_VAULT", "SESSION_REGISTRY_VAULT_NAME")
_CACHE = {}


def _stamp():
    """Contenu du fichier (minuscule) et environnement : une réécriture de même taille dans le
    même tic d'horloge est vue, ce que (taille, mtime) manquerait."""
    path = config_path()
    try:
        with open(path, "rb") as fh:
            found = fh.read()
    except OSError:
        found = None
    return (path, found, tuple(os.environ.get(k) for k in ENV_KEYS))


def settings():
    """Réglages effectifs, chemins développés ; jamais d'exception. Recalculés seulement
    quand le contenu du fichier ou l'environnement change : un problème n'est consigné qu'une fois."""
    stamp = _stamp()
    if _CACHE.get("stamp") != stamp:
        _CACHE.update(stamp=stamp, value=_compute())
    return copy.deepcopy(_CACHE["value"])


def _compute():
    problems = []
    merged = _merge(_read_file(problems), problems)
    _environment(merged)
    merged["data_dir"] = os.path.expanduser(merged["data_dir"])
    for section, key in PATHS:
        merged[section][key] = os.path.expanduser(merged[section][key])
    for context, exc in problems:
        _log(merged["data_dir"], context, exc)
    return merged


def data_dir():
    return settings()["data_dir"]


def _log(folder, context, exc):
    try:
        os.makedirs(folder, exist_ok=True)
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        with open(os.path.join(folder, "errors.log"), "a") as fh:
            fh.write("%s %s: %r\n" % (stamp, context, exc))
    except Exception:
        pass


def log_error(context, exc):
    """Consigne une erreur dans <data_dir>/errors.log ; ne lève jamais."""
    try:
        folder = data_dir()
    except Exception:
        return
    _log(folder, context, exc)
