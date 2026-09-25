"""Ledger (owed, decision, defect, hypothesis; close; list) and note append."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from helpers import make_ws, run
except ImportError:  # run as part of the tests package
    from tests.helpers import make_ws, run

from lib import io as fio

NOW = "2026-10-12T09:00+01:00"


class LedgerBase(unittest.TestCase):
    persona = "A"

    def setUp(self):
        self._old_now = os.environ.get("INDELIBLE_NOW")
        os.environ["INDELIBLE_NOW"] = NOW
        self.tmp = Path(tempfile.mkdtemp(prefix="indelible-ledger-"))
        self.ws = make_ws(self.tmp, self.persona)

    def tearDown(self):
        if self._old_now is None:
            os.environ.pop("INDELIBLE_NOW", None)
        else:
            os.environ["INDELIBLE_NOW"] = self._old_now
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def ind(self, *args, **kw):
        return run(list(args), ws=self.ws, now=kw.get("now", NOW), stdin=kw.get("stdin"))

    def rows(self):
        return fio.read_jsonl(self.ws / "ledger.jsonl")


class LedgerTests(LedgerBase):
    def test_owed_needs_a_dated_time_and_closes_with_a_status_event(self):
        r = self.ind("ledger", "add", "owed", "--subject", "ielts", "--what", "Register for the 12 Dec sitting",
                     "--due", "2026-10-14T20:00+01:00")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("L-0001", r.stdout)
        row = self.rows()[0]
        self.assertEqual((row["v"], row["kind"], row["subject"], row["by"]), (1, "owed", "ielts", "learner"))
        self.assertEqual(row["due"], "2026-10-14T20:00+01:00")
        self.assertEqual(row["at"], NOW)

        r = self.ind("ledger", "add", "owed", "--subject", "ielts", "--what", "x", "--due", "2026-10-14")
        self.assertEqual(r.returncode, 2)
        self.assertIn("time", r.stderr)
        r = self.ind("ledger", "add", "owed", "--subject", "ielts", "--what", "x")
        self.assertEqual(r.returncode, 2)
        r = self.ind("ledger", "add", "owed", "--subject", "nope", "--what", "x", "--due", "2026-10-14T20:00+01:00")
        self.assertEqual(r.returncode, 2)
        r = self.ind("ledger", "add", "owed", "--subject", "ielts", "--what", "  ", "--due", "2026-10-14T20:00+01:00")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(len(self.rows()), 1)

        r = self.ind("ledger", "list", "--open")
        self.assertIn("L-0001", r.stdout)
        self.assertIn("[open]", r.stdout)
        r = self.ind("ledger", "close", "L-0001", "--note", "registered")
        self.assertEqual(r.returncode, 0, r.stderr)
        status = self.rows()[-1]
        self.assertEqual((status["kind"], status["ref"], status["status"], status["note"]),
                         ("status", "L-0001", "done", "registered"))
        self.assertNotIn("id", status)
        r = self.ind("ledger", "list", "--open")
        self.assertIn("No ledger rows match", r.stdout)
        r = self.ind("ledger", "list")
        self.assertIn("[done]", r.stdout)
        r = self.ind("ledger", "close", "L-0001")
        self.assertEqual(r.returncode, 1)
        self.assertIn("already done", r.stdout)
        r = self.ind("ledger", "close", "L-0099")
        self.assertEqual(r.returncode, 2)
        r = self.ind("ledger", "close", "nonsense")
        self.assertEqual(r.returncode, 2)

    def test_ids_are_never_reused(self):
        for i in range(3):
            r = self.ind("ledger", "add", "hypothesis", "--subject", "ielts", "--statement", "s%d" % i,
                         "--rule", "r")
            self.assertEqual(r.returncode, 0, r.stderr)
        self.ind("ledger", "close", "L-0002", "--status", "dropped")
        r = self.ind("ledger", "add", "owed", "--what", "w", "--due", "2026-10-13T08:00+01:00", "--by", "claude")
        self.assertIn("L-0004", r.stdout)
        ids = [x.get("id") for x in self.rows() if x.get("kind") != "status"]
        self.assertEqual(ids, ["L-0001", "L-0002", "L-0003", "L-0004"])
        self.assertIsNone(self.rows()[-1]["subject"])
        self.assertEqual(self.rows()[-1]["by"], "claude")

    def test_second_defect_in_a_category_refuses_rule(self):
        args = ["ledger", "add", "defect", "--subject", "ielts", "--category", "late_build",
                "--what", "no sheets ready for the 07:00 block"]
        r = self.ind(*(args + ["--fix-type", "rule", "--fix", "builder runs right after the close message"]))
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.ind(*(args + ["--fix-type", "rule", "--fix", "try harder"]))
        self.assertEqual(r.returncode, 1)
        self.assertIn("Refused", r.stdout)
        self.assertIn("structural", r.stdout)
        self.assertEqual(len(self.rows()), 1)
        r = self.ind(*(args + ["--fix-type", "planner", "--fix", "at least 2 h between a close and the next block"]))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([x["fix_type"] for x in self.rows()], ["rule", "planner"])
        # another category may still start with a rule
        r = self.ind("ledger", "add", "defect", "--subject", "ielts", "--category", "undefined_term",
                     "--what", "'gist' used undefined", "--fix-type", "rule", "--fix", "define every word")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.ind("ledger", "add", "defect", "--subject", "ielts", "--category", "nonsense",
                     "--what", "x", "--fix-type", "lint", "--fix", "y")
        self.assertEqual(r.returncode, 2)

    def test_a_repeat_after_a_structural_fix_still_refuses_rule(self):
        base = ["ledger", "add", "defect", "--subject", "ielts", "--category", "sizing", "--what", "ran 75 of 60 min"]
        self.assertEqual(self.ind(*(base + ["--fix-type", "lint", "--fix", "budget check"])).returncode, 0)
        r = self.ind(*(base + ["--fix-type", "rule", "--fix", "smaller sheets"]))
        self.assertEqual(r.returncode, 1)

    def test_decision_with_safeguard(self):
        r = self.ind("ledger", "add", "decision", "--subject", "ielts", "--summary", "Saturday timed section moves to 09:00",
                     "--why", "I think better early", "--check-on", "2026-11-14")
        self.assertEqual(r.returncode, 2)
        self.assertIn("all three", r.stderr)
        r = self.ind("ledger", "add", "decision", "--subject", "ielts", "--summary", "x", "--why", "y",
                     "--check-on", "14/11/2026", "--rule", "r", "--action", "a")
        self.assertEqual(r.returncode, 2)
        r = self.ind("ledger", "add", "decision", "--subject", "ielts", "--summary", "Timed section moves to 09:00",
                     "--why", "I think better early", "--check-on", "2026-11-14", "--rule", "timed accuracy < 0.70",
                     "--action", "revert")
        self.assertEqual(r.returncode, 0, r.stderr)
        row = self.rows()[-1]
        self.assertEqual(row["safeguard"], {"check_on": "2026-11-14", "rule": "timed accuracy < 0.70",
                                            "action": "revert"})
        self.assertEqual(row["by"], "learner")
        r = self.ind("ledger", "add", "decision", "--subject", "ielts", "--summary", "Drop the extra reading",
                     "--why", "no time")
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("safeguard", self.rows()[-1])

    def test_list_filters_and_json(self):
        self.ind("ledger", "add", "owed", "--subject", "ielts", "--what", "Register", "--due", "2026-10-11T20:00+01:00")
        self.ind("ledger", "add", "hypothesis", "--subject", "ielts", "--statement", "Mornings suit reading",
                 "--rule", "morning accuracy >= evening + 10 points")
        r = self.ind("ledger", "list", "--kind", "owed")
        self.assertIn("L-0001", r.stdout)
        self.assertIn("OVERDUE", r.stdout)
        self.assertNotIn("L-0002", r.stdout)
        r = self.ind("ledger", "list", "--json", "--subject", "ielts")
        data = json.loads(r.stdout)
        self.assertEqual([d["id"] for d in data], ["L-0001", "L-0002"])
        self.assertEqual(data[0]["_status"], "open")


class NoteTests(LedgerBase):
    def test_note_append_adds_timestamped_sections(self):
        r = self.ind("note", "append", "ielts", "session", stdin="Energy 2 of 5.\nChose to keep going.\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        p = self.ws / "ielts" / "notes" / "session.md"
        text = p.read_text(encoding="utf-8")
        self.assertIn("## 2026-10-12T09:00+01:00\n\nEnergy 2 of 5.\nChose to keep going.\n", text)
        r = self.ind("note", "append", "ielts", "session", stdin="Explained in Portuguese first: ação → action",
                     now="2026-10-12T09:30+01:00")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = p.read_text(encoding="utf-8")
        self.assertIn("Energy 2 of 5.", text)
        self.assertIn("## 2026-10-12T09:30+01:00", text)
        self.assertIn("ação → action", text)
        self.assertLess(text.index("Energy"), text.index("ação"))

    def test_note_append_refuses_empty_input_and_bad_names(self):
        self.assertEqual(self.ind("note", "append", "ielts", "session", stdin="   \n").returncode, 2)
        self.assertEqual(self.ind("note", "append", "ielts", "../escape", stdin="x").returncode, 2)
        self.assertEqual(self.ind("note", "append", "nope", "session", stdin="x").returncode, 2)
        self.assertFalse((self.ws / "escape.md").exists())


if __name__ == "__main__":
    unittest.main()
