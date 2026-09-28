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
                                              "least_sure_line": "none", "asks": asks})
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
                                                  "least_sure_line": "none", "asks": asks})
        r = self.cli(["grade", "record", self.sid, "ielts-cold-01", "--from", path], now="2026-10-16T08:00+01:00")
        self.assertIn("T01 0 → 3", r.stdout)
        self.assertNotIn("Not counted toward level 3", r.stdout)


# ==========================================================================
# The sitting time is asked for, never guessed (cli-bugs-2)
# ==========================================================================

class SittingTimeTests(TimingCase):
    """A recheck issued Thu 15 Oct at 20:50 and sat at 21:00, 61.5 h after the teach."""

    NOW = "2026-10-16T09:00+01:00"
    ISSUED = "2026-10-15T20:50+01:00"
    ASKS = [{"ask": "1a", "verdict": "right", "check": "filled", "least_sure": False},
            {"ask": "2a", "verdict": "right", "check": "filled", "least_sure": False}]

    def setUp(self):
        TimingCase.setUp(self)
        self.teach()
        self.typed = self.tmp / "answers.txt"
        self.typed.write_text("1a: first answer\n2a: second answer\n", encoding="utf-8")

    def sheet(self, sheet_id="ielts-cold-01", stype="cold", origin="cold:T01", issued=ISSUED, evidence=False,
              sitting=None):
        items = [make_item(1, "T01", ["1a"], origin=origin, layer="reading"),
                 make_item(2, "T01", ["2a"], origin=origin, layer="reading")]
        write_sheet(self.ws, self.sid, sheet_id, stype, items, evidence=evidence, sitting=sitting)
        path = self.sdir / "data" / "sheets.jsonl"
        rows = fio.read_jsonl(path)
        for row in rows:
            if row["id"] == sheet_id:
                row["issued_at"] = issued
        fio.write_jsonl(path, rows)

    def grade(self, sheet_id, grades, now=None, code=0):
        path = self.grades_file("%s.json" % sheet_id, grades)
        return self.cli(["grade", "record", self.sid, sheet_id, "--from", path], now=now, code=code)

    def test_a_recheck_sent_the_next_morning_needs_its_date(self):
        self.sheet()
        r = self.cli(["scan", "ingest", self.sid, "ielts-cold-01", "--typed", self.typed], code=1)
        self.assertIn("was issued Thu 15 Oct 20:50. When was it sat? Add --date", r.stdout + r.stderr)
        row = sheet_row(self.ws, "ielts-cold-01")
        self.assertEqual((row["status"], row["evidence"]), ("issued", []))
        r = self.cli(["sheet", "sat", self.sid, "ielts-cold-01", "--start", "21:00"], code=1)
        self.assertIn("When was it sat?", r.stdout + r.stderr)
        r = self.cli(["scan", "ingest", self.sid, "ielts-cold-01", "--typed", self.typed, "--date", "2026-10-15"])
        self.assertIn("marked as taken (2026-10-15)", r.stdout)

    def test_grading_refuses_to_guess_the_time_of_a_recheck_sat_earlier(self):
        self.sheet(evidence=True, sitting={"start": None, "stop": None, "date": "2026-10-15"})
        r = self.grade("ielts-cold-01", {"least_sure_line": "none", "asks": self.ASKS}, code=2)
        self.assertIn("Not recorded: ielts-cold-01 was issued 2026-10-15T20:50+01:00 and has no start or stop time",
                      r.stdout + r.stderr)
        self.assertEqual(sheet_row(self.ws, "ielts-cold-01")["status"], "issued")
        r = self.grade("ielts-cold-01", {"date": "2026-10-15", "start": "21:00", "stop": "21:08", "least_sure_line": "none", "asks": self.ASKS})
        self.assertIn("T01 0 → 3", r.stdout)
        attempt = fio.read_jsonl(self.sdir / "data" / "attempts.jsonl")[0]
        self.assertEqual(attempt["interval_h"], 61.5)

    def test_a_recheck_marked_in_its_own_session_still_needs_no_times(self):
        self.sheet(issued="2026-10-15T20:50+01:00")
        now = "2026-10-15T21:10+01:00"
        r = self.cli(["scan", "ingest", self.sid, "ielts-cold-01", "--typed", self.typed], now=now)
        self.assertIn("marked as taken (2026-10-15)", r.stdout)
        r = self.grade("ielts-cold-01", {"least_sure_line": "none", "asks": self.ASKS}, now="2026-10-15T21:15+01:00")
        self.assertIn("T01 0 → 3", r.stdout)

    def test_practice_sent_the_next_day_keeps_today_with_a_note(self):
        self.sheet("ielts-drills-01", stype="drills", origin="new")
        r = self.cli(["scan", "ingest", self.sid, "ielts-drills-01", "--typed", self.typed])
        self.assertIn("marked as taken (2026-10-16)", r.stdout)
        self.assertIn("note: the taken date is set to today (2026-10-16), but ielts-drills-01 was issued "
                      "2026-10-15. If it was sat on another day, run: sheet sat ielts ielts-drills-01 --date",
                      r.stdout)

    def test_a_sitting_before_the_issue_is_refused(self):
        # "7:00" for a recheck issued at 20:50 the same day: a 12-hour-clock slip, not a sitting
        self.sheet(evidence=True)
        r = self.grade("ielts-cold-01", {"date": "2026-10-15", "start": "07:00", "stop": "07:10", "least_sure_line": "none", "asks": self.ASKS},
                       code=2)
        self.assertIn("The sitting time 2026-10-15T07:00+01:00 is before ielts-cold-01 was issued "
                      "(2026-10-15T20:50+01:00). Check the date and the start time (24-hour clock).",
                      r.stdout + r.stderr)
        self.assertEqual(sheet_row(self.ws, "ielts-cold-01")["status"], "issued")
        # a few minutes early is a clock difference, not a slip
        r = self.grade("ielts-cold-01", {"date": "2026-10-15", "start": "20:47", "stop": "20:57", "least_sure_line": "none", "asks": self.ASKS})
        self.assertIn("T01 0 → 3", r.stdout)

    def test_a_guessed_sitting_time_is_never_before_the_issue(self):
        # practice with no times, sat on the day it was issued: the guess is the issue time, not 12:00
        self.sheet("ielts-drills-01", stype="drills", origin="new", evidence=True,
                   sitting={"start": None, "stop": None, "date": "2026-10-15"})
        self.grade("ielts-drills-01", {"least_sure_line": "none", "asks": self.ASKS})
        attempt = fio.read_jsonl(self.sdir / "data" / "attempts.jsonl")[0]
        self.assertEqual(attempt["at"], self.ISSUED)

    def test_a_mistake_re_served_on_a_sheet_sent_later_needs_its_date(self):
        self.sheet("ielts-mixed-01", stype="mixed", origin="error:E-ielts-0001")
        r = self.cli(["sheet", "sat", self.sid, "ielts-mixed-01"], code=1)
        self.assertIn("When was it sat?", r.stdout + r.stderr)
        self.cli(["sheet", "sat", self.sid, "ielts-mixed-01", "--date", "2026-10-15", "--start", "21:00"])
        self.assertEqual(sheet_row(self.ws, "ielts-mixed-01")["sat"]["date"], "2026-10-15")


# ==========================================================================
# Drills on a later day move the window (instructions-for-claude-9)
# ==========================================================================

class MovedWindowTests(TimingCase):
    """T03 taught Thu 15 Oct 07:00; its drills are sat Fri 16 Oct 13:00, 30 h later."""

    NOW = "2026-10-15T07:00+01:00"
    DRILLS = "2026-10-16T13:00+01:00"

    def obligation(self):
        return [b for b in self.blocks().values() if b["kind"] == "cold"][0]

    def test_drills_on_a_later_day_move_the_window_so_place_and_check_agree(self):
        self.cli(["session", "taught", self.sid, "T03"])
        bid = self.obligation()["id"]
        self.assertEqual(self.obligation()["window"]["to"], "2026-10-18T07:00+01:00")
        r = self.cli(["session", "expose", self.sid, "T03", "--kind", "drill"], now=self.DRILLS)
        self.assertIn("Its 2-day recheck now falls between Sun 18 Oct 09:00 and Mon 19 Oct 13:00", r.stdout)
        self.assertIn("Recheck %s: window moved" % bid, r.stdout)
        self.assertEqual(self.obligation()["window"], {"from": "2026-10-18T09:00+01:00",
                                                       "to": "2026-10-19T13:00+01:00", "basis": "exposure"})
        # 72 h after the teach is outside the old window, 66 h after the drills inside the new one
        self.cli(["plan", "place", bid, "--start", "2026-10-19T07:00+01:00", "--min", "15"], now=self.DRILLS)
        r = self.cli(["plan", "check"], now=self.DRILLS)
        self.assertIn("plan check: PASS", r.stdout)

    def test_drills_graded_on_a_later_day_move_the_window_without_session_expose(self):
        self.cli(["session", "taught", self.sid, "T03"])
        bid = self.obligation()["id"]
        self.cli(["plan", "place", bid, "--start", "2026-10-17T10:00+01:00", "--min", "15"])
        items = [{"n": n, "topic": "T03", "layer": "production", "op": "write-overview", "origin": "new",
                  "text": "Write one overview sentence.", "asks": [{"id": "%da" % n, "label": "Answer:"}]}
                 for n in (1, 2)]
        spec = {"v": 1, "id": "ielts-overview-01-drills", "type": "drills", "subject": self.sid, "title": "Drills",
                "est_min": 8, "tools": "none", "answer_form": "short", "items": items, "blocks": [], "terms": [],
                "theory": None, "least_sure": True}
        fio.write_json(self.sdir / ".indelible" / "specs" / "ielts-overview-01-drills.json", spec)
        fio.write_json(self.sdir / ".indelible" / "keys" / "ielts-overview-01-drills.json",
                       {"%da" % n: {"accept": ["x"]} for n in (1, 2)})
        fio.append_jsonl(self.sdir / "data" / "sheets.jsonl", {
            "v": 1, "id": "ielts-overview-01-drills", "subject": self.sid, "type": "drills", "measures": False,
            "topics": ["T03"], "asks": 2, "est_min": 8, "status": "issued", "created": self.NOW, "lint": "PASS",
            "files": [], "key_sha": "0" * 64, "issued_at": "2026-10-15T08:00+01:00",
            "sat": {"start": None, "stop": None, "date": None},
            "evidence": [{"path": "scans/d.jpg", "kind": "photo"}], "graded_at": None, "opens_unsat": 0,
            "block": None})
        grades = self.grades_file("g.json", {"date": "2026-10-16", "start": "12:50", "stop": "13:00", "least_sure_line": "none", "asks": [
            {"ask": "1a", "verdict": "right", "check": "n/a"}, {"ask": "2a", "verdict": "right", "check": "n/a"}]})
        r = self.cli(["grade", "record", self.sid, "ielts-overview-01-drills", "--from", grades],
                     now="2026-10-16T18:00+01:00")
        self.assertEqual(self.obligation()["window"], {"from": "2026-10-18T09:00+01:00",
                                                       "to": "2026-10-19T13:00+01:00", "basis": "exposure"})
        self.assertIn("WARN: the 2-day recheck booked Sat 17 Oct 10:00 (%s) is outside its new window" % bid,
                      r.stdout)

    def test_a_placed_recheck_left_outside_the_new_window_is_named(self):
        self.cli(["session", "taught", self.sid, "T03"])
        bid = self.obligation()["id"]
        self.cli(["plan", "place", bid, "--start", "2026-10-17T10:00+01:00", "--min", "15"])
        r = self.cli(["session", "expose", self.sid, "T03", "--kind", "drill"], now=self.DRILLS)
        self.assertIn("WARN: the 2-day recheck booked Sat 17 Oct 10:00 (%s) is outside its new window: move it "
                      "inside (plan move %s --start 2026-10-18T09:00+01:00)" % (bid, bid), r.stdout)
        self.assertEqual(r.stdout.count("WARN"), 1)
        self.cli(["plan", "move", bid, "--start", "2026-10-19T07:00+01:00"], now=self.DRILLS)

    def test_a_repair_on_a_later_day_moves_the_window_too(self):
        # T03 taught Thu 07:00, its recheck placed Sat 10:00; a wrong idea on T03 repaired Fri 20:00 (37 h later)
        self.cli(["session", "taught", self.sid, "T03"])
        bid = self.obligation()["id"]
        self.cli(["plan", "place", bid, "--start", "2026-10-17T10:00+01:00", "--min", "15"])
        self.cli(["error", "add", self.sid, "--topic", "T03", "--kind", "belief", "--mode", "D",
                  "--belief", "reads the heading as the first line", "--account", "took the first line"])
        repaired = "2026-10-16T20:00+01:00"
        r = self.cli(["error", "repair", self.sid, "E-ielts-0001"], now=repaired)
        self.assertIn("Its 2-day recheck now falls between Sun 18 Oct 16:00 and Mon 19 Oct 20:00", r.stdout)
        self.assertIn("WARN: the 2-day recheck booked Sat 17 Oct 10:00 (%s) is outside its new window: move it "
                      "inside (plan move %s --start 2026-10-18T16:00+01:00)" % (bid, bid), r.stdout)
        self.assertEqual(self.obligation()["window"], {"from": "2026-10-18T16:00+01:00",
                                                       "to": "2026-10-19T20:00+01:00", "basis": "exposure"})
        self.cli(["plan", "move", bid, "--start", "2026-10-18T16:00+01:00"], now=repaired)
        r = self.cli(["plan", "check"], now=repaired)
        self.assertIn("plan check: PASS", r.stdout)

    def test_a_topic_already_rechecked_keeps_its_windows(self):
        self.cli(["session", "taught", self.sid, "T03"])
        path = self.sdir / "data" / "topics.json"
        state = fio.read_json(path)
        state["T03"]["last_cold"] = "2026-10-17T07:00+01:00"
        state["T03"]["level"] = 3
        fio.write_json(path, state)
        before = self.obligation()["window"]
        r = self.cli(["session", "expose", self.sid, "T03", "--kind", "chat"], now="2026-10-17T09:00+01:00")
        self.assertIn("It cannot be on a 2-day recheck before", r.stdout)
        self.assertEqual(self.obligation()["window"], before)

    def test_a_topic_its_recheck_left_below_3_gets_a_new_window(self):
        # The recheck left T03 below 3: the next warm exposure opens a new 2-day window.
        self.cli(["session", "taught", self.sid, "T03"])
        path = self.sdir / "data" / "topics.json"
        state = fio.read_json(path)
        state["T03"].update({"last_cold": "2026-10-17T07:00+01:00", "level": 2})
        fio.write_json(path, state)
        r = self.cli(["session", "expose", self.sid, "T03", "--kind", "review"], now="2026-10-17T09:00+01:00")
        self.assertIn("Its 2-day recheck now falls between Mon 19 Oct 05:00 and Tue 20 Oct 09:00", r.stdout)


# ==========================================================================
# A recheck that lapses is owed as a late recheck (persona-journeys-1)
# ==========================================================================

class LateRecheckTests(TimingCase):
    """T01's recheck is booked Thu 15 Oct 07:00–07:15, inside its window (it closes Fri 16 Oct 07:29)."""

    NOW = "2026-10-15T07:00+01:00"
    BID = "B-20261015-ielts-2"
    WINDOW = {"from": "2026-10-15T03:29+01:00", "to": "2026-10-16T07:29+01:00"}
    NEXT_DAY = "2026-10-16T12:00+01:00"

    def setUp(self):
        TimingCase.setUp(self)
        self.teach()
        self.save_blocks([self.cold_block(self.BID, "2026-10-15T07:00+01:00", "2026-10-15T07:15+01:00",
                                          window=self.WINDOW)])

    def skip_in_session(self, block=None):
        """A session runs over the recheck's time and the learner skips it; the close defers C9."""
        args = ["session", "open", self.sid, "--planned", "60"] + (["--block", block] if block else [])
        self.cli(args)
        return self.cli(["session", "close", self.sid, "--defer", "learner skipped the recheck"],
                        now="2026-10-15T07:50+01:00")

    def test_the_close_catches_a_recheck_skipped_in_the_session(self):
        self.cli(["session", "open", self.sid, "--planned", "60"])
        r = self.cli(["session", "close", self.sid], now="2026-10-15T07:50+01:00", code=1)
        self.assertIn("FAIL C9 recheck sat: the 2-day recheck %s (today 07:00) was not sat: move it inside its "
                      "window (plan move %s --start 2026-10-15T08:00+01:00), then plan check; the window closes "
                      "Fri 16 Oct 07:29, and after that it is a late recheck (plan.md §7)" % (self.BID, self.BID),
                      r.stdout)
        self.cli(["plan", "move", self.BID, "--start", "2026-10-15T18:00+01:00"], now="2026-10-15T07:51+01:00")
        r = self.cli(["session", "close", self.sid], now="2026-10-15T07:52+01:00")
        self.assertIn("PASS C9 recheck sat", r.stdout)

    def test_a_session_run_on_the_recheck_block_leaves_it_open(self):
        r = self.skip_in_session(block=self.BID)
        self.assertIn("FAIL C9", r.stdout)
        self.assertEqual(self.blocks()[self.BID]["status"], "synced")
        todos = [x for x in fio.read_jsonl(self.ws / "ledger.jsonl") if x.get("kind") == "owed"]
        self.assertEqual([x.get("refs") for x in todos], [[self.BID]])

    def test_after_its_window_the_brief_and_due_flag_a_late_recheck(self):
        self.skip_in_session()
        learner, claude = self.parts(self.cli(["brief", self.sid], now=self.NEXT_DAY).stdout)
        self.assertIn("FLAGS: a 2-day recheck's window has passed", learner)
        for word in ("T01", "Matching headings", self.BID):
            self.assertNotIn(word, learner.split("MASTERY")[0])
        self.assertIn("LATE RECHECK (plan.md §7): %s T01 Matching headings (window closed today 07:29)" % self.BID,
                      claude)
        r = self.cli(["due", self.sid, "--list"], now=self.NEXT_DAY)
        self.assertIn("0. late rechecks, window passed", r.stdout)
        self.assertIn("   %s T01 Matching headings · 76 h since last seen (window closed today 07:29)" % self.BID,
                      r.stdout)
        self.assertLess(r.stdout.index("0. late"), r.stdout.index("1. 2-day"))
        data = json.loads(self.cli(["due", self.sid, "--json"], now=self.NEXT_DAY).stdout)
        self.assertEqual(data["tiers"]["0_late"][0]["block"], self.BID)
        self.assertEqual(data["counts"]["late"], 1)
        self.cli(["set", "root", "learner.vocab", '"technical"'], now=self.NEXT_DAY)
        learner, _ = self.parts(self.cli(["brief", self.sid], now=self.NEXT_DAY).stdout)
        self.assertIn("FLAGS: late recheck (window passed): 1", learner)

    def test_the_flag_clears_once_the_topic_is_served_or_seen_again(self):
        self.skip_in_session()
        # a warm exposure opens the window again: the recheck is not late any more
        self.expose("T01", "2026-10-16T10:00+01:00", kind="chat")
        self.assertNotIn("window has passed", self.cli(["brief", self.sid], now=self.NEXT_DAY).stdout)
        # served cold after its window (a late recheck on file)
        path = self.sdir / "data" / "topics.json"
        state = fio.read_json(path)
        state["T01"]["last_cold"] = "2026-10-19T07:00+01:00"
        fio.write_json(path, state)
        self.assertNotIn("LATE RECHECK", self.cli(["brief", self.sid], now="2026-10-22T12:00+01:00").stdout)

    def test_a_recheck_nobody_turned_up_for_stays_a_missed_block(self):
        learner, claude = self.parts(self.cli(["brief", self.sid], now=self.NEXT_DAY).stdout)
        self.assertIn("missed?", learner)
        self.assertNotIn("window has passed", learner)
        self.assertNotIn("LATE RECHECK", claude)

    def test_c9_names_a_start_after_the_close_even_on_a_quarter_hour(self):
        # closing at 07:45 exactly: 07:45 itself would be caught by C9 again at the next close
        self.cli(["session", "open", self.sid, "--planned", "60"])
        r = self.cli(["session", "close", self.sid], now="2026-10-15T07:45+01:00", code=1)
        self.assertIn("(plan move %s --start 2026-10-15T08:00+01:00)" % self.BID, r.stdout)
        self.cli(["plan", "move", self.BID, "--start", "2026-10-15T08:00+01:00"], now="2026-10-15T07:45+01:00")
        r = self.cli(["session", "close", self.sid], now="2026-10-15T07:46+01:00")
        self.assertIn("PASS C9 recheck sat", r.stdout)

    def test_c9_moves_an_evening_recheck_to_the_next_waking_time(self):
        # Booked 22:00 and skipped: 22:30 would end within 30 min of bedtime (23:00), which plan check fails.
        window = {"from": "2026-10-15T03:29+01:00", "to": "2026-10-16T12:00+01:00"}
        self.save_blocks([self.cold_block(self.BID, "2026-10-15T22:00+01:00", "2026-10-15T22:15+01:00",
                                          window=window)])
        self.cli(["session", "open", self.sid, "--planned", "20"], now="2026-10-15T22:00+01:00")
        r = self.cli(["session", "close", self.sid], now="2026-10-15T22:20+01:00", code=1)
        self.assertIn("(plan move %s --start 2026-10-16T07:00+01:00)" % self.BID, r.stdout)
        self.cli(["plan", "move", self.BID, "--start", "2026-10-16T07:00+01:00"], now="2026-10-15T22:21+01:00")
        self.assertNotIn("FAIL", self.cli(["plan", "check"], now="2026-10-15T22:21+01:00", code=None).stdout)

    def friday_block(self):
        """The recheck on Fri 16 Oct 07:00, with a stored window that ends at 07:17, before
        T01's own window (07:29): plan move keeps to the stored one."""
        window = {"from": "2026-10-15T03:17+01:00", "to": "2026-10-16T07:17+01:00"}
        self.save_blocks([self.cold_block(self.BID, "2026-10-16T07:00+01:00", "2026-10-16T07:15+01:00",
                                          window=window)])
        self.cli(["session", "open", self.sid, "--planned", "60"], now="2026-10-16T07:00+01:00")

    def test_c9_keeps_its_move_inside_the_window_plan_move_accepts(self):
        self.friday_block()
        r = self.cli(["session", "close", self.sid], now="2026-10-16T07:12+01:00", code=1)
        self.assertIn("(plan move %s --start 2026-10-16T07:15+01:00), then plan check; the window closes "
                      "today 07:17" % self.BID, r.stdout)
        self.cli(["plan", "move", self.BID, "--start", "2026-10-16T07:15+01:00"], now="2026-10-16T07:12+01:00")
        r = self.cli(["session", "close", self.sid], now="2026-10-16T07:13+01:00")
        self.assertIn("PASS C9 recheck sat", r.stdout)

    def test_c9_is_info_when_no_start_is_left_in_the_window(self):
        self.friday_block()
        r = self.cli(["session", "close", self.sid], now="2026-10-16T07:25+01:00")
        self.assertIn("INFO C9 recheck sat: the 2-day recheck %s (today 07:00) was not sat, and no time is left in "
                      "its window (it closes today 07:17): it becomes a late recheck, which the next brief flags "
                      "(plan.md §7)" % self.BID, r.stdout)
        self.assertNotIn("plan move", r.stdout)

    def test_a_recheck_sat_inside_its_window_is_not_flagged_late(self):
        self.skip_in_session()
        # an unlinked cold sheet on T01, sat on Friday inside the window, far from the block's time
        items = [make_item(1, "T01", ["1a"], origin="cold:T01", layer="reading"),
                 make_item(2, "T01", ["2a"], origin="cold:T01", layer="reading")]
        write_sheet(self.ws, self.sid, "ielts-cold-01", "cold", items)
        asks = [{"ask": "1a", "verdict": "right", "check": "filled", "least_sure": False},
                {"ask": "2a", "verdict": "right", "check": "filled", "least_sure": False}]
        path = self.grades_file("friday.json", {"date": "2026-10-16", "start": "07:05", "stop": "07:15",
                                                "least_sure_line": "none", "asks": asks})
        r = self.cli(["grade", "record", self.sid, "ielts-cold-01", "--from", path], now="2026-10-16T07:20+01:00")
        self.assertIn("T01 0 → 3", r.stdout)
        self.assertEqual(self.blocks()[self.BID]["status"], "done")
        out = self.cli(["brief", self.sid], now=self.NEXT_DAY).stdout
        self.assertNotIn("window has passed", out)
        self.assertNotIn("LATE RECHECK", out)

    def test_a_recheck_whose_block_stays_open_is_not_flagged_after_an_in_window_serve(self):
        self.skip_in_session()
        # served cold inside the window (Fri 07:05), with the booking left open
        path = self.sdir / "data" / "topics.json"
        state = fio.read_json(path)
        state["T01"]["last_cold"] = "2026-10-16T07:05+01:00"
        fio.write_json(path, state)
        out = self.cli(["brief", self.sid], now=self.NEXT_DAY).stdout
        self.assertNotIn("window has passed", out)
        self.assertNotIn("LATE RECHECK", out)

    def test_c9_is_info_once_the_window_has_closed(self):
        rows = [self.cold_block(self.BID, "2026-10-16T07:00+01:00", "2026-10-16T07:15+01:00", window=self.WINDOW)]
        self.save_blocks(rows)
        self.cli(["session", "open", self.sid, "--planned", "60"], now="2026-10-16T07:00+01:00")
        r = self.cli(["session", "close", self.sid], now="2026-10-16T07:50+01:00")
        self.assertIn("INFO C9 recheck sat: the 2-day recheck %s (today 07:00) was not sat and its window closed "
                      "today 07:29: it is a late recheck at the next session" % self.BID, r.stdout)

    def test_plan_check_labels_the_late_recheck_measured(self):
        # A window that has passed can't be fixed while planning, so it WARNs and the plan still
        # passes: a FAIL would block every preview until the next session runs the late recheck.
        self.save_blocks([self.cold_block(self.BID, window=self.WINDOW, status="planned")])
        r = self.cli(["plan", "check"], now=self.NEXT_DAY, code=0)
        self.assertIn("WARN late_recheck: Recheck %s was never placed and its window closed" % self.BID, r.stdout)
        self.assertIn("run it first at the next session as a late recheck [measured], labelled with its real "
                      "interval (plan.md §7)", r.stdout)
        self.assertNotIn("[practice]", r.stdout)
        self.assertIn("plan check: PASS · 0 hard, 1 warning", r.stdout)
        # Placed after its window: the same WARN, not the cold_window FAIL a move could fix.
        self.save_blocks([self.cold_block(self.BID, window=self.WINDOW, status="planned",
                                          start="2026-10-17T07:00+01:00", end="2026-10-17T07:15+01:00")])
        r = self.cli(["plan", "check", "--json"], now=self.NEXT_DAY, code=0)
        rows = [(f["level"], f["rule"]) for f in json.loads(r.stdout)["findings"] if f["block"] == self.BID]
        self.assertIn(("WARN", "late_recheck"), rows)
        self.assertNotIn(("FAIL", "cold_window"), rows)


# ==========================================================================
# Sick days over a recheck window (persona-journeys-4)
# ==========================================================================

class SickDaysTests(TimingCase):
    """Wed 14 Oct 20:00: the learner is sick on Thu 15 (and maybe Fri 16). T01's recheck is booked Thu 07:00."""

    NOW = "2026-10-14T20:00+01:00"
    BID = "B-20261015-ielts-2"

    def setUp(self):
        TimingCase.setUp(self)
        self.teach()
        window = {"from": "2026-10-15T03:29+01:00", "to": "2026-10-16T07:29+01:00"}
        self.save_blocks([
            self.cold_block(self.BID, "2026-10-15T07:00+01:00", "2026-10-15T07:15+01:00", window=window),
            dict(self.cold_block("B-20261015-ielts-1", "2026-10-15T07:15+01:00", "2026-10-15T08:00+01:00"),
                 kind="repair", content="fix mistakes", protected=False),
        ])

    def sick(self, day):
        self.cli(["set", "root", "time.blocked.+", json.dumps({"date": day, "what": "sick"})])

    def fixes(self):
        data = json.loads(self.cli(["plan", "check", "--json"], code=1).stdout)
        return dict((r["block"], r["fix"]) for r in data["findings"] if r["rule"] == "blocked")

    def test_a_recheck_whose_whole_window_is_sick_days_is_cancelled_not_moved(self):
        self.sick("2026-10-15")
        self.sick("2026-10-16")
        fixes = self.fixes()
        self.assertEqual(fixes[self.BID],
                         "no time is left in its window (Thu 15 Oct 03:29 – Fri 16 Oct 07:29): plan cancel %s "
                         "--reason \"window lost\", add a to-do for a late recheck first at the next session, and apply "
                         "the late-recheck rule then (plan.md §7 and §11)" % self.BID)
        self.assertEqual(fixes["B-20261015-ielts-1"], "move it to another day: plan move B-20261015-ielts-1 --start ISO")

    def test_a_run_of_sick_days_is_one_entry(self):
        # date to to_date, both included: the same finding as one entry per day, and nothing after it.
        self.cli(["set", "root", "time.blocked.+",
                  json.dumps({"date": "2026-10-15", "to_date": "2026-10-16", "what": "sick"})])
        fixes = self.fixes()
        self.assertTrue(fixes[self.BID].startswith("no time is left in its window"), fixes[self.BID])
        self.assertIn("B-20261015-ielts-1", fixes)
        self.cli(["plan", "move", "B-20261015-ielts-1", "--start", "2026-10-17T10:00+01:00"])
        data = json.loads(self.cli(["plan", "check", "--json"], code=None).stdout)
        self.assertNotIn("B-20261015-ielts-1", [r["block"] for r in data["findings"] if r["rule"] == "blocked"],
                         "the day after to_date is free")

    def test_a_run_of_days_needs_its_first_day_and_an_end_after_it(self):
        for bad, why in (({"date": "2026-10-16", "to_date": "2026-10-15", "what": "sick"}, "is before date"),
                         ({"to_date": "2026-10-15", "what": "sick"}, "needs a date")):
            r = self.cli(["set", "root", "time.blocked.+", json.dumps(bad)], code=None)
            self.assertNotEqual(r.returncode, 0, bad)
            self.assertIn(why, r.stdout + r.stderr)

    def test_a_recheck_with_time_left_in_its_window_is_moved_inside_it(self):
        self.sick("2026-10-15")
        self.assertEqual(self.fixes()[self.BID], "move it inside its window (Thu 15 Oct 03:29 – Fri 16 Oct 07:29): "
                                                 "plan move %s --start ISO" % self.BID)
        self.cli(["plan", "move", self.BID, "--start", "2026-10-16T07:00+01:00"])


if __name__ == "__main__":
    unittest.main()
