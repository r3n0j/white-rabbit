import json
import os

from tests.helpers import IsolatedCase
from white_rabbit import transcript

SID = "11111111-2222-3333-4444-555555555555"


class OutputTotalTest(IsolatedCase):
    def setUp(self):
        super().setUp()
        self.claude = os.path.join(self.root, "claude")
        os.makedirs(os.path.join(self.claude, "projects", "-repo"))
        self.path = os.path.join(self.claude, "projects", "-repo", SID + ".jsonl")
        self.env = {"CLAUDE_CONFIG_DIR": self.claude}

    def write(self, *entries, partial=""):
        with open(self.path, "a") as fh:
            for entry in entries:
                fh.write(json.dumps(entry) + "\n")
            fh.write(partial)

    def answer(self, mid, out):
        return {"type": "assistant", "message": {"id": mid, "usage": {"output_tokens": out}}}

    def total(self):
        os.environ.update(self.env)
        try:
            return transcript.output_total(SID)
        finally:
            del os.environ["CLAUDE_CONFIG_DIR"]

    def test_counts_each_answer_once_however_many_lines_it_spans(self):
        self.write({"type": "user"}, self.answer("a", 10), self.answer("a", 40), self.answer("b", 5))
        self.assertEqual(self.total(), 45)

    def test_reads_only_what_was_added_and_waits_for_a_whole_line(self):
        self.write(self.answer("a", 10), partial='{"type": "assi')
        self.assertEqual(self.total(), 10)
        with open(self.path, "a") as fh:
            fh.write('stant", "message": {"id": "b", "usage": {"output_tokens": 7}}}\n')
        self.write(self.answer("b", 9))
        self.assertEqual(self.total(), 19)

    def test_none_without_a_transcript(self):
        self.assertIsNone(self.total())
