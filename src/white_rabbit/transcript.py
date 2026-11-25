"""Tokens générés par une session, lus dans son transcript Claude Code.

La lecture est incrémentale : un petit cache par session (à côté du registre) garde
l'offset déjà lu et le total, de sorte qu'un transcript de plusieurs jours n'est relu
qu'à partir de ce qui s'y est ajouté. Une réponse du modèle s'étale sur plusieurs
lignes qui répètent son usage : chaque message n'est compté qu'une fois."""
import glob
import json
import os

from white_rabbit import config


def _projects_dir():
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    return os.path.join(base, "projects")


def transcript_path(sid):
    found = glob.glob(os.path.join(glob.escape(_projects_dir()), "*", glob.escape(sid) + ".jsonl"))
    return max(found, key=os.path.getmtime) if found else None


def _cache_path(sid):
    return os.path.join(config.data_dir(), sid + ".out.json")


def _read_cache(sid, path):
    try:
        with open(_cache_path(sid)) as fh:
            cache = json.load(fh)
        if cache.get("path") == path and cache.get("offset", 0) <= os.path.getsize(path):
            return cache
    except (OSError, ValueError, AttributeError):
        pass
    return {"path": path, "offset": 0, "total": 0, "last_id": None, "last_out": 0}


def _count(cache, line):
    try:
        entry = json.loads(line)
    except ValueError:
        return
    message = entry.get("message") if isinstance(entry, dict) and entry.get("type") == "assistant" else None
    usage = message.get("usage") if isinstance(message, dict) else None
    out = usage.get("output_tokens") if isinstance(usage, dict) else None
    if not isinstance(out, int):
        return
    if message.get("id") is not None and message.get("id") == cache["last_id"]:
        cache["total"] += out - cache["last_out"]
    else:
        cache["total"] += out
    cache["last_id"], cache["last_out"] = message.get("id"), out


def output_total(sid):
    """Tokens générés depuis le début de la session, ou None sans transcript."""
    if not sid:
        return None
    path = transcript_path(sid)
    if path is None:
        return None
    cache = _read_cache(sid, path)
    with open(path, "rb") as fh:
        fh.seek(cache["offset"])
        chunk = fh.read()
    end = chunk.rfind(b"\n") + 1
    for line in chunk[:end].splitlines():
        _count(cache, line.decode("utf-8", "replace"))
    if end:
        cache["offset"] += end
        os.makedirs(config.data_dir(), exist_ok=True)
        tmp = _cache_path(sid) + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(cache, fh)
        os.replace(tmp, _cache_path(sid))
    return cache["total"]
