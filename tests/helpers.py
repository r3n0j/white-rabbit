"""Base de test isolée : données et configuration dans un dossier temporaire."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class IsolatedCase(unittest.TestCase):
    """`self.dir` : dossier de données ; `self.root` : dossier temporaire racine.
    `configure(gitlab={...}, notes={...})` écrit le config.json du test."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.dir = os.path.join(self.root, "data")
        self.config_file = os.path.join(self.root, "config.json")
        env = {k: v for k, v in os.environ.items() if not k.startswith(("SESSION_REGISTRY_", "WHITE_RABBIT_"))}
        env.update(WHITE_RABBIT_DIR=self.dir, WHITE_RABBIT_CONFIG=self.config_file, HOME=self.root)
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def configure(self, **sections):
        with open(self.config_file, "w") as fh:
            json.dump(sections, fh)

    def errors(self):
        try:
            with open(os.path.join(self.dir, "errors.log")) as fh:
                return fh.read()
        except OSError:
            return ""
