"""Recheck timing: closing windows, sitting times, late rechecks and moved windows.

Synthetic personas only: A (ielts, Europe/Lisbon, scheduled) and D (rust,
Europe/Berlin, on demand). T01 is taught on Tue 13 Oct at 07:29, so its first
2-day window runs from Thu 15 Oct 03:29 to Fri 16 Oct 07:29.
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from helpers import make_ws, run
    from test_sheet import SUBJECT, cold_spec, new_sheet, sheet_row
    from test_grade import make_item, write_sheet
except ImportError:  # run as part of the tests package
    from tests.helpers import make_ws, run
    from tests.test_sheet import SUBJECT, cold_spec, new_sheet, sheet_row
    from tests.test_grade import make_item, write_sheet

from lib import io as fio

TAUGHT = "2026-10-13T07:29+01:00"
SEP = "-- for Claude, do not read aloud --"


class TimingCase(unittest.TestCase):
    PERSONA = "A"
    NOW = "2026-10-15T09:00+01:00"

    def setUp(self):
        self._old_now = os.environ.get("INDELIBLE_NOW")
        os.environ["INDELIBLE_NOW"] = self.NOW
        self.tmp = Path(tempfile.mkdtemp(prefix="indelible-timing-"))
        self.ws = make_ws(self.tmp, self.PERSONA)
        self.sid = {"A": "ielts", "D": "rust"}[self.PERSONA]
        self.sdir = self.ws / self.sid

    def tearDown(self):
        if self._old_now is None:
            os.environ.pop("INDELIBLE_NOW", None)
        else:
            os.environ["INDELIBLE_NOW"] = self._old_now
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def cli(self, args, now=None, code=0, stdin=None):
        r = run([str(a) for a in args], ws=self.ws, now=now or self.NOW, stdin=stdin)
        if code is not None:
            self.assertEqual(r.returncode, code, "%s -> %s\n%s\n%s" % (args, r.returncode, r.stdout, r.stderr))
        return r

    def expose(self, topic, at, kind="teach"):
        fio.append_jsonl(self.sdir / "data" / "exposures.jsonl", {"v": 1, "topic": topic, "at": at, "kind": kind})

    def teach(self, topic="T01", at=TAUGHT):
        """A teach on record: the exposure and taught_at, as session taught leaves them."""
        self.expose(topic, at)
        path = self.sdir / "data" / "topics.json"
        state = fio.read_json(path, default={}) or {}
        state.setdefault(topic, {}).update({"taught_at": at, "taught_by": "sheet"})
        fio.write_json(path, state)

    def blocks(self):
        return dict((b["id"], b) for b in fio.read_jsonl(self.ws / "plan" / "blocks.jsonl"))

    def save_blocks(self, rows):
        fio.write_jsonl(self.ws / "plan" / "blocks.jsonl", list(rows))

    def cold_block(self, bid, start=None, end=None, window=None, content="cold:T01", status="synced"):
        return {"v": 1, "id": bid, "subject": self.sid, "kind": "cold", "start": start, "end": end,
                "window": window, "protected": True, "measurement": False, "soft": False, "pair": None,
                "content": content, "status": status, "cal": None, "moved_from": None, "miss_reason": None}

    def grades_file(self, name, grades):
        path = self.tmp / name
        path.write_text(json.dumps(grades), encoding="utf-8")
        return path

    def parts(self, text):
        self.assertIn(SEP, text)
        return text.split(SEP, 1)


# ==========================================================================
# A window that closes soon (cli-bugs-3)
# ==========================================================================

class ClosingWindowTests(TimingCase):
    def test_the_brief_and_due_give_the_closing_time_and_mark_closing(self):
        self.teach()
        _, claude = self.parts(self.cli(["brief", self.sid]).stdout)
        self.assertIn("RECHECK NOW: T01 Matching headings (49 h, window closes Fri 16 Oct 07:29)", claude)
        # 71.5 h after the teach, 29 minutes before the window closes: cut to 71 h, marked CLOSING
        late = "2026-10-16T07:00+01:00"
        _, claude = self.parts(self.cli(["brief", self.sid], now=late).stdout)
        self.assertIn("RECHECK NOW: T01 Matching headings (71 h, window closes today 07:29, CLOSING)", claude)
        r = self.cli(["due", self.sid, "--list"], now=late)
        self.assertIn("T01 Matching headings · 71 h since last seen · window closes today 07:29, CLOSING", r.stdout)
        data = json.loads(self.cli(["due", self.sid, "--json"], now=late).stdout)
        self.assertEqual(data["tiers"]["1_cold"][0]["closes_at"], "2026-10-16T07:29+01:00")

    def test_issue_prints_the_latest_start_that_still_counts(self):
        self.teach("T01")
        self.teach("T04", "2026-10-13T07:10+01:00")
        spec = cold_spec()
        now = "2026-10-16T07:00+01:00"
        self.assertEqual(new_sheet(self.ws, spec, now=now).returncode, 0)
        self.cli(["sheet", "lint", SUBJECT, spec["id"]], now=now)
        self.cli(["sheet", "build", SUBJECT, spec["id"], "--format", "md"], now=now)
        r = self.cli(["sheet", "issue", SUBJECT, spec["id"]], now=now)
        lines = [ln for ln in r.stdout.splitlines() if ln.startswith("Start by")]
        self.assertEqual(lines, [
            "Start by today 07:10: the 44–72 h window of T04 closes then (a later start is a late recheck "
            "and can't raise mastery).",
            "Start by today 07:29: the 44–72 h window of T01 closes then (a later start is a late recheck "
            "and can't raise mastery).",
        ])

    def test_a_first_recheck_sat_after_its_window_says_it_did_not_count(self):
        self.teach()
        items = [make_item(1, "T01", ["1a"], origin="cold:T01", layer="reading"),
                 make_item(2, "T01", ["2a"], origin="cold:T01", layer="reading")]
        write_sheet(self.ws, self.sid, "ielts-cold-01", "cold", items)
        asks = [{"ask": "1a", "verdict": "right", "check": "filled", "least_sure": False},
                {"ask": "2a", "verdict": "right", "check": "filled", "least_sure": False}]
        path = self.grades_file("late.json", {"date": "2026-10-16", "start": "07:35", "stop": "07:45",
                                              "asks": asks})
        r = self.cli(["grade", "record", self.sid, "ielts-cold-01", "--from", path], now="2026-10-16T08:00+01:00")
        self.assertIn("Levels: no change", r.stdout)
        self.assertIn("Not counted toward level 3: T01 was sat at 72.1 h, outside its 44–72 h window. Treat it "
                      "as a late recheck [measured] and book a fresh one from now (plan.md §7).", r.stdout)

    def test_a_first_recheck_sat_inside_its_window_has_no_late_note(self):
        self.teach()
        items = [make_item(1, "T01", ["1a"], origin="cold:T01", layer="reading"),
                 make_item(2, "T01", ["2a"], origin="cold:T01", layer="reading")]
        write_sheet(self.ws, self.sid, "ielts-cold-01", "cold", items)
        asks = [{"ask": "1a", "verdict": "right", "check": "filled", "least_sure": False},
                {"ask": "2a", "verdict": "right", "check": "filled", "least_sure": False}]
        path = self.grades_file("inwindow.json", {"date": "2026-10-16", "start": "07:20", "stop": "07:28",
                                                  "asks": asks})
        r = self.cli(["grade", "record", self.sid, "ielts-cold-01", "--from", path], now="2026-10-16T08:00+01:00")
        self.assertIn("T01 0 → 3", r.stdout)
        self.assertNotIn("Not counted toward level 3", r.stdout)


if __name__ == "__main__":
    unittest.main()
