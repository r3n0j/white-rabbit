"""Adaptateur de notes : un fichier écrit sous `root` (extensions listées) est une note ;
son lien est obsidian://, file:// ou absent."""
import os
import urllib.parse


class Notes:
    def __init__(self, settings):
        self.root = os.path.realpath(settings["root"])
        self.kind = settings["link"]
        self.vault = settings["vault"] or os.path.basename(self.root)
        self.extensions = tuple(settings["extensions"])

    def is_note(self, path):
        if not isinstance(path, str) or not path.endswith(self.extensions):
            return False
        return os.path.realpath(path).startswith(self.root + os.sep)

    def link(self, path):
        real = os.path.realpath(path)
        if self.kind == "obsidian":
            rel = os.path.splitext(os.path.relpath(real, self.root))[0]
            return "obsidian://open?vault=%s&file=%s" % (urllib.parse.quote(self.vault, safe=""),
                                                        urllib.parse.quote(rel, safe=""))
        if self.kind == "file":
            return "file://" + urllib.parse.quote(real)
        return None
