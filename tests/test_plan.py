"""plan add/place/move/cancel/done/miss/list/week/check/diff and cal ack (cmd_plan.py).

Persona A (IELTS, Europe/Lisbon). INDELIBLE_NOW is Monday 12 Oct 2026 09:00
+01:00. Times are before the 25 Oct clock change (+01:00) except in the one
test about that change.
"""

import json
import os
import re
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
SID = "ielts"


class PlanCase(unittest.TestCase):
    """One persona-A workspace per class, copied fresh for every test."""

    PERSONA = "A"

    @classmethod
    def setUpClass(cls):
        cls._root = Path(tempfile.mkdtemp(prefix="indelible-plan-"))
        (cls._root / "template").mkdir()
        cls._template = make_ws(cls._root / "template", cls.PERSONA)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(str(cls._root), ignore_errors=True)

    def setUp(self):
        self._old_now = os.environ.get("INDELIBLE_NOW")
        os.environ["INDELIBLE_NOW"] = NOW
        self.ws = self._root / ("case-" + self._testMethodName)
        shutil.copytree(str(self._template), str(self.ws))
        # Fixed settings, independent of the asset defaults.
        self.set_root("time.sleep", {"bed": "23:00", "wake": "07:00"})
        self.set_root("time.weekly_ceiling_min", 336)
        self.set_root("time.blocked", [])

    def tearDown(self):
        if self._old_now is None:
            os.environ.pop("INDELIBLE_NOW", None)
        else:
            os.environ["INDELIBLE_NOW"] = self._old_now

    # ---- helpers ------------------------------------------------------------
    def cli(self, *args, **kw):
        return run([str(a) for a in args], ws=self.ws, now=kw.get("now", NOW))

    def ok(self, *args, **kw):
        r = self.cli(*args, **kw)
        self.assertEqual(r.returncode, 0, "exit %s\n%s\n%s" % (r.returncode, r.stdout, r.stderr))
        return r

    def add(self, kind, start, minutes, *extra):
        r = self.ok("plan", "add", SID, "--kind", kind, "--start", start, "--min", minutes, *extra)
        bid = r.stdout.split()[0]
        self.assertRegex(bid, r"^B-\d{8}-ielts-\d+$")
        return bid

    def blocks(self):
        return dict((b["id"], b) for b in fio.read_jsonl(self.ws / "plan" / "blocks.jsonl"))

    def check(self, now=NOW):
        r = self.cli("plan", "check", "--json", now=now)
        self.assertIn(r.returncode, (0, 1), r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(r.returncode == 1, data["result"] == "FAIL")
        return r.returncode, data

    def findings(self, data, level=None, rule=None, block=None):
        return [f for f in data["findings"]
                if (level is None or f["level"] == level) and (rule is None or f["rule"] == rule)
                and (block is None or f["block"] == block)]

    def set_root(self, dotted, value):
        path = self.ws / "indelible.json"
        cfg = fio.read_json(path)
        node = cfg
        parts = dotted.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = value
        fio.write_json(path, cfg)

    def expose(self, topic, at, kind="teach"):
        fio.append_jsonl(self.ws / SID / "data" / "exposures.jsonl", {"v": 1, "topic": topic, "at": at, "kind": kind})

    def write_block(self, **fields):
        row = {"v": 1, "id": None, "subject": SID, "kind": "cold", "start": None, "end": None, "window": None,
               "protected": True, "measurement": False, "soft": False, "pair": None, "content": "cold:T01",
               "status": "planned", "cal": None, "moved_from": None, "miss_reason": None}
        row.update(fields)
        path = self.ws / "plan" / "blocks.jsonl"
        fio.write_jsonl(path, fio.read_jsonl(path) + [row])
        return row["id"]


# ==========================================================================
# Recheck windows (default cold_window_h 44-72)
# ==========================================================================

class ColdWindowTests(PlanCase):
    def test_paired_cold_at_30h_and_80h_rejected_66h_accepted(self):
        teach = self.add("teach", "2026-10-13T14:00+01:00", 60, "--content", "new skill")
        for start, hours in (("2026-10-14T20:00+01:00", 30), ("2026-10-16T22:00+01:00", 80)):
            cold = self.add("cold", start, 20, "--content", "cold:T01", "--pair", teach)
            rc, data = self.check()
            self.assertEqual(rc, 1, "a recheck %d h after its teach must fail" % hours)
            hits = self.findings(data, "FAIL", "cold_window", cold)
            self.assertEqual(len(hits), 1, data)
            self.assertIn("%d h" % hours, hits[0]["message"])
            self.assertTrue(hits[0]["fix"])
            self.ok("plan", "cancel", cold, "--reason", "test")
        cold = self.add("cold", "2026-10-16T08:00+01:00", 20, "--content", "cold:T01", "--pair", teach)
        rc, data = self.check()
        self.assertEqual(rc, 0, data)
        self.assertEqual(self.findings(data, "FAIL"), [])
        self.assertTrue(self.blocks()[cold]["protected"])

    def test_window_counts_elapsed_hours_across_the_clock_change(self):
        # Lisbon leaves summer time on 25 Oct: Fri 14:00 +01:00 to Mon 13:30 +00:00 is 72.5 h, not 71.5 h.
        teach = self.add("teach", "2026-10-23T14:00+01:00", 60)
        late = self.add("cold", "2026-10-26T13:30+00:00", 20, "--content", "cold:T01", "--pair", teach)
        rc, data = self.check()
        self.assertEqual(rc, 1, data)
        hits = self.findings(data, "FAIL", "cold_window", late)
        self.assertEqual(len(hits), 1, data)
        self.assertIn("72.5 h", hits[0]["message"])
        self.ok("plan", "cancel", late, "--reason", "test")
        self.add("cold", "2026-10-26T12:30+00:00", 20, "--content", "cold:T01", "--pair", teach)  # 71.5 h
        rc, data = self.check()
        self.assertEqual(self.findings(data, "FAIL"), [], data)

    def test_cold_window_from_recorded_exposure(self):
        self.expose("T02", "2026-10-12T03:00+01:00")
        cases = (("2026-10-13T09:00+01:00", 30, 1), ("2026-10-15T11:00+01:00", 80, 1),
                 ("2026-10-14T21:00+01:00", 66, 0))
        for start, hours, want in cases:
            cold = self.add("cold", start, 20, "--content", "cold:T02")
            rc, data = self.check()
            self.assertEqual(rc, want, "%d h: %s" % (hours, data))
            self.assertEqual(len(self.findings(data, "FAIL", "cold_window", cold)), want)
            self.ok("plan", "cancel", cold, "--reason", "test")

    def test_place_inside_window_only(self):
        self.expose("T01", "2026-10-11T17:00+01:00")
        obl = self.write_block(id="B-20261013-ielts-1", window={"from": "2026-10-13T13:00+01:00",
                                                                 "to": "2026-10-14T17:00+01:00"})
        for start in ("2026-10-12T23:00+01:00", "2026-10-15T01:00+01:00"):  # 30 h and 80 h
            r = self.cli("plan", "place", obl, "--start", start, "--min", 20)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("outside the window", r.stdout)
            self.assertIn("Tue 13 Oct 13:00", r.stdout)
            self.assertIn("Wed 14 Oct 17:00", r.stdout)
            self.assertIsNone(self.blocks()[obl]["start"])
        self.ok("plan", "place", obl, "--start", "2026-10-14T11:00+01:00", "--min", 20)  # 66 h
        b = self.blocks()[obl]
        self.assertEqual(b["start"], "2026-10-14T11:00+01:00")
        self.assertEqual(b["end"], "2026-10-14T11:20+01:00")
        self.assertEqual(b["window"]["to"], "2026-10-14T17:00+01:00")
        rc, data = self.check()
        self.assertEqual(rc, 0, data)
        r = self.cli("plan", "place", obl, "--start", "2026-10-14T12:00+01:00", "--min", 20)
        self.assertEqual(r.returncode, 1)
        self.assertIn("plan move", r.stdout)

    def test_add_obligation_without_start_uses_the_pair(self):
        teach = self.add("teach", "2026-10-13T14:00+01:00", 60)
        r = self.ok("plan", "add", SID, "--kind", "cold", "--content", "cold:T01", "--pair", teach)
        obl = r.stdout.split()[0]
        b = self.blocks()[obl]
        self.assertIsNone(b["start"])
        self.assertEqual(b["window"]["from"], "2026-10-15T11:00+01:00")  # teach end + 44 h
        self.assertEqual(b["window"]["to"], "2026-10-16T14:00+01:00")    # teach start + 72 h
        self.assertEqual(b["window"]["basis"], "pair")
        r = self.cli("plan", "add", SID, "--kind", "teach", "--content", "new skill")
        self.assertEqual(r.returncode, 2)

    def test_recheck_within_24_hours_of_exposure_fails(self):
        self.expose("T02", "2026-10-12T08:00+01:00")
        cold = self.add("cold", "2026-10-13T07:00+01:00", 20, "--content", "cold:T02")
        rc, data = self.check()
        self.assertEqual(rc, 1)
        self.assertTrue(self.findings(data, "FAIL", "cold_24h", cold), data)

    def test_recheck_within_24_hours_of_a_planned_teach_fails(self):
        teach = self.add("teach", "2026-10-14T18:00+01:00", 60, "--content", "new skill teach:T03")
        cold = self.add("cold", "2026-10-15T08:00+01:00", 20, "--content", "cold:T03")
        rc, data = self.check()
        self.assertEqual(rc, 1)
        hits = self.findings(data, "FAIL", "cold_24h", cold)
        self.assertEqual(len(hits), 1, data)
        self.assertEqual(hits[0]["other"], teach)

    def test_on_demand_fix_names_the_window(self):
        self.set_root("time.schedule", "on_demand")
        obl = self.write_block(id="B-20261010-ielts-1", window={"from": "2026-10-10T09:00+01:00",
                                                                 "to": "2026-10-13T05:00+01:00"})
        rc, data = self.check()
        self.assertEqual(rc, 1)
        hits = self.findings(data, "FAIL", "obligation_due", obl)
        self.assertTrue(hits[0]["fix"].startswith("tell the learner the window: between Mon 12 Oct 09:15"), hits)

    def test_obligation_closing_within_24h_unplaced_fails(self):
        soon = self.write_block(id="B-20261010-ielts-1", window={"from": "2026-10-10T09:00+01:00",
                                                                  "to": "2026-10-13T05:00+01:00"})
        later = self.write_block(id="B-20261011-ielts-1", content="cold:T02",
                                 window={"from": "2026-10-11T09:00+01:00", "to": "2026-10-13T15:00+01:00"})
        rc, data = self.check()
        self.assertEqual(rc, 1)
        hits = self.findings(data, "FAIL", "obligation_due")
        self.assertEqual([h["block"] for h in hits], [soon])
        self.assertIn("plan place %s" % soon, hits[0]["fix"])
        self.assertEqual(self.findings(data, block=later), [])
        self.assertEqual(data["checked"]["obligations"], 2)


# ==========================================================================
# Sleep, blocked time, overlaps, measurements, ceiling
# ==========================================================================

class HardRuleTests(PlanCase):
    def test_sleep_overlap_fails(self):
        bid = self.add("review", "2026-10-13T22:45+01:00", 60)
        rc, data = self.check()
        self.assertEqual(rc, 1)
        hits = self.findings(data, "FAIL", "sleep", bid)
        self.assertEqual(len(hits), 1, data)
        self.assertIn("2026-10-13T21:30+01:00", hits[0]["fix"])  # ends 30 min before bedtime

    def test_block_before_waking_fails(self):
        bid = self.add("review", "2026-10-13T06:30+01:00", 60)
        rc, data = self.check()
        self.assertEqual(rc, 1)
        hits = self.findings(data, "FAIL", "sleep", bid)
        self.assertEqual(len(hits), 1, data)
        self.assertIn("2026-10-13T07:00+01:00", hits[0]["fix"])

    def test_ending_within_30_min_of_bedtime_fails(self):
        bid = self.add("review", "2026-10-13T22:00+01:00", 40)
        rc, data = self.check()
        self.assertEqual(rc, 1)
        self.assertEqual(len(self.findings(data, "FAIL", "bedtime", bid)), 1, data)
        self.assertEqual(self.findings(data, "FAIL", "sleep", bid), [])

    def test_evening_block_clear_of_bedtime_passes(self):
        bid = self.add("review", "2026-10-13T21:00+01:00", 60)
        rc, data = self.check()
        self.assertEqual(rc, 0, data)
        self.assertEqual(self.findings(data, "FAIL", block=bid), [])
        self.assertTrue(self.findings(data, "WARN", "outside_window", bid))

    def test_blocked_time_fails(self):
        self.set_root("time.blocked", [
            {"days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "from": "09:00", "to": "18:00", "what": "work"},
            {"date": "2026-10-17", "what": "wedding"}])
        work = self.add("teach", "2026-10-13T10:00+01:00", 60)
        party = self.add("review", "2026-10-17T10:00+01:00", 60)
        free = self.add("review", "2026-10-13T18:00+01:00", 60)
        rc, data = self.check()
        self.assertEqual(rc, 1)
        self.assertEqual(len(self.findings(data, "FAIL", "blocked", work)), 1)
        self.assertEqual(len(self.findings(data, "FAIL", "blocked", party)), 1)
        self.assertEqual(self.findings(data, "FAIL", block=free), [])

    def test_overlapping_blocks_fail(self):
        a = self.add("teach", "2026-10-13T07:00+01:00", 60)
        b = self.add("review", "2026-10-13T07:30+01:00", 30)
        c = self.add("review", "2026-10-13T08:00+01:00", 15)  # touches both, overlaps neither
        rc, data = self.check()
        self.assertEqual(rc, 1)
        hits = self.findings(data, "FAIL", "overlap")
        self.assertEqual([(h["block"], h["other"]) for h in hits], [(b, a)])
        self.assertEqual(self.findings(data, "FAIL", block=c), [])

    def test_measurement_two_hours_after_another_fails(self):
        mock = self.add("mock", "2026-10-17T10:00+01:00", 60, "--measurement")
        diag = self.add("diagnostic", "2026-10-17T13:00+01:00", 60)
        self.assertTrue(self.blocks()[diag]["measurement"])
        rc, data = self.check()
        self.assertEqual(rc, 1)
        hits = self.findings(data, "FAIL", "measurement_gap", diag)
        self.assertEqual(len(hits), 1, data)
        self.assertEqual(hits[0]["other"], mock)
        self.ok("plan", "move", diag, "--start", "2026-10-17T14:00+01:00")
        rc, data = self.check()
        self.assertEqual(self.findings(data, "FAIL", "measurement_gap"), [])

    def test_weekly_ceiling_exceeded_fails(self):
        ids = [self.add("review", "2026-10-%02dT17:00+01:00" % d, 90) for d in (13, 14, 15, 16)]
        rc, data = self.check()
        self.assertEqual(rc, 1)
        hits = self.findings(data, "FAIL", "ceiling")
        self.assertEqual(len(hits), 1, data)
        self.assertEqual(hits[0]["week"], "2026-W42")
        self.assertIn("360", hits[0]["message"])
        self.assertIn("plan cancel", hits[0]["fix"])
        self.ok("plan", "cancel", ids[0], "--reason", "over the ceiling")
        rc, data = self.check()
        self.assertEqual(self.findings(data, "FAIL", "ceiling"), [])
        self.assertEqual(rc, 0, data)

    def test_soft_warnings_rest_day_and_confusable(self):
        self.set_root("time.rest_day", "Sun")
        sunday = self.add("review", "2026-10-18T10:00+01:00", 30)
        self.add("teach", "2026-10-13T07:00+01:00", 30, "--content", "teach:T01")
        paraphrase = self.add("teach", "2026-10-13T07:30+01:00", 30, "--content", "teach:T04")
        rc, data = self.check()
        self.assertEqual(rc, 0, data)
        self.assertTrue(self.findings(data, "WARN", "rest_day", sunday))
        self.assertTrue(self.findings(data, "WARN", "confusable", paraphrase))
        for f in data["findings"]:
            self.assertTrue(f["fix"], f)

    def test_text_output_and_exit_code(self):
        self.add("review", "2026-10-13T22:45+01:00", 60)
        r = self.cli("plan", "check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL sleep:", r.stdout)
        self.assertIn("  Fix: plan move", r.stdout)
        self.assertIn("plan check: FAIL", r.stdout)


# ==========================================================================
# Moving, cancelling, done and missed
# ==========================================================================

class MoveTests(PlanCase):
    def test_moving_a_teach_moves_its_cold(self):
        teach = self.add("teach", "2026-10-13T14:00+01:00", 60)
        cold = self.add("cold", "2026-10-16T08:00+01:00", 20, "--content", "cold:T01", "--pair", teach)
        r = self.ok("plan", "move", teach, "--start", "2026-10-14T14:00+01:00")
        self.assertIn(cold, r.stdout)
        b = self.blocks()
        self.assertEqual(b[teach]["start"], "2026-10-14T14:00+01:00")
        self.assertEqual(b[teach]["end"], "2026-10-14T15:00+01:00")
        self.assertEqual(b[teach]["moved_from"], "2026-10-13T14:00+01:00")
        self.assertEqual(b[cold]["start"], "2026-10-17T08:00+01:00")
        self.assertEqual(b[cold]["end"], "2026-10-17T08:20+01:00")
        self.assertEqual(b[cold]["moved_from"], "2026-10-16T08:00+01:00")
        self.assertEqual(b[cold]["moves"], 1)
        rc, data = self.check()
        self.assertEqual(self.findings(data, "FAIL", "cold_window"), [])

    def test_moving_a_teach_shifts_its_unplaced_recheck_window(self):
        teach = self.add("teach", "2026-10-13T14:00+01:00", 60)
        obl = self.ok("plan", "add", SID, "--kind", "cold", "--content", "cold:T01",
                      "--pair", teach).stdout.split()[0]
        self.ok("plan", "move", teach, "--start", "2026-10-13T16:00+01:00", "--min", 45)
        w = self.blocks()[obl]["window"]
        self.assertEqual(w["from"], "2026-10-15T12:45+01:00")  # new end + 44 h
        self.assertEqual(w["to"], "2026-10-16T16:00+01:00")    # new start + 72 h

    def test_move_refused_when_the_recheck_would_leave_a_fixed_window(self):
        teach = self.write_block(id="B-20261012-ielts-1", kind="teach", content="new skill",
                                 start="2026-10-12T07:00+01:00", end="2026-10-12T08:00+01:00", protected=True)
        self.expose("T01", "2026-10-12T08:00+01:00")
        cold = self.write_block(id="B-20261014-ielts-1", pair=teach, start="2026-10-14T07:00+01:00",
                                end="2026-10-14T07:20+01:00",
                                window={"from": "2026-10-14T04:00+01:00", "to": "2026-10-15T08:00+01:00"})
        before = self.blocks()
        r = self.cli("plan", "move", teach, "--start", "2026-10-14T07:00+01:00")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(cold, r.stdout)
        self.assertEqual(self.blocks(), before)

    def test_direct_recheck_move_outside_window_refused(self):
        teach = self.add("teach", "2026-10-13T14:00+01:00", 60)
        cold = self.add("cold", "2026-10-16T08:00+01:00", 20, "--content", "cold:T01", "--pair", teach)
        r = self.cli("plan", "move", cold, "--start", "2026-10-17T08:00+01:00")
        self.assertEqual(r.returncode, 1)
        self.assertIn("window", r.stdout)
        self.assertEqual(self.blocks()[cold]["start"], "2026-10-16T08:00+01:00")

    def test_miss_then_rebook_keeps_the_id(self):
        bid = self.write_block(id="B-20261012-ielts-1", kind="teach", content="new skill",
                               start="2026-10-12T07:00+01:00", end="2026-10-12T08:00+01:00")
        self.ok("plan", "miss", bid, "--reason", "no reason given")
        b = self.blocks()[bid]
        self.assertEqual((b["status"], b["miss_reason"]), ("missed", "no reason given"))
        self.ok("plan", "move", bid, "--start", "2026-10-13T07:00+01:00")
        b = self.blocks()[bid]
        self.assertEqual(b["status"], "planned")
        self.assertEqual(b["moved_from"], "2026-10-12T07:00+01:00")
        self.assertEqual(b["start"], "2026-10-13T07:00+01:00")

    def test_miss_refused_before_the_block_starts(self):
        bid = self.add("review", "2026-10-13T07:00+01:00", 30)
        r = self.cli("plan", "miss", bid, "--reason", "busy")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.blocks()[bid]["status"], "planned")

    def test_cancel_and_done(self):
        a = self.add("review", "2026-10-13T07:00+01:00", 30)
        b = self.add("review", "2026-10-14T07:00+01:00", 30)
        self.ok("plan", "cancel", a, "--reason", "learner said no")
        self.ok("plan", "done", b)
        rows = self.blocks()
        self.assertEqual(rows[a]["status"], "cancelled")
        self.assertEqual(rows[a]["cancel_reason"], "learner said no")
        self.assertEqual(rows[b]["status"], "done")
        self.assertEqual(self.cli("plan", "done", a).returncode, 1)
        self.assertEqual(self.cli("plan", "move", a, "--start", "2026-10-15T07:00+01:00").returncode, 1)
        self.assertEqual(self.cli("plan", "cancel", "B-20990101-ielts-1", "--reason", "x").returncode, 2)

    def test_add_validates_input(self):
        bad = [
            ["plan", "add", SID, "--kind", "teach", "--start", "2026-10-13", "--min", 60],
            ["plan", "add", SID, "--kind", "teach", "--start", "2026-10-13T07:00+01:00", "--min", 0],
            ["plan", "add", SID, "--kind", "teach", "--start", "2026-10-13T07:00+01:00"],
            ["plan", "add", "nosuch", "--kind", "teach", "--start", "2026-10-13T07:00+01:00", "--min", 60],
            ["plan", "add", SID, "--kind", "cold", "--start", "2026-10-13T07:00+01:00", "--min", 20,
             "--pair", "B-20990101-ielts-9"],
        ]
        for args in bad:
            r = self.cli(*args)
            self.assertEqual(r.returncode, 2, (args, r.stdout, r.stderr))
        self.assertEqual(self.blocks(), {})


# ==========================================================================
# list and week
# ==========================================================================

class ListWeekTests(PlanCase):
    def test_list_shows_missed_without_writing(self):
        gone = self.write_block(id="B-20261012-ielts-1", kind="teach", content="new skill",
                                start="2026-10-12T07:00+01:00", end="2026-10-12T08:00+01:00")
        held = self.write_block(id="B-20261012-ielts-2", kind="review", content="review",
                                start="2026-10-12T08:00+01:00", end="2026-10-12T08:30+01:00")
        fio.append_jsonl(self.ws / SID / "data" / "sessions.jsonl", {
            "v": 1, "id": "S-ielts-0001", "block": None, "kind": "review",
            "planned": {"start": "2026-10-12T08:00+01:00", "min": 30},
            "actual": {"start": "2026-10-12T08:02+01:00", "end": "2026-10-12T08:31+01:00", "elapsed_min": 29}})
        before = (self.ws / "plan" / "blocks.jsonl").read_bytes()
        r = self.ok("plan", "list", "--json")
        rows = dict((b["id"], b) for b in json.loads(r.stdout))
        self.assertEqual(rows[gone]["status"], "missed?")
        self.assertEqual(rows[gone]["stored_status"], "planned")
        self.assertEqual(rows[held]["status"], "planned")
        self.assertEqual((self.ws / "plan" / "blocks.jsonl").read_bytes(), before)
        text = self.ok("plan", "list").stdout
        self.assertIn("missed?", text)
        r = self.ok("plan", "list", "--from", "2026-10-13", "--json")
        self.assertEqual(json.loads(r.stdout), [])

    def test_list_filters_by_date_and_subject(self):
        a = self.add("review", "2026-10-13T07:00+01:00", 30)
        b = self.add("review", "2026-10-20T07:00+01:00", 30)
        rows = json.loads(self.ok("plan", "list", "--subject", SID, "--from", "2026-10-19", "--to",
                                  "2026-10-25", "--json").stdout)
        self.assertEqual([r["id"] for r in rows], [b])
        self.assertEqual(self.cli("plan", "list", "--subject", "nosuch").returncode, 2)
        self.assertNotEqual(a, b)

    def test_fallback_week_table(self):
        # The table plan week writes itself when the brief module is not installed.
        from lib import cmd_plan
        from lib import ws as wsmod
        self.add("teach", "2026-10-13T07:00+01:00", 60)
        self.write_block(id="B-20261014-ielts-1", window={"from": "2026-10-14T09:00+01:00",
                                                          "to": "2026-10-15T09:00+01:00"})
        text = cmd_plan.week_text(cmd_plan.Ctx(wsmod.Workspace(self.ws)))
        self.assertTrue(text.startswith("<!-- generated by indelible; do not edit -->"))
        self.assertIn("# Week 2026-W42 (Mon 12 Oct – Sun 18 Oct)", text)
        self.assertIn("| Tue 13 Oct | 07:00–08:00 | IELTS Academic | new skill | 60 | planned |", text)
        self.assertIn("2-day recheck, between Wed 14 Oct 09:00 and Thu 15 Oct 09:00", text)
        self.assertNotIn("B-2026", text)  # plain vocabulary: no ids
        self.assertIn("Minutes planned: 60 of a 336 ceiling", text)

    def test_week_writes_the_view(self):
        self.add("teach", "2026-10-13T07:00+01:00", 60)
        r = self.ok("plan", "week")
        view = self.ws / "views" / "week.md"
        self.assertTrue(view.exists())
        text = view.read_text(encoding="utf-8")
        self.assertIn("2026-W42", text)
        self.assertIn("IELTS Academic", text)
        self.assertIn("2026-W42", r.stdout)


# ==========================================================================
# diff and cal ack
# ==========================================================================

class DiffAckTests(PlanCase):
    TOPIC_WORDS = ("Matching headings", "T01", "Paraphrase", "T04")

    def diff(self):
        return json.loads(self.ok("plan", "diff", "--json").stdout)

    def ack(self, rows):
        path = self.ws / ".indelible" / "cal-results.json"
        path.write_text(json.dumps(rows), encoding="utf-8")
        return self.cli("cal", "ack", "--from", path)

    def assert_card(self, row):
        notes = row["notes"]
        lines = notes.split("\n")
        self.assertEqual(lines[0], "[ind:%s]" % row["block"])
        self.assertLessEqual(len(notes), 600)
        steps = [l for l in lines if re.match(r"^\d\. ", l)]
        self.assertTrue(3 <= len(steps) <= 6, notes)
        self.assertTrue(lines[-1].startswith("Start: open Claude in "), notes)
        self.assertTrue(lines[-1].endswith('say "start ielts"'), notes)
        self.assertTrue(any(l.startswith("Short on time") for l in lines), notes)

    def test_create_move_cancel_rows_and_ack(self):
        teach = self.add("teach", "2026-10-13T07:00+01:00", 60, "--content", "new skill")
        cold = self.add("cold", "2026-10-15T07:00+01:00", 20, "--content", "cold:T01", "--pair", teach)
        rows = self.diff()
        self.assertEqual([(r["op"], r["block"]) for r in rows], [("create", teach), ("create", cold)])
        by = dict((r["block"], r) for r in rows)
        self.assertEqual(by[teach]["title"], "IELTS Academic · new skill · 60m")
        self.assertEqual(by[cold]["title"], "IELTS Academic · 2-day recheck (mixed) · 20m")
        self.assertEqual(by[cold]["start"], "2026-10-15T07:00+01:00")
        self.assertEqual(by[cold]["end"], "2026-10-15T07:20+01:00")
        for r in rows:
            self.assertEqual(set(["op", "block", "subject", "title", "start", "end", "notes"]) - set(r), set())
            self.assert_card(r)
            body = "\n".join(r["notes"].split("\n")[:-1])  # the last line holds the workspace path
            for word in self.TOPIC_WORDS:
                self.assertNotIn(word, r["title"])
                self.assertNotIn(word, body)

        r = self.ack([{"block": x["block"], "provider": "google", "id": "evt-%d" % i, "etag": None,
                       "start": x["start"]} for i, x in enumerate(rows)])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        b = self.blocks()
        self.assertEqual((b[teach]["status"], b[cold]["status"]), ("synced", "synced"))
        self.assertEqual(b[teach]["cal"]["id"], "evt-0")
        self.assertEqual(b[teach]["cal"]["start"], "2026-10-13T07:00+01:00")
        self.assertEqual(self.diff(), [])
        self.assertIn("Unchanged 2", self.ok("plan", "diff").stdout)

        self.ok("plan", "move", teach, "--start", "2026-10-13T07:30+01:00", "--min", 45)
        rows = self.diff()
        self.assertEqual([(r["op"], r["block"]) for r in rows], [("move", teach), ("move", cold)])
        self.assertEqual(rows[0]["was"], "2026-10-13T07:00+01:00")
        self.assertEqual(rows[0]["title"], "IELTS Academic · new skill · 45m")
        self.assertEqual(rows[1]["start"], "2026-10-15T07:30+01:00")
        self.assertEqual(self.blocks()[teach]["status"], "synced")

        self.ok("plan", "cancel", teach, "--reason", "learner said no")
        rows = self.diff()
        self.assertEqual([(r["op"], r["block"]) for r in rows], [("cancel", teach), ("move", cold)])
        text = self.ok("plan", "diff").stdout
        self.assertIn("Cancel 1", text)
        self.assertIn("not deleted", text)

        r = self.ack([{"block": x["block"], "provider": "google", "id": "evt-%d" % i, "etag": "e2",
                       "start": x["start"]} for i, x in enumerate(rows)])
        self.assertEqual(r.returncode, 0, r.stdout)
        b = self.blocks()
        self.assertEqual(b[teach]["status"], "cancelled")
        self.assertTrue(b[teach]["cal"]["cancelled"])
        self.assertEqual(b[cold]["status"], "synced")
        self.assertEqual(self.diff(), [])

    def test_cold_title_never_names_the_topic(self):
        teach = self.add("teach", "2026-10-13T07:00+01:00", 60, "--content", "Paraphrase, first pass")
        self.add("cold", "2026-10-15T07:00+01:00", 20, "--content", "cold:T04 Paraphrase", "--pair", teach)
        self.add("mixed", "2026-10-15T07:20+01:00", 40, "--content", "2-day recheck on Paraphrase, then drills")
        for r in self.diff():
            self.assert_card(r)
            body = "\n".join(r["notes"].split("\n")[:-1])  # the last line holds the workspace path
            for word in self.TOPIC_WORDS:
                self.assertNotIn(word, r["title"])
                self.assertNotIn(word, body)
        cold_rows = [r for r in self.diff() if "recheck" in r["title"]]
        self.assertEqual(len(cold_rows), 1)
        self.assertIn("2-day recheck (mixed)", cold_rows[0]["title"])
        mixed = [r for r in self.diff() if "mixed practice" in r["title"]][0]
        self.assertIn("Sit the 2-day recheck first.", mixed["notes"])

    def test_past_blocks_are_not_offered(self):
        self.write_block(id="B-20261012-ielts-1", kind="teach", content="new skill",
                         start="2026-10-12T07:00+01:00", end="2026-10-12T08:00+01:00")
        self.assertEqual(self.diff(), [])

    def test_ack_rejects_unknown_blocks_and_bad_rows(self):
        bid = self.add("review", "2026-10-13T07:00+01:00", 30)
        r = self.ack([{"block": bid, "provider": "ics", "id": bid + "@indelible", "etag": None},
                      {"block": "B-20990101-ielts-1", "provider": "ics", "id": "x", "etag": None}])
        self.assertEqual(r.returncode, 1)
        self.assertIn("B-20990101-ielts-1", r.stdout)
        self.assertEqual(self.blocks()[bid]["status"], "synced")
        self.assertEqual(self.blocks()[bid]["cal"]["start"], "2026-10-13T07:00+01:00")
        r = self.ack([{"block": bid, "provider": "fax", "id": "x"}])
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
