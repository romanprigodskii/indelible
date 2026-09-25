"""stats, review week and compact on a small synthetic history (persona A, subject ``ielts``).

Week 2026-W42 runs Mon 12 Oct to Sun 18 Oct 2026. The history, written
straight to the data files:

  12 Oct  ielts-cold-01   cold    T04 at 48 h, taught by sheet: 3 of 4 right       -> T04 level 3
  13 Oct  ielts-para-02   drills  T04 x10 (7 right, 2 careless wrong, 1 half);
                                  T01 x2 (1 right, 1 careless wrong; T01 below level 3)
  14 Oct  ielts-cold-02   cold    T01 at 50 h, taught externally (from topics.json): 1 of 2 right
                                  (the miss named on the Least-sure line: it still counts, so T01
                                  does not reach 3); T02 at 100 h (outside both retention bands)
  17 Oct  ielts-cold-03   cold    T04 at 170 h: 1 of 1 right (the 7-day band)
"""

import json
import unittest
from datetime import date

try:
    from test_grade import GradeBase, make_item, read_rows, write_sheet
except ImportError:  # run as part of the tests package
    from tests.test_grade import GradeBase, make_item, read_rows, write_sheet

from lib import CheckFailed
from lib import cmd_stats
from lib import io as fio

SUNDAY = "2026-10-18T19:00+01:00"


def attempt(sheet, n, topic, verdict, at, instrument, interval_h=None, check="filled", least_sure=False,
            mode=None, taught_by=None, layer="verbal"):
    row = {"v": 1, "sheet": sheet, "item": n, "ask": "%da" % n, "topic": topic, "layer": layer,
           "instrument": instrument, "cold": instrument == "cold", "interval_h": interval_h,
           "verdict": verdict, "score": {"right": 1, "half": 0.5}.get(verdict, 0), "check": check,
           "least_sure": least_sure, "mode": mode, "account": None, "error_id": None, "at": at,
           "prov": "measured" if instrument != "practice" else "practice"}
    if taught_by:
        row["taught_by"] = taught_by
    return row


def history():
    rows = []
    mon, tue = "2026-10-12T08:00+01:00", "2026-10-13T08:00+01:00"
    wed, weekend = "2026-10-14T08:00+01:00", "2026-10-17T10:00+01:00"
    for n, v in enumerate(["right", "right", "right", "wrong"], start=1):
        rows.append(attempt("ielts-cold-01", n, "T04", v, mon, "cold", 48.0, taught_by="sheet",
                            mode="D" if v == "wrong" else None))
    drills = [("T04", "right", "filled", False, None)] * 6 + [
        ("T04", "right", "caught", False, None),
        ("T04", "wrong", "filled", False, "C"),
        ("T04", "wrong", "missing", True, "C"),
        ("T04", "half", "filled", False, "F"),
        ("T01", "right", "filled", False, None),
        ("T01", "wrong", "missing", False, "C"),
    ]
    for n, (topic, v, check, ls, mode) in enumerate(drills, start=1):
        rows.append(attempt("ielts-para-02-drills", n, topic, v, tue, "practice", check=check, least_sure=ls,
                            mode=mode))
    rows.append(attempt("ielts-cold-02", 1, "T01", "right", wed, "cold", 50.0))
    rows.append(attempt("ielts-cold-02", 2, "T01", "wrong", wed, "cold", 50.0, least_sure=True, mode="E"))
    rows.append(attempt("ielts-cold-02", 3, "T02", "right", wed, "cold", 100.0, taught_by="sheet"))
    rows.append(attempt("ielts-cold-03", 1, "T04", "right", weekend, "cold", 170.0, taught_by="sheet"))
    return rows


class StatsBase(GradeBase):
    NOW = SUNDAY

    def setUp(self):
        GradeBase.setUp(self)
        fio.write_jsonl(self.sdir / "data" / "attempts.jsonl", history())
        fio.write_json(self.sdir / "data" / "topics.json", {
            "T01": {"level": 0, "level_basis": "no evidence yet", "taught_at": "2026-10-12T06:00+01:00",
                    "taught_by": "external", "last_cold": None, "cold_passes": [], "explanation_on_file": False,
                    "note": ""}})
        key = write_sheet(self.ws, self.sid, "ielts-cold-04", "cold", [make_item(1, "T04", ["1a"])])
        self.remember_key(key)

    def add_week_records(self):
        fio.write_jsonl(self.sdir / "data" / "sessions.jsonl", [
            {"v": 1, "id": "S-ielts-0001", "block": "B-20261012-ielts-1", "kind": "teach",
             "planned": {"start": "2026-10-12T07:00+01:00", "min": 60},
             "actual": {"start": "2026-10-12T07:02+01:00", "end": "2026-10-12T08:04+01:00", "elapsed_min": 62},
             "sheets": [], "asks": {}, "overrun_min": 2, "note": "",
             "closed": {"at": "2026-10-12T08:06+01:00", "status": "same-day"}},
            {"v": 1, "id": "S-ielts-0002", "block": "B-20261013-ielts-1", "kind": "teach",
             "planned": {"start": "2026-10-13T07:00+01:00", "min": 60},
             "actual": {"start": "2026-10-13T07:00+01:00", "end": "2026-10-13T07:55+01:00", "elapsed_min": 55},
             "sheets": [], "asks": {}, "overrun_min": 0, "note": "",
             "closed": {"at": "2026-10-14T07:00+01:00", "status": "late"}},
        ])

        def block(bid, day, hour, status="planned", moved_from=None, kind="teach"):
            return {"v": 1, "id": bid, "subject": "ielts", "kind": kind,
                    "start": "%sT%02d:00+01:00" % (day, hour), "end": "%sT%02d:00+01:00" % (day, hour + 1),
                    "window": None, "protected": True, "measurement": False, "soft": False, "pair": None,
                    "content": "", "status": status, "cal": None, "moved_from": moved_from, "miss_reason": None}

        fio.write_jsonl(self.ws / "plan" / "blocks.jsonl", [
            block("B-20261012-ielts-1", "2026-10-12", 7, "done"),
            block("B-20261013-ielts-1", "2026-10-13", 7, "done"),
            block("B-20261015-ielts-1", "2026-10-15", 7, "planned"),
            block("B-20261017-ielts-1", "2026-10-17", 10, "done", moved_from="2026-10-16T07:00+01:00", kind="cold"),
            block("B-20261019-ielts-1", "2026-10-19", 7, "planned"),
        ])
        fio.write_jsonl(self.sdir / "data" / "errors.jsonl", [
            {"v": 1, "id": "E-ielts-0001", "opened": "2026-10-12", "topic": "T04", "kind": "belief", "mode": "D",
             "belief": "reads 'unless' as 'if'", "status": "spacing", "repair_at": "2026-10-13T19:00+01:00",
             "rung": 0, "next_due": "2026-10-19", "passes": [], "fails": []},
            {"v": 1, "id": "E-ielts-0002", "opened": "2026-10-13", "topic": "T01", "kind": "slip", "mode": "C",
             "status": "spacing", "rung": 0, "next_due": "2026-10-14", "passes": [], "fails": []},
            {"v": 1, "id": "E-ielts-0003", "opened": "2026-09-20", "topic": "T02", "kind": "slip", "mode": "C",
             "status": "retired", "rung": 3, "next_due": None,
             "passes": ["2026-09-21", "2026-09-24", "2026-10-01", "2026-10-15"], "fails": []},
        ])
        for row in [
            {"v": 1, "id": "L-0001", "kind": "owed", "subject": "ielts", "by": "learner",
             "what": "Register for the 12 Dec sitting", "due": "2026-10-16T20:00+01:00", "at": "2026-10-11T18:00+01:00"},
            {"v": 1, "id": "L-0002", "kind": "owed", "subject": "ielts", "by": "claude",
             "what": "Build Saturday's sheets", "due": "2026-10-25T20:00+01:00", "at": "2026-10-11T18:00+01:00"},
            {"v": 1, "id": "L-0003", "kind": "decision", "subject": "ielts", "by": "learner",
             "summary": "Saturday timed section moves to 09:00", "why": "clearest head early",
             "safeguard": {"check_on": "2026-10-17", "rule": "timed accuracy < 0.70", "action": "revert"},
             "at": "2026-10-11T18:00+01:00"},
            {"v": 1, "id": "L-0004", "kind": "defect", "subject": "ielts", "category": "undefined_term",
             "what": "'gist' used undefined", "fix_type": "rule", "fix": "define it", "at": "2026-10-12T08:00+01:00"},
            {"v": 1, "id": "L-0005", "kind": "defect", "subject": "ielts", "category": "undefined_term",
             "what": "'scan' used undefined", "fix_type": "lint", "fix": "sense_list += scan",
             "at": "2026-10-14T08:00+01:00"},
        ]:
            fio.append_jsonl(self.ws / "ledger.jsonl", row)


class StatsTests(StatsBase):
    def test_metrics_on_a_small_history(self):
        self.add_week_records()
        st = json.loads(self.cli(["stats", self.sid, "--json"]).stdout)
        self.assertEqual(st["asks"], 20)
        prac, cold = st["instruments"]["practice"], st["instruments"]["cold"]
        self.assertEqual(prac["label"], "practice")
        self.assertEqual(cold["label"], "measured")
        # Careless per 10: only the T04 drills count (T04 reached level 3 on Monday; T01 was below 3).
        self.assertEqual((prac["careless_per_10"]["num"], prac["careless_per_10"]["n"]), (2, 10))
        self.assertAlmostEqual(prac["careless_per_10"]["value"], 2.0)
        self.assertEqual((cold["careless_per_10"]["num"], cold["careless_per_10"]["n"]), (0, 1))
        # Unnamed-wrong: wrong answers not on the Least-sure line / all wrong answers.
        self.assertEqual((prac["unnamed_wrong"]["num"], prac["unnamed_wrong"]["n"]), (2, 3))
        self.assertEqual((cold["unnamed_wrong"]["num"], cold["unnamed_wrong"]["n"]), (1, 2))
        self.assertEqual((prac["least_sure_hit"]["num"], prac["least_sure_hit"]["n"]), (1, 1))
        # Check coverage: filled or caught / asks with a check line.
        self.assertEqual((prac["check_coverage"]["num"], prac["check_coverage"]["n"]), (10, 12))
        self.assertEqual(prac["check_catches"], 1)
        self.assertEqual((cold["accuracy"]["num"], cold["accuracy"]["n"]), (6, 8))
        self.assertEqual((prac["accuracy"]["num"], prac["accuracy"]["n"]), (8.5, 12))
        # Retention at 48 h (36-72 h), split by how the topic was taught and by topic.
        r48 = st["retention_48h"]
        self.assertEqual((r48["overall"]["num"], r48["overall"]["n"]), (4, 6))
        self.assertEqual(dict((k, (v["num"], v["n"])) for k, v in r48["by_taught_by"].items()),
                         {"sheet": (3, 4), "external": (1, 2)})
        self.assertEqual(dict((k, (v["num"], v["n"])) for k, v in r48["by_topic"].items()),
                         {"T01": (1, 2), "T04": (3, 4)})
        self.assertEqual((st["retention_7d"]["overall"]["num"], st["retention_7d"]["overall"]["n"]), (1, 1))
        self.assertEqual((st["execution"]["blocks"]["num"], st["execution"]["blocks"]["n"]), (3, 4))
        self.assertEqual(st["execution"]["overruns"], 1)

    def test_text_output_labels_every_instrument(self):
        r = self.cli(["stats", self.sid])
        out = r.stdout
        self.assertIn("cold [measured n=8]: accuracy 75% (6/8)", out)
        self.assertIn("practice [practice n=12]: accuracy 71% (8.5/12)", out)
        self.assertIn("careless per 10: 2.0 (2 in 10 questions on level-3+ topics)", out)
        self.assertIn("retention 48 h [measured]: 67% (4/6) · by teaching: external 50% (1/2), sheet 75% (3/4)", out)
        self.assertIn("retention 7 d [measured]: 100% (1/1)", out)
        self.assert_no_secrets()

    def test_since_until_window(self):
        st = json.loads(self.cli(["stats", self.sid, "--json", "--since", "2026-10-14", "--until", "2026-10-14"]).stdout)
        self.assertEqual(st["asks"], 3)
        self.assertEqual(list(st["instruments"]), ["cold"])


class ReviewWeekTests(StatsBase):
    def test_review_prints_at_most_15_lines_and_writes_the_file(self):
        self.add_week_records()
        r = self.cli(["review", "week", "all"])
        lines = r.stdout.rstrip("\n").split("\n")
        self.assertLessEqual(len(lines), 15)
        out = r.stdout
        self.assertIn("Week 2026-W42 (Mon 12 Oct to Sun 18 Oct) · written to reviews/2026-W42.md", out)
        self.assertIn("IELTS Academic: 2 sessions, 117/120 min · overruns 1 (+2 min) · closed same day 1/2", out)
        self.assertIn("blocks 3/4 done, 1 moved, 1 missed", out)
        self.assertIn("2-day recheck: 67% (4/6) [measured]", out)
        self.assertIn("7-day: 100% (1/1) [measured]", out)
        self.assertIn("mistakes 2 new, 1 fixed, 1 retired, 1 overdue", out)
        self.assertIn("levels T04 0→3", out)
        self.assertNotIn("T01 0→3", out)   # 1 of 2 on the recheck: the named miss is not hidden
        self.assertIn("practice [practice]: careless/10 2.0 · unnamed-wrong 67% (2/3) · checks 83% (10/12), 1 caught", out)
        self.assertIn('To do, overdue: 1 · "Register for the 12 Dec sitting"', out)
        self.assertIn("Issued, not taken yet: ielts-cold-04", out)
        self.assertIn("undefined_term x2 (latest fix: lint)", out)
        self.assertIn("Safeguards past their check date", out)
        # Plain vocabulary (the default): no ledger ids for the learner.
        self.assertNotIn("L-000", out)

        path = self.ws / "reviews" / "2026-W42.md"
        self.assertTrue(path.exists())
        text = path.read_text(encoding="utf-8")
        self.assertLessEqual(len(text.rstrip("\n").split("\n")), 60)
        self.assertIn("# Weekly review 2026-W42", text)
        self.assertIn("- 2-day recheck (36-72 h): 67% (4/6) [measured]", text)
        self.assertIn("- practice [practice n=12]", text)
        self.assertIn("careless per 10 2.0 (2 in 10 questions on level-3+ topics)", text)
        self.assertNotIn("L-000", text)
        self.assert_no_secrets()

    def test_many_subjects_still_fit_in_15_lines(self):
        self.add_week_records()
        cfg = fio.read_json(self.ws / "indelible.json")
        for sid, title in (("spanish", "Spanish for a trip"), ("stats", "Statistics final"), ("rust", "Rust")):
            cfg["subjects"].append({"id": sid, "dir": sid, "state": "live", "priority": 2,
                                    "target_weekly_min": 60, "min_weekly_min": None})
            fio.write_json(self.ws / sid / "subject.json",
                           {"v": 1, "id": sid, "title": title, "profile": "course", "topics": []})
        fio.write_json(self.ws / "indelible.json", cfg)
        r = self.cli(["review", "week", "--week", "2026-W42"])
        lines = r.stdout.rstrip("\n").split("\n")
        self.assertLessEqual(len(lines), 15)
        for title in ("IELTS Academic:", "Spanish for a trip:", "Statistics final:", "Rust:"):
            self.assertIn(title, r.stdout)
        text = (self.ws / "reviews" / "2026-W42.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(text.rstrip("\n").split("\n")), 60)

    def test_default_week_and_explicit_week(self):
        # On Sunday the default is the current week; on a Wednesday it is the week just ended.
        self.cli(["review", "week", self.sid])
        self.assertTrue((self.ws / "reviews" / "2026-W42.md").exists())
        self.cli(["review", "week", self.sid], now="2026-10-21T09:00+01:00")
        self.cli(["review", "week", self.sid, "--week", "2026-W40"])
        self.assertTrue((self.ws / "reviews" / "2026-W40.md").exists())
        r = self.cli(["review", "week", "--week", "2026-X40"], expect=2)
        self.assertIn("2026-W42", r.stderr)


class CompactTests(StatsBase):
    NOW = "2026-10-14T09:00+01:00"

    def setUp(self):
        StatsBase.setUp(self)

        def retired(n, opened, last_pass):
            return {"v": 1, "id": "E-ielts-%04d" % n, "opened": opened, "topic": "T04", "kind": "slip",
                    "mode": "C", "status": "retired", "rung": 3, "next_due": None,
                    "passes": [opened, last_pass], "fails": []}

        self.arch = self.sdir / "archive"
        fio.write_jsonl(self.arch / "errors-2026-09.jsonl", [retired(1, "2026-08-01", "2026-09-02")])
        fio.write_jsonl(self.sdir / "data" / "errors.jsonl", [
            retired(2, "2026-09-01", "2026-09-28"),      # 16 days ago: moves to errors-2026-09
            retired(3, "2026-09-10", "2026-10-01"),      # 13 days ago: moves to errors-2026-10
            retired(4, "2026-09-12", "2026-10-07"),      # exactly 7 days: stays
            {"v": 1, "id": "E-ielts-0005", "opened": "2026-10-12", "topic": "T01", "kind": "slip", "mode": "C",
             "status": "spacing", "rung": 0, "next_due": "2026-10-13", "passes": [], "fails": []},
        ])
        sept = [attempt("ielts-old-01", n, "T04", "right", "2026-09-2%dT08:00+01:00" % n, "practice")
                for n in range(1, 4)]
        octo = [attempt("ielts-new-01", n, "T01", "right", "2026-10-1%dT08:00+01:00" % n, "practice")
                for n in range(1, 3)]
        fio.write_jsonl(self.sdir / "data" / "attempts.jsonl", sept + octo)
        fio.write_jsonl(self.arch / "attempts-2026-08.jsonl",
                        [attempt("ielts-older-01", 1, "T04", "right", "2026-08-20T08:00+01:00", "practice")])
        self.sept, self.octo = sept, octo

    def all_ids(self):
        ids = set(e["id"] for e in read_rows(self.sdir / "data" / "errors.jsonl"))
        for p in self.arch.glob("errors-*.jsonl"):
            ids |= set(e["id"] for e in read_rows(p))
        return ids

    def snapshot(self):
        files = {}
        for p in sorted(self.sdir.rglob("*.jsonl")):
            files[str(p)] = p.read_bytes()
        return files

    def test_dry_run_writes_nothing(self):
        before = self.snapshot()
        r = self.cli(["compact", self.sid, "--dry-run"])
        self.assertIn("would move 2 retired mistakes", r.stdout)
        self.assertIn("would move 3 graded questions to archive/attempts-2026-09.jsonl", r.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_compact_moves_retired_errors_and_old_attempts_with_parity(self):
        ids_before = self.all_ids()
        r = self.cli(["compact", self.sid])
        self.assertIn("moved 2 retired mistakes to archive/errors-2026-09.jsonl, archive/errors-2026-10.jsonl",
                      r.stdout)
        self.assertIn("ID parity OK (5 mistake ids)", r.stdout)
        self.assertEqual(self.all_ids(), ids_before)
        active = [e["id"] for e in read_rows(self.sdir / "data" / "errors.jsonl")]
        self.assertEqual(active, ["E-ielts-0004", "E-ielts-0005"])
        sept = read_rows(self.arch / "errors-2026-09.jsonl")
        self.assertEqual([e["id"] for e in sept], ["E-ielts-0001", "E-ielts-0002"])
        self.assertIn("retired 2026-09-28 after 2 passes", sept[1]["outcome"])
        self.assertEqual([e["id"] for e in read_rows(self.arch / "errors-2026-10.jsonl")], ["E-ielts-0003"])
        # Attempts: September rotated out, October stays; nothing lost.
        self.assertEqual(read_rows(self.sdir / "data" / "attempts.jsonl"), self.octo)
        self.assertEqual(read_rows(self.arch / "attempts-2026-09.jsonl"), self.sept)
        self.assertEqual(len(read_rows(self.arch / "attempts-2026-08.jsonl")), 1)
        # .bak copies of every rewritten file that existed.
        for p in (self.sdir / "data" / "errors.jsonl", self.sdir / "data" / "attempts.jsonl",
                  self.arch / "errors-2026-09.jsonl"):
            self.assertTrue(fio.bak_path(p).exists(), p)
        # Running again moves nothing; ids are never reused.
        r = self.cli(["compact", self.sid])
        self.assertIn("nothing to move", r.stdout)
        r = self.cli(["error", "add", self.sid, "--topic", "T04", "--kind", "slip", "--mode", "C",
                      "--belief", "drops a negative", "--account", "slip"])
        self.assertIn("E-ielts-0006 opened", r.stdout)
        # Levels still see the archived attempts (T04's only evidence is now in the archive).
        r = self.cli(["topic", "show", self.sid, "--json"])
        t04 = [t for t in json.loads(r.stdout) if t["id"] == "T04"][0]
        self.assertEqual(t04["level"], 2)

    def test_parity_guard_refuses(self):
        active = [
            {"v": 1, "id": "E-ielts-0002", "status": "retired", "passes": ["2026-09-01"], "topic": "T04"},
            {"v": 1, "id": "E-ielts-0003", "status": "retired", "passes": ["2026-09-02"], "topic": "T04"},
        ]
        original = cmd_stats._row_key
        cmd_stats._row_key = lambda e: "same"  # makes the second move look like a duplicate: an id would vanish
        try:
            with self.assertRaises(CheckFailed) as ctx:
                cmd_stats.plan_compaction(active, {}, [], {}, date(2026, 10, 14), "2026-10-14T09:00+01:00")
        finally:
            cmd_stats._row_key = original
        self.assertIn("parity", str(ctx.exception))
        plan = cmd_stats.plan_compaction(active, {}, [], {}, date(2026, 10, 14), "2026-10-14T09:00+01:00")
        self.assertEqual(len(plan["moved_errors"]), 2)


if __name__ == "__main__":
    unittest.main()
