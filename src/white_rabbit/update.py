"""Mise à jour de white-rabbit : dernier tag publié, réinstallation par pipx, puis `setup`.

La vérification quotidienne (`check-update`, lancée en tâche de fond au démarrage d'une
session) garde le dernier tag dans `<data_dir>/latest.json` : la statusline et le panneau
annoncent une version plus récente sans jamais attendre le réseau."""
import json
import os
import re
import shutil
import subprocess
import sys
import time

from white_rabbit import __version__, config, setup

REPO = os.environ.get("WHITE_RABBIT_REPO", "https://github.com/r3n0j/white-rabbit")
TAG = re.compile(r"refs/tags/v(\d+)\.(\d+)\.(\d+)$")
CHECK_EVERY = 86_400
TIMEOUT = 20


def _version(text):
    return tuple(int(part) for part in text.split("."))


def latest_tag(timeout=TIMEOUT):
    """Le tag `vX.Y.Z` le plus haut du dépôt, ou None."""
    out = subprocess.run(["git", "ls-remote", "--tags", "--refs", REPO], capture_output=True, text=True,
                         timeout=timeout, check=True).stdout
    versions = [tuple(int(n) for n in match.groups())
                for match in (TAG.search(line) for line in out.splitlines()) if match]
    return "v%d.%d.%d" % max(versions) if versions else None


def is_newer(tag):
    return bool(tag) and _version(tag.lstrip("v")) > _version(__version__)


def _cache():
    return os.path.join(config.data_dir(), "latest.json")


def cached_latest():
    """Le tag publié plus récent que la version installée, d'après la dernière vérification."""
    try:
        with open(_cache()) as fh:
            tag = json.load(fh).get("tag")
    except (OSError, ValueError, AttributeError):
        return None
    return tag if is_newer(tag) else None


def check():
    """Vérifie le dernier tag et le garde en cache ; silencieux en cas d'échec."""
    try:
        tag = latest_tag()
    except Exception as exc:
        config.log_error("check-update", exc)
        return
    os.makedirs(config.data_dir(), exist_ok=True)
    with open(_cache() + ".tmp", "w") as fh:
        json.dump({"tag": tag, "checked": time.time()}, fh)
    os.replace(_cache() + ".tmp", _cache())


def spawn_check():
    """Lance `check-update` en processus détaché au plus une fois par jour ; n'attend jamais."""
    try:
        if time.time() - os.path.getmtime(_cache()) < CHECK_EVERY:
            return
    except OSError:
        pass
    try:
        os.makedirs(config.data_dir(), exist_ok=True)
        with open(_cache(), "a"):
            os.utime(_cache())
        src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [src, os.environ.get("PYTHONPATH")])))
        subprocess.Popen([sys.executable, "-m", "white_rabbit", "check-update"], env=env,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except Exception as exc:
        config.log_error("spawn check-update", exc)


def _from_pipx():
    return "pipx" in os.path.realpath(sys.prefix).split(os.sep)


def run(args):
    """`white-rabbit update [--force]` : installe le dernier tag puis relance `setup`."""
    try:
        tag = latest_tag()
    except Exception as exc:
        print("cannot read the tags of %s: %s" % (REPO, exc))
        return 1
    if tag is None:
        print("no release tag found in %s" % REPO)
        return 1
    if not is_newer(tag) and "--force" not in args:
        print("white-rabbit %s is up to date" % __version__)
        return 0
    if not _from_pipx() or not shutil.which("pipx"):
        print("white-rabbit %s runs from %s, not from pipx: update that copy (git pull, latest: %s)"
              % (__version__, os.path.dirname(os.path.abspath(__file__)), tag))
        return 1
    print("installing white-rabbit %s…" % tag)
    if subprocess.run(["pipx", "install", "--force", "git+%s@%s" % (REPO, tag)]).returncode != 0:
        return 1
    exe = shutil.which("white-rabbit") or "white-rabbit"
    subprocess.run([exe, "setup"] + (["--panel"] if setup.panel_linked() else []))
    try:
        os.remove(_cache())
    except OSError:
        pass
    print("white-rabbit %s installed; open a new Claude Code session to load it" % tag)
    return 0
