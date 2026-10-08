"""Statusline de white-rabbit : MR, notes et ToDo de la session (liens OSC 8, couleurs
ANSI, désactivées par NO_COLOR). Lecture seule du registre, jamais de réseau."""
import json
import os
import re

from white_rabbit import registry

STATE_WORDS = {"closed": "closed", "locked": "locked"}
STATUSLINE_TITLE_WIDTH = 32
STATUSLINE_MAX_NOTES = 6
STATUSLINE_LABEL = "1;38;5;51"
STATUSLINE_LINK = "38;5;33"
STATUSLINE_NEXT = "1;97"
STATUSLINE_DIM = "2"


def _osc8(text, url):
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"


def _paint(text, style):
    """Texte en couleur ANSI, ou tel quel si NO_COLOR est défini."""
    if os.environ.get("NO_COLOR"):
        return text
    return f"\033[{style}m{text}\033[0m"


def _short_title(title):
    title = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", title or "?")
    if len(title) <= STATUSLINE_TITLE_WIDTH:
        return title
    return title[:STATUSLINE_TITLE_WIDTH - 1] + "…"


def _note_item(note):
    label = _paint(_short_title(note.get("title")), STATUSLINE_LINK)
    url = registry.note_link(note["path"])
    return _osc8(label, url) if url else label


def statusline_lines(data):
    """Footer de la statusline : une ligne `MR:` (liens OSC 8 `repo!iid`, état écrit
    s'il n'est pas « opened »), une ligne `Notes:` (liens de notes courts, au plus
    STATUSLINE_MAX_NOTES puis `+N`) et une ligne `Next:` (l'action next, puis `(+N)` pour les
    autres items). Intitulés aqua, liens bleu clair, next en blanc vif, le reste atténué ;
    sans couleur si NO_COLOR est défini. Une ligne vide est omise."""
    lines = []
    mrs = registry.visible_mrs(data)
    if mrs:
        items = []
        for mr in mrs:
            item = _osc8(_paint(f"{mr['project'].rsplit('/', 1)[-1]}!{mr['iid']}", STATUSLINE_LINK), mr["url"])
            if mr.get("state") != "opened":
                state = STATE_WORDS.get(mr.get("state"), mr.get("state") or "unknown")
                item += " " + _paint(f"({state})", STATUSLINE_DIM)
            items.append(item)
        lines.append(_paint("MR:", STATUSLINE_LABEL) + " " + " · ".join(items))
    notes = registry.visible_notes(data)
    if notes:
        items = [_note_item(note) for note in notes[:STATUSLINE_MAX_NOTES]]
        if len(notes) > STATUSLINE_MAX_NOTES:
            items.append(_paint(f"+{len(notes) - STATUSLINE_MAX_NOTES}", STATUSLINE_DIM))
        lines.append(_paint("Notes:", STATUSLINE_LABEL) + " " + " · ".join(items))
    upcoming = registry.next_todo(data)
    if upcoming:
        rest = len(registry.visible_todos(data)) - 1
        lines.append(_paint("Next:", STATUSLINE_LABEL) + " " + _paint(f"▸ {upcoming['text']}", STATUSLINE_NEXT)
                     + (" " + _paint(f"(+{rest})", STATUSLINE_DIM) if rest else ""))
    return lines


def render(raw):
    """Texte de la statusline pour le payload JSON de Claude Code ; "" au moindre doute."""
    try:
        payload = json.loads(raw or "{}")
        sid = payload.get("session_id") if isinstance(payload, dict) else None
        if not isinstance(sid, str):
            return ""
        return "\n".join(statusline_lines(registry.load(sid)))
    except Exception:
        return ""
