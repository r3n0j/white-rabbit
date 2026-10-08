"""Registre par session de ce qu'une session Claude Code a produit : MR, notes écrites,
ToDo. Un fichier JSON par session dans le dossier de données, muté sous verrou flock.
Le registre ignore les outils : GitLab et les notes passent par les adaptateurs.
Les fonctions publiques ne lèvent jamais : les erreurs vont dans errors.log."""
import concurrent.futures
import contextlib
import datetime
import fcntl
import json
import os
import re
import time

from white_rabbit import adapters, config

REFRESH_TTL = 120
GLAB_TIMEOUT = 5
PURGE_AGE_DAYS = 30
SAFE_SID = re.compile(r"^[\w-]+$")
TODO_NEXT = re.compile(r"^\[next\]\s*", re.IGNORECASE)
TODO_MAX_ITEMS = 10
TODO_MAX_CHARS = 200


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _dir():
    return config.data_dir()


def _file(sid):
    return os.path.join(_dir(), f"{sid}.json")


def _log_error(context, exc):
    config.log_error(context, exc)


def _valid(sid):
    return isinstance(sid, str) and bool(SAFE_SID.match(sid))


def _empty(sid, cwd=None):
    return {"session_id": sid, "cwd": cwd, "updated": None, "mrs": [], "notes": [], "todos": []}


def _read(sid):
    try:
        with open(_file(sid)) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return _empty(sid)
    if not isinstance(data, dict):
        return _empty(sid)
    data.setdefault("mrs", [])
    data.setdefault("notes", [])
    data.setdefault("todos", [])
    data["session_id"] = sid
    return data


def _write(data):
    data["updated"] = _now()
    path = _file(data["session_id"])
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


@contextlib.contextmanager
def _locked(sid):
    os.makedirs(_dir(), exist_ok=True)
    with open(os.path.join(_dir(), f"{sid}.lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _mutate(sid, cwd, change):
    if not _valid(sid):
        return False
    try:
        with _locked(sid):
            data = _read(sid)
            if cwd and not data.get("cwd"):
                data["cwd"] = cwd
            changed = change(data)
            if changed:
                _write(data)
            return changed
    except Exception as exc:
        _log_error(f"mutate {sid}", exc)
        return False


def load(sid):
    """Registre de la session, vide si inconnu ou illisible."""
    if not _valid(sid):
        return _empty(sid)
    return _read(sid)


def add_mr(sid, url, cwd=None):
    """Ajoute une MR (état initial « opened ») ; False si GitLab est désactivé, l'URL
    invalide ou la MR déjà présente."""
    gitlab = adapters.gitlab()
    parsed = gitlab.parse(url) if gitlab else None
    if not parsed:
        return False
    project, iid = parsed

    def change(data):
        if any(mr.get("url") == url for mr in data["mrs"]):
            return False
        data["mrs"].append({
            "url": url, "project": project, "iid": iid, "title": None,
            "source_branch": None, "target_branch": None, "state": "opened",
            "checked_at": None, "added_at": _now(),
        })
        return True

    return _mutate(sid, cwd, change)


def add_note(sid, path, created, cwd=None):
    """Enregistre une note écrite ; une note « created » le reste. False si l'adaptateur
    de notes est désactivé ou si le fichier n'est pas une note."""
    notes = adapters.notes()
    if not notes or not notes.is_note(path):
        return False
    real = os.path.realpath(path)

    def change(data):
        for note in data["notes"]:
            if note.get("path") == real:
                note["last_written"] = _now()
                if created:
                    note["action"] = "created"
                return True
        data["notes"].append({
            "path": real,
            "title": os.path.splitext(os.path.basename(real))[0],
            "action": "created" if created else "modified",
            "last_written": _now(),
        })
        return True

    return _mutate(sid, cwd, change)


def note_link(path):
    """Lien d'une note (obsidian://, file://) ou None (notes désactivées, lien « none »)."""
    try:
        notes = adapters.notes()
        return notes.link(path) if notes and path else None
    except Exception as exc:
        _log_error(f"note_link {path}", exc)
        return None


def todo_items(labels):
    """ToDo tirée d'une liste d'actions : [{"text", "next"}] avec un seul next (la première
    action préfixée de `[next]`, sinon la première ; un `[next]` au-delà du plafond remplace
    la dernière action gardée) ; [] pour une liste vide, None si ce n'est pas une liste de
    chaînes."""
    if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
        return None
    items, flagged = [], None
    for label in labels:
        label = label.strip()
        if label.startswith("- "):
            label = label[2:].strip()
        marked = bool(TODO_NEXT.match(label))
        label = " ".join(TODO_NEXT.sub("", label).split())
        if not label:
            continue
        if len(label) > TODO_MAX_CHARS:
            label = label[:TODO_MAX_CHARS - 1] + "…"
        if marked and flagged is None:
            flagged = len(items)
        items.append({"text": label, "next": False})
    if flagged is not None and flagged >= TODO_MAX_ITEMS:
        items[TODO_MAX_ITEMS - 1] = items[flagged]
        flagged = TODO_MAX_ITEMS - 1
    items = items[:TODO_MAX_ITEMS]
    if items:
        items[flagged or 0]["next"] = True
    return items


def set_todo_items(sid, labels, cwd=None):
    """Remplace la ToDo de la session par la liste d'actions (écrite par `white-rabbit todo`) ;
    False si la liste est invalide ou identique."""
    todos = todo_items(labels)
    if todos is None:
        return False

    def change(data):
        if data.get("todos") == todos:
            return False
        data["todos"] = todos
        data["todos_updated"] = _now()
        return True

    return _mutate(sid, cwd, change)


def visible_todos(data):
    """Items de la ToDo qui ont un texte (registre ancien ou abîmé : liste vide)."""
    todos = data.get("todos")
    if not isinstance(todos, list):
        return []
    return [t for t in todos if isinstance(t, dict) and t.get("text")]


def next_todo(data):
    """Item next de la ToDo, ou None."""
    return next((t for t in visible_todos(data) if t.get("next")), None)


def visible_mrs(data):
    """MR à afficher : toutes sauf les mergées."""
    return [mr for mr in data.get("mrs", []) if mr.get("state") != "merged"]


def visible_notes(data):
    """Notes à afficher : celles encore présentes sur le disque."""
    return [note for note in data.get("notes", []) if os.path.exists(note.get("path") or "")]


def purge(max_age_days=PURGE_AGE_DAYS):
    """Supprime les registres (et verrous) non modifiés depuis max_age_days jours."""
    try:
        limit = time.time() - max_age_days * 86400
        for name in os.listdir(_dir()):
            if name.endswith((".json", ".lock")):
                path = os.path.join(_dir(), name)
                if os.path.getmtime(path) < limit:
                    os.remove(path)
    except FileNotFoundError:
        pass
    except Exception as exc:
        _log_error("purge", exc)


def _stale(mr, now):
    if mr.get("state") == "merged":
        return False
    checked = mr.get("checked_at")
    return checked is None or now - checked >= REFRESH_TTL


def needs_refresh(sid):
    now = time.time()
    return any(_stale(mr, now) for mr in load(sid)["mrs"])


def refresh(sid, timeout=GLAB_TIMEOUT):
    """Rafraîchit les MR périmées en parallèle ; conserve l'état précédent en cas d'échec."""
    if not _valid(sid):
        return
    try:
        gitlab = adapters.gitlab()
        if gitlab is None:
            return
        now = time.time()
        stale = [mr for mr in load(sid)["mrs"] if _stale(mr, now)]
        if not stale:
            return
        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(stale)) as pool:
            futures = {pool.submit(gitlab.fetch_state, mr["url"], timeout): mr["url"] for mr in stale}
            for future in concurrent.futures.as_completed(futures):
                try:
                    results[futures[future]] = future.result()
                except Exception as exc:
                    _log_error(f"refresh {futures[future]}", exc)
        if not results:
            return

        def change(data):
            for mr in data["mrs"]:
                if mr.get("url") in results:
                    mr.update({k: v for k, v in results[mr["url"]].items() if v is not None})
                    mr["checked_at"] = now
            return True

        _mutate(sid, None, change)
    except Exception as exc:
        _log_error(f"refresh {sid}", exc)
