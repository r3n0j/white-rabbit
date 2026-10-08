"""Adaptateurs actifs : un adaptateur désactivé n'est ni construit ni importé. Les
modules sont privés (`_gitlab`, `_notes`) pour ne pas masquer les fonctions homonymes."""
from white_rabbit import config


def gitlab(cfg=None):
    cfg = cfg or config.settings()
    if not cfg["gitlab"]["enabled"]:
        return None
    from white_rabbit.adapters._gitlab import GitLab
    return GitLab(cfg["gitlab"])


def notes(cfg=None):
    cfg = cfg or config.settings()
    if not cfg["notes"]["enabled"]:
        return None
    from white_rabbit.adapters._notes import Notes
    return Notes(cfg["notes"])
