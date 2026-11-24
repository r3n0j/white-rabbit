"""Statusline de white-rabbit : MR, notes et ToDo de la session (liens OSC 8, couleurs
ANSI, désactivées par NO_COLOR). Lit le registre sans jamais attendre le réseau : le
rafraîchissement des MR part en processus détaché."""
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
STATUSLINE_MERGED = "38;5;42"
STATUSLINE_FRESH_MERGED = "9;38;5;42"
STATUSLINE_TO_MERGE = "38;5;214"


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


def _mr_item(mr, style):
    return _osc8(_paint(f"{mr['project'].rsplit('/', 1)[-1]}!{mr['iid']}", style), mr["url"])


def _mr_line(data):
    """Ligne `MR:` : compteurs `✓ N merged · ● N to merge` (un compteur à zéro est omis), le
    premier suivi des MR mergées depuis la dernière réponse (barrées), puis après `:` les MR
    non mergées (liens OSC 8 `repo!iid`, état écrit s'il n'est pas « opened ») ; None sans
    aucune MR."""
    merged, to_merge = registry.mr_counts(data)
    counters = []
    if merged:
        counters.append(_paint("✓", STATUSLINE_MERGED) + f" {merged} merged")
        counters += [_mr_item(mr, STATUSLINE_FRESH_MERGED) for mr in registry.fresh_merged(data)]
    if to_merge:
        counters.append(_paint("●", STATUSLINE_TO_MERGE) + f" {to_merge} to merge")
    items = []
    for mr in registry.visible_mrs(data):
        item = _mr_item(mr, STATUSLINE_LINK)
        if mr.get("state") != "opened":
            state = STATE_WORDS.get(mr.get("state"), mr.get("state") or "unknown")
            item += " " + _paint(f"({state})", STATUSLINE_DIM)
        items.append(item)
    parts = [" · ".join(part) for part in (counters, items) if part]
    if not parts:
        return None
    return _paint("MR:", STATUSLINE_LABEL) + " " + " : ".join(parts)


def statusline_lines(data):
    """Footer de la statusline : une ligne `MR:` (compteurs des MR mergées et à merger, puis
    les MR non mergées), une ligne `Notes:` (liens de notes courts, au plus
    STATUSLINE_MAX_NOTES puis `+N`), une ligne `Next:` (l'action next, puis `(+N)` pour les
    autres items) et, à défaut, une ligne `Then:` atténuée (la suite proposée).
    Intitulés aqua, liens bleu clair, next en blanc vif, le reste atténué ;
    sans couleur si NO_COLOR est défini. Une ligne vide est omise."""
    lines = []
    mr_line = _mr_line(data)
    if mr_line:
        lines.append(mr_line)
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
    elif registry.then_item(data):
        lines.append(_paint("Then:", STATUSLINE_LABEL) + " " + _paint(f"◦ {registry.then_item(data)}", STATUSLINE_DIM))
    return lines


def render(raw):
    """Texte de la statusline pour le payload JSON de Claude Code ; "" au moindre doute."""
    try:
        payload = json.loads(raw or "{}")
        sid = payload.get("session_id") if isinstance(payload, dict) else None
        if not isinstance(sid, str):
            return ""
        registry.spawn_refresh()
        return "\n".join(statusline_lines(registry.load(sid)))
    except Exception:
        return ""
