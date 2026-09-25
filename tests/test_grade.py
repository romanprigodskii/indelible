"""grade record: attempts, mistakes, the ladder, levels, recheck obligations, and key secrecy.

Examples use the synthetic persona A (IELTS Academic, subject id ``ielts``).
Sheets, specs and keys are written straight to disk with lib.io, so these
tests do not depend on the sheet commands.
"""

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

NOW = "2026-10-14T09:00+01:00"
MEASURING = ("cold", "diagnostic", "mock", "checkpoint", "probe", "words")


# ==========================================================================
# Fixtures (also imported by test_learning_cmds and test_stats)
# ==========================================================================

def secret_for(ask_id):
    """A distinctive accepted answer: it must never appear in any output."""
    return "quillwort%s" % ask_id.replace("-", "")


def make_item(n, topic, asks, origin="new", layer="verbal"):
    return {"n": n, "topic": topic, "layer": layer, "op": "match-paraphrase", "origin": origin,
            "text": "Question %d: read the sentence and answer." % n,
            "asks": [{"id": a, "label": "Answer:", "check": True, "check_hint": "Read it back"} for a in asks]}


def make_key(items):
    key = {}
    for it in items:
        for a in it["asks"]:
            key[a["id"]] = {"accept": [secret_for(a["id"])], "check": "the sentence still holds",
                            "solution": "worked step for %s" % a["id"]}
    return key


def write_sheet(ws, sid, sheet_id, stype, items, status="issued", evidence=True, key=None, sitting=None):
    """Sealed spec, key and sheets row for a sheet, written directly."""
    root = Path(ws) / sid
    spec = {"v": 1, "id": sheet_id, "type": stype, "subject": sid, "title": "Sheet %s" % sheet_id,
            "est_min": 12, "tools": "none", "answer_form": "short", "items": items,
            "blocks": [], "terms": [], "theory": None, "least_sure": True}
    fio.write_json(root / ".indelible" / "specs" / ("%s.json" % sheet_id), spec)
    key = make_key(items) if key is None else key
    fio.write_json(root / ".indelible" / "keys" / ("%s.json" % sheet_id), key, mode=0o600)
    row = {"v": 1, "id": sheet_id, "subject": sid, "type": stype, "measures": stype in MEASURING,
           "topics": sorted(set(it["topic"] for it in items)), "asks": sum(len(it["asks"]) for it in items),
           "est_min": 12, "status": status, "created": "2026-10-13T19:00+01:00", "lint": "PASS", "files": [],
           "key_sha": "0" * 64, "issued_at": "2026-10-13T19:20+01:00",
           "sat": sitting or {"start": None, "stop": None, "date": None},
           "evidence": [{"path": "scans/%s-answers.jpg" % sheet_id, "kind": "photo"}] if evidence else [],
           "graded_at": None, "opens_unsat": 0, "block": None}
    path = root / "data" / "sheets.jsonl"
    rows = [r for r in fio.read_jsonl(path) if r.get("id") != sheet_id] + [row]
    fio.write_jsonl(path, rows)
    return key


def add_exposure(ws, sid, topic, at, kind="teach"):
    fio.append_jsonl(Path(ws) / sid / "data" / "exposures.jsonl", {"v": 1, "topic": topic, "at": at, "kind": kind})


def add_blocks(ws, blocks):
    path = Path(ws) / "plan" / "blocks.jsonl"
    fio.write_jsonl(path, fio.read_jsonl(path) + list(blocks))


def cold_obligation(block_id, sid, topic, frm, to):
    return {"v": 1, "id": block_id, "subject": sid, "kind": "cold", "start": None, "end": None,
            "window": {"from": frm, "to": to}, "protected": True, "measurement": False, "soft": False,
            "pair": None, "content": "cold:%s" % topic, "status": "planned", "cal": None,
            "moved_from": None, "miss_reason": None}


def write_grades(folder, name, grades):
    path = Path(folder) / name
    path.write_text(json.dumps(grades, ensure_ascii=False), encoding="utf-8")
    return path


def read_rows(path):
    return fio.read_jsonl(path)


class GradeBase(unittest.TestCase):
    NOW = NOW
    PERSONA = "A"

    def setUp(self):
        self._old_now = os.environ.get("INDELIBLE_NOW")
        os.environ["INDELIBLE_NOW"] = self.NOW
        self.tmp = Path(tempfile.mkdtemp(prefix="indelible-grade-"))
        self.ws = make_ws(self.tmp, self.PERSONA)
        self.sid = "ielts"
        self.sdir = self.ws / self.sid
        self.outputs = []
        self.secrets = []

    def tearDown(self):
        if self._old_now is None:
            os.environ.pop("INDELIBLE_NOW", None)
        else:
            os.environ["INDELIBLE_NOW"] = self._old_now
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def cli(self, args, now=None, expect=0):
        r = run(args, ws=self.ws, now=now or self.NOW)
        self.outputs.append(r.stdout + r.stderr)
        if expect is not None:
            self.assertEqual(r.returncode, expect, "%s -> %s\nstdout: %s\nstderr: %s"
                             % (args, r.returncode, r.stdout, r.stderr))
        return r

    def remember_key(self, key):
        for entry in key.values():
            self.secrets.extend(entry["accept"])

    def assert_no_secrets(self):
        self.assertTrue(self.secrets, "no secrets registered")
        for text in self.outputs:
            for s in self.secrets:
                self.assertNotIn(s, text)
                self.assertNotIn(s.lower(), text.lower())

    def errors(self):
        return read_rows(self.sdir / "data" / "errors.jsonl")

    def attempts(self):
        return read_rows(self.sdir / "data" / "attempts.jsonl")

    def topics(self):
        return fio.read_json(self.sdir / "data" / "topics.json", default={}) or {}

    def sheet(self, sheet_id):
        for r in read_rows(self.sdir / "data" / "sheets.jsonl"):
            if r["id"] == sheet_id:
                return r
        return None


# ==========================================================================
# A cold sheet, graded
# ==========================================================================

class ColdSheetTests(GradeBase):
    """T04 and T01 were taught on Mon 12 Oct; the 2-day recheck is taken Wed 14 Oct at 08:00."""

    def setUp(self):
        GradeBase.setUp(self)
        add_exposure(self.ws, self.sid, "T04", "2026-10-12T07:20+01:00")
        add_exposure(self.ws, self.sid, "T01", "2026-10-12T07:40+01:00")
        add_blocks(self.ws, [
            cold_obligation("B-20261014-ielts-1", self.sid, "T04", "2026-10-14T03:20+01:00", "2026-10-15T07:20+01:00"),
            cold_obligation("B-20261014-ielts-2", self.sid, "T01", "2026-10-14T03:40+01:00", "2026-10-15T07:40+01:00"),
        ])
        items = []
        for n in range(1, 9):
            topic = "T04" if n % 2 else "T01"
            layer = "verbal" if topic == "T04" else "reading"
            items.append(make_item(n, topic, ["%da" % n], origin="cold:%s" % topic, layer=layer))
        self.key = write_sheet(self.ws, self.sid, "ielts-cold-01", "cold", items)
        self.remember_key(self.key)
        # T04: 3 of 4 right (75%). T01: three right answers, all on the Least-sure line, and one wrong.
        self.grades = {"start": "08:00", "stop": "08:12", "date": "2026-10-14", "asks": [
            {"ask": "1a", "verdict": "right", "check": "filled", "least_sure": False},
            {"ask": "2a", "verdict": "right", "check": "filled", "least_sure": True},
            {"ask": "3a", "verdict": "right", "check": "filled", "least_sure": False},
            {"ask": "4a", "verdict": "right", "check": "filled", "least_sure": True},
            {"ask": "5a", "verdict": "right", "check": "caught", "least_sure": False},
            {"ask": "6a", "verdict": "right", "check": "filled", "least_sure": True},
            {"ask": "7a", "verdict": "wrong", "check": "filled", "least_sure": False, "mode": "V", "kind": "belief",
             "account": "didn't know 'albeit'; guessed 'because'", "belief": "reads 'albeit' as 'because'"},
            {"ask": "8a", "verdict": "wrong", "check": "missing", "least_sure": False, "mode": "C", "kind": "slip",
             "account": "slip, copied the wrong numeral", "belief": "copied the numeral from the margin wrongly"},
        ]}

    def record(self, *extra, **kw):
        path = write_grades(self.tmp, "grades.json", self.grades)
        return self.cli(["grade", "record", self.sid, "ielts-cold-01", "--from", path] + list(extra), **kw)

    def test_cold_sheet_writes_attempts_errors_levels_and_closes_obligations(self):
        r = self.record()
        out = r.stdout
        self.assertIn("ielts-cold-01 graded: 6/8 (75%) [measured n=8]", out)
        self.assertIn("Wrong answers not on the Least-sure line: 2 of 2", out)
        self.assertIn("Check lines written: 7 of 8; caught a mistake: 1", out)
        self.assertIn("E-ielts-0001 (belief, needs repair)", out)
        self.assertIn("E-ielts-0002 (slip, due 2026-10-15)", out)
        # 3 of 4 cold is a pass, but 7a opened an untreated wrong idea on T04: held at 2 until repaired.
        self.assertIn("T04 0 → 2", out)
        self.assertIn("2-day recheck done", out)

        rows = self.attempts()
        self.assertEqual(len(rows), 8)
        for a in rows:
            self.assertEqual(a["v"], 1)
            self.assertEqual(a["instrument"], "cold")
            self.assertIs(a["cold"], True)
            self.assertEqual(a["prov"], "measured")
            self.assertEqual(a["sheet"], "ielts-cold-01")
            self.assertEqual(a["at"], "2026-10-14T08:00+01:00")
        by_ask = dict((a["ask"], a) for a in rows)
        self.assertEqual(by_ask["1a"]["interval_h"], 48.7)
        self.assertEqual(by_ask["2a"]["interval_h"], 48.3)
        self.assertEqual(by_ask["1a"]["layer"], "verbal")
        self.assertEqual(by_ask["2a"]["layer"], "reading")
        self.assertEqual(by_ask["7a"]["error_id"], "E-ielts-0001")
        self.assertEqual(by_ask["8a"]["error_id"], "E-ielts-0002")
        self.assertEqual(by_ask["5a"]["check"], "caught")
        self.assertEqual(by_ask["7a"]["score"], 0)
        self.assertEqual(by_ask["1a"]["score"], 1)

        errs = dict((e["id"], e) for e in self.errors())
        self.assertEqual(set(errs), {"E-ielts-0001", "E-ielts-0002"})
        belief = errs["E-ielts-0001"]
        self.assertEqual((belief["kind"], belief["status"], belief["next_due"], belief["topic"]),
                         ("belief", "untreated", None, "T04"))
        self.assertEqual(belief["mode"], "V")
        self.assertIs(belief["named_least_sure"], False)
        self.assertEqual(belief["prov"], "measured")
        self.assertEqual(belief["answer_ref"], ".indelible/keys/errors/E-ielts-0001.json")
        slip = errs["E-ielts-0002"]
        self.assertEqual((slip["kind"], slip["status"], slip["rung"], slip["next_due"]),
                         ("slip", "spacing", 0, "2026-10-15"))
        # The key entry was copied, not printed.
        copied = fio.read_json(self.sdir / ".indelible" / "keys" / "errors" / "E-ielts-0001.json")
        self.assertEqual(copied, {"7a": self.key["7a"]})
        if os.name == "posix":
            mode = (self.sdir / ".indelible" / "keys" / "errors" / "E-ielts-0001.json").stat().st_mode & 0o777
            self.assertEqual(mode, 0o600)

        topics = self.topics()
        self.assertEqual(topics["T04"]["level"], 2)
        self.assertIn("cold 3/4 on ielts-cold-01", topics["T04"]["level_basis"])
        self.assertIn("held at 2 while a wrong idea is not fixed (E-ielts-0001)", topics["T04"]["level_basis"])
        self.assertEqual(topics["T04"]["last_cold"], "2026-10-14T08:00+01:00")
        self.assertEqual(len(topics["T04"]["cold_passes"]), 1)
        # T01's right answers were all on the Least-sure line, so they never count.
        self.assertEqual(topics["T01"]["level"], 0)

        blocks = dict((b["id"], b) for b in read_rows(self.ws / "plan" / "blocks.jsonl"))
        self.assertEqual(blocks["B-20261014-ielts-1"]["status"], "done")
        self.assertEqual(blocks["B-20261014-ielts-2"]["status"], "done")

        sheet = self.sheet("ielts-cold-01")
        self.assertEqual(sheet["status"], "graded")
        self.assertEqual(sheet["graded_at"], NOW)
        self.assertEqual(sheet["sat"], {"start": "08:00", "stop": "08:12", "date": "2026-10-14"})

        # A measuring sheet logs no warm exposure: marking is not teaching.
        exposures = read_rows(self.sdir / "data" / "exposures.jsonl")
        self.assertEqual(sorted((x["topic"], x["at"]) for x in exposures),
                         [("T01", "2026-10-12T07:40+01:00"), ("T04", "2026-10-12T07:20+01:00")])
        # Repairing the wrong idea releases the level.
        r = self.cli(["error", "repair", self.sid, "E-ielts-0001"], now="2026-10-14T18:00+01:00")
        self.assertIn("Levels: T04 2 → 3", r.stdout)
        self.assert_no_secrets()

    def test_graded_once_only(self):
        self.record()
        r = self.record(expect=1)
        self.assertIn("already graded", r.stdout)
        self.assertEqual(len(self.attempts()), 8)
        self.assert_no_secrets()

    def test_least_sure_right_answers_do_not_raise_the_level(self):
        # Every T01 answer right, but all on the Least-sure line: T01 stays below 3.
        self.grades["asks"][-1] = {"ask": "8a", "verdict": "right", "check": "filled", "least_sure": True}
        self.record()
        topics = self.topics()
        self.assertEqual(topics["T01"]["level"], 0)
        self.assertIn("only least-sure questions so far", topics["T01"]["level_basis"])
        self.assertEqual(topics["T04"]["level"], 2)   # held: 7a is an untreated wrong idea
        self.assertEqual(topics["T01"]["cold_passes"], [])
        self.assert_no_secrets()

    def test_shaky_flag_opens_shaky_mistakes_for_least_sure_right_answers(self):
        r = self.record("--shaky")
        errs = [e for e in self.errors() if e["kind"] == "shaky"]
        self.assertEqual(sorted(e["ask"] for e in errs), ["2a", "4a", "6a"])
        for e in errs:
            self.assertEqual((e["status"], e["rung"], e["next_due"]), ("spacing", 1, "2026-10-17"))
            self.assertIs(e["named_least_sure"], True)
            self.assertTrue(e["mode"])
            self.assertTrue(e["account"])
        self.assertIn("(shaky, due 2026-10-17)", r.stdout)
        self.assert_no_secrets()

    def test_requires_evidence(self):
        write_sheet(self.ws, self.sid, "ielts-cold-01", "cold",
                    [make_item(n, "T04" if n % 2 else "T01", ["%da" % n]) for n in range(1, 9)],
                    evidence=False, key=self.key)
        r = self.record(expect=1)
        self.assertIn("No evidence is filed", r.stdout)
        self.assertEqual(self.attempts(), [])
        self.assertEqual(self.sheet("ielts-cold-01")["status"], "issued")

    def test_unknown_question_and_missing_mode_are_refused_before_writing(self):
        self.grades["asks"].append({"ask": "9z", "verdict": "right", "check": "filled"})
        del self.grades["asks"][7]["mode"]
        r = self.record(expect=2)
        self.assertIn("'9z' is not on sheet", r.stderr)
        self.assertIn("8a: a mistake needs a mode", r.stderr)
        self.assertEqual(self.attempts(), [])
        self.assertEqual(self.errors(), [])

    def test_belief_containing_an_accepted_answer_is_refused_without_printing_it(self):
        self.grades["asks"][6]["belief"] = "thinks %s is wrong" % secret_for("7a").upper()
        r = self.record(expect=1)
        self.assertIn("7a", r.stdout)
        self.assertIn("accepted answer", r.stdout)
        self.assertEqual(self.attempts(), [])
        self.assert_no_secrets()

    def test_future_date_refused(self):
        self.grades["date"] = "2026-10-20"
        r = self.record(expect=2)
        self.assertIn("in the future", r.stderr)


# ==========================================================================
# Practice sheets and the ladder through grade record
# ==========================================================================

class PracticeAndLadderTests(GradeBase):
    def test_drills_are_practice_and_log_a_drill_exposure(self):
        items = [make_item(n, "T02", ["%da" % n], layer="reading") for n in range(1, 5)]
        key = write_sheet(self.ws, self.sid, "ielts-tfng-01-drills", "drills", items)
        self.remember_key(key)
        grades = {"date": "2026-10-14", "start": "07:10", "stop": "07:30", "asks": [
            {"ask": "1a", "verdict": "right", "check": "filled"},
            {"ask": "2a", "verdict": "right", "check": "filled"},
            {"ask": "3a", "verdict": "half", "check": "filled", "kind": "slip", "mode": "F",
             "account": "left out the second part", "belief": "stops after the first clause"},
            {"ask": "4a", "verdict": "right", "check": "filled"}]}
        path = write_grades(self.tmp, "g.json", grades)
        r = self.cli(["grade", "record", self.sid, "ielts-tfng-01-drills", "--from", path])
        self.assertIn("3.5/4 (88%) [practice]", r.stdout)
        self.assertNotIn("measured", r.stdout)
        rows = self.attempts()
        self.assertTrue(all(a["instrument"] == "practice" and a["prov"] == "practice" and a["cold"] is False
                            for a in rows))
        self.assertIsNone(rows[0]["interval_h"])
        self.assertEqual(self.topics()["T02"]["level"], 2)
        err = self.errors()[0]
        self.assertEqual((err["kind"], err["prov"], err["next_due"]), ("slip", "practice", "2026-10-15"))
        exp = read_rows(self.sdir / "data" / "exposures.jsonl")
        # timed when the sheet was sat (its stop time), not when it was marked
        self.assertEqual([(x["topic"], x["kind"], x["at"]) for x in exp], [("T02", "drill", "2026-10-14T07:30+01:00")])
        self.assert_no_secrets()

    def test_error_ladder_moves_through_grade_record(self):
        # A slip and a belief, opened by hand on Wed 14 Oct.
        self.cli(["error", "add", self.sid, "--topic", "T02", "--kind", "slip", "--mode", "C",
                  "--belief", "skips the negative in the statement", "--account", "slip"])
        self.cli(["error", "add", self.sid, "--topic", "T04", "--kind", "belief", "--mode", "D",
                  "--belief", "reads 'unless' as 'if'", "--account", "thought unless meant if"])
        self.cli(["error", "repair", self.sid, "E-ielts-0002", "--sheet", "ielts-unless-01-repair"],
                 now="2026-10-14T06:30+01:00")
        errs = dict((e["id"], e) for e in self.errors())
        self.assertEqual(errs["E-ielts-0002"]["status"], "spacing")
        self.assertEqual(errs["E-ielts-0002"]["next_due"], "2026-10-15")

        # Thu 15 Oct: both come back on a recheck. The slip is right, the belief is missed again.
        items = [make_item(1, "T02", ["1a"], origin="error:E-ielts-0001", layer="reading"),
                 make_item(2, "T04", ["2a", "2b"], origin="error:E-ielts-0002")]
        key = write_sheet(self.ws, self.sid, "ielts-cold-02", "cold", items)
        self.remember_key(key)
        grades = {"date": "2026-10-15", "start": "07:05", "stop": "07:15", "asks": [
            {"ask": "1a", "verdict": "right", "check": "filled"},
            {"ask": "2a", "verdict": "right", "check": "filled"},
            {"ask": "2b", "verdict": "wrong", "check": "filled", "mode": "D", "account": "same as before"}]}
        path = write_grades(self.tmp, "g2.json", grades)
        r = self.cli(["grade", "record", self.sid, "ielts-cold-02", "--from", path], now="2026-10-15T09:00+01:00")
        self.assertIn("E-ielts-0001 passed, rung 1, due 2026-10-18", r.stdout)
        self.assertIn("E-ielts-0002 missed, needs repair", r.stdout)
        self.assertIn("Mistakes opened: none", r.stdout)
        errs = dict((e["id"], e) for e in self.errors())
        self.assertEqual(len(errs), 2)
        slip = errs["E-ielts-0001"]
        self.assertEqual((slip["status"], slip["rung"], slip["next_due"], slip["passes"]),
                         ("spacing", 1, "2026-10-18", ["2026-10-15"]))
        belief = errs["E-ielts-0002"]
        self.assertEqual((belief["status"], belief["rung"], belief["next_due"], belief["fails"]),
                         ("untreated", 0, None, ["2026-10-15"]))
        by_ask = dict((a["ask"], a) for a in self.attempts())
        self.assertEqual(by_ask["1a"]["error_id"], "E-ielts-0001")
        self.assertEqual(by_ask["2b"]["error_id"], "E-ielts-0002")
        self.assert_no_secrets()

    def test_sentinel_serve_on_an_archived_mistake(self):
        retired = {"v": 1, "id": "E-ielts-0001", "opened": "2026-09-01", "topic": "T02", "kind": "slip", "mode": "C",
                   "belief": "skips the negative", "status": "retired", "rung": 3, "next_due": None,
                   "passes": ["2026-09-02", "2026-09-05", "2026-09-12", "2026-10-03"], "fails": [],
                   "outcome": "retired 2026-10-03 after 4 passes and 0 misses"}
        fio.write_jsonl(self.sdir / "archive" / "errors-2026-10.jsonl", [retired])
        retired2 = dict(retired, id="E-ielts-0002")
        fio.write_jsonl(self.sdir / "archive" / "errors-2026-09.jsonl", [retired2])
        items = [make_item(1, "T02", ["1a"], origin="sentinel:E-ielts-0001", layer="reading"),
                 make_item(2, "T04", ["2a"], origin="sentinel:E-ielts-0002")]
        key = write_sheet(self.ws, self.sid, "ielts-cold-09", "cold", items)
        self.remember_key(key)
        grades = {"date": "2026-10-14", "start": "07:00", "asks": [
            {"ask": "1a", "verdict": "wrong", "check": "filled", "mode": "C", "account": "slip"},
            {"ask": "2a", "verdict": "right", "check": "filled"}]}
        path = write_grades(self.tmp, "g.json", grades)
        r = self.cli(["grade", "record", self.sid, "ielts-cold-09", "--from", path])
        self.assertIn("E-ielts-0001 missed its sentinel serve: back from the archive, rung 0, due 2026-10-15", r.stdout)
        self.assertIn("E-ielts-0002 passed its sentinel serve", r.stdout)
        active = self.errors()
        self.assertEqual([(e["id"], e["status"]) for e in active], [("E-ielts-0001", "reopened")])
        # The archive is never rewritten by grading.
        self.assertEqual(read_rows(self.sdir / "archive" / "errors-2026-10.jsonl"), [retired])
        self.assert_no_secrets()

    def test_issued_sheet_without_a_spec_is_refused(self):
        items = [make_item(1, "T02", ["1a"])]
        key = write_sheet(self.ws, self.sid, "ielts-x-01", "drills", items)
        self.remember_key(key)
        (self.sdir / ".indelible" / "specs" / "ielts-x-01.json").unlink()
        path = write_grades(self.tmp, "g.json", {"asks": [{"ask": "1a", "verdict": "right", "check": "filled"}]})
        r = self.cli(["grade", "record", self.sid, "ielts-x-01", "--from", path], expect=2)
        self.assertIn("No sealed spec", r.stderr)
        self.assert_no_secrets()



# ==========================================================================
# Regression tests for the grading fixes
# ==========================================================================

class GradingRegressionTests(GradeBase):
    """Diagnostics, repair pencils, theory pencils, contamination and served blocks."""

    def grade(self, sheet_id, grades, now=None, expect=0):
        path = write_grades(self.tmp, "g-%s.json" % sheet_id, grades)
        return self.cli(["grade", "record", self.sid, sheet_id, "--from", path], now=now, expect=expect)

    def exposures(self):
        return read_rows(self.sdir / "data" / "exposures.jsonl")

    def test_a_diagnostic_logs_no_exposure_so_untaught_topics_are_never_rechecks(self):
        items = [make_item(n, ("T01", "T02", "T03", "T04")[(n - 1) % 4], ["%da" % n], layer="reading")
                 for n in range(1, 9)]
        key = write_sheet(self.ws, self.sid, "ielts-diagnostic-01", "diagnostic", items)
        self.remember_key(key)
        self.grade("ielts-diagnostic-01", {"date": "2026-10-12", "start": "07:00", "stop": "07:40", "asks": [
            {"ask": "%da" % n, "verdict": "right" if n % 3 else "dont_know", "check": "filled"} for n in range(1, 9)]},
            now="2026-10-12T07:45+01:00")
        self.assertEqual(self.exposures(), [])
        # 48 h later nothing is a 2-day recheck: none of these topics was taught.
        r = self.cli(["due", self.sid, "--list"], now="2026-10-14T07:45+01:00")
        tier1 = r.stdout.split("1. 2-day rechecks", 1)[1].split("2. ", 1)[0]
        self.assertIn("none", tier1)
        r = self.cli(["brief", self.sid], now="2026-10-14T07:45+01:00")
        self.assertNotIn("2-day rechecks ready now", r.stdout)
        self.assertNotIn("RECHECK NOW", r.stdout)
        self.assert_no_secrets()

    def test_a_repair_sheet_never_moves_the_ladder(self):
        self.cli(["error", "add", self.sid, "--topic", "T04", "--kind", "belief", "--mode", "D",
                  "--belief", "reads 'unless' as 'if'", "--account", "thought unless meant if"])
        items = [make_item(1, "T04", ["1a"], origin="error:E-ielts-0001")]
        key = write_sheet(self.ws, self.sid, "ielts-repair-01", "repair", items)
        self.remember_key(key)
        r = self.grade("ielts-repair-01", {"date": "2026-10-14", "start": "07:00", "stop": "07:10",
                                           "asks": [{"ask": "1a", "verdict": "right", "check": "n/a"}]})
        self.assertIn("no ladder move", r.stdout)
        e = self.errors()[0]
        self.assertEqual((e["status"], e["rung"], e["next_due"], e["passes"]), ("untreated", 0, None, []))
        # after the repair, the pencil pass is not among the passes that allow early retirement
        self.cli(["error", "repair", self.sid, "E-ielts-0001"], now="2026-10-14T09:00+01:00")
        self.assertEqual(self.errors()[0]["passes"], [])
        # and the pencils (done with the fix in view) raise no level
        self.assertEqual(self.topics()["T04"]["level"], 0)
        self.assert_no_secrets()

    def test_an_untreated_wrong_idea_on_a_cold_sheet_is_not_moved(self):
        self.cli(["error", "add", self.sid, "--topic", "T02", "--kind", "belief", "--mode", "D",
                  "--belief", "treats 'not given' as 'false'", "--account", "mixed them up"])
        items = [make_item(1, "T02", ["1a"], origin="error:E-ielts-0001", layer="reading")]
        key = write_sheet(self.ws, self.sid, "ielts-cold-07", "cold", items)
        self.remember_key(key)
        r = self.grade("ielts-cold-07", {"date": "2026-10-14", "start": "07:00", "stop": "07:05",
                                         "asks": [{"ask": "1a", "verdict": "right", "check": "filled"}]})
        self.assertIn("E-ielts-0001 not moved: the wrong idea is not fixed yet", r.stdout)
        e = self.errors()[0]
        self.assertEqual((e["status"], e["rung"], e["passes"]), ("untreated", 0, []))
        self.assert_no_secrets()

    def test_theory_pencils_are_recorded_but_raise_no_level(self):
        items = [make_item(n, "T01", ["%da" % n], layer="reading") for n in range(1, 6)]
        key = write_sheet(self.ws, self.sid, "ielts-headings-01-theory", "theory", items)
        self.remember_key(key)
        r = self.grade("ielts-headings-01-theory", {"date": "2026-10-14", "start": "07:00", "stop": "07:15",
                                                     "asks": [{"ask": "%da" % n, "verdict": "right", "check": "n/a"}
                                                              for n in range(1, 6)]})
        self.assertIn("5/5 (100%) [practice]", r.stdout)
        self.assertIn("Levels: no change", r.stdout)
        self.assertEqual(self.topics()["T01"]["level"], 0)
        self.assertTrue(all(a["sheet_type"] == "theory" for a in self.attempts()))
        self.assert_no_secrets()

    def test_a_recheck_seen_in_the_24_hours_before_is_not_counted(self):
        add_exposure(self.ws, self.sid, "T04", "2026-10-12T07:20+01:00")
        add_exposure(self.ws, self.sid, "T04", "2026-10-13T20:00+01:00", kind="chat")   # 12 h before the sitting
        add_blocks(self.ws, [cold_obligation("B-20261014-ielts-1", self.sid, "T04",
                                             "2026-10-14T03:20+01:00", "2026-10-15T07:20+01:00")])
        items = [make_item(1, "T04", ["1a", "1b"], origin="cold:T04")]
        key = write_sheet(self.ws, self.sid, "ielts-cold-08", "cold", items)
        self.remember_key(key)
        r = self.grade("ielts-cold-08", {"date": "2026-10-14", "start": "08:00", "stop": "08:05", "asks": [
            {"ask": "1a", "verdict": "right", "check": "filled"},
            {"ask": "1b", "verdict": "right", "check": "filled"}]})
        self.assertIn("Not counted (seen too recently", r.stdout)
        self.assertTrue(all(a.get("contaminated") is True for a in self.attempts()))
        self.assertEqual(self.topics()["T04"]["level"], 0)
        self.assertIsNone(self.topics().get("T04", {}).get("last_cold"))
        blocks = dict((b["id"], b) for b in read_rows(self.ws / "plan" / "blocks.jsonl"))
        self.assertEqual(blocks["B-20261014-ielts-1"]["status"], "planned")   # still open
        self.assert_no_secrets()

    def test_only_the_served_recheck_block_is_closed(self):
        add_exposure(self.ws, self.sid, "T04", "2026-10-12T07:10+01:00")
        add_exposure(self.ws, self.sid, "T02", "2026-10-12T07:30+01:00")

        def timed(bid, start, end, content):
            return {"v": 1, "id": bid, "subject": self.sid, "kind": "cold", "start": start, "end": end,
                    "window": None, "protected": True, "measurement": False, "soft": False, "pair": None,
                    "content": content, "status": "planned", "cal": None, "moved_from": None, "miss_reason": None}

        add_blocks(self.ws, [
            timed("B-20261014-ielts-1", "2026-10-14T07:00+01:00", "2026-10-14T07:20+01:00", "cold:T04,T02"),
            timed("B-20261021-ielts-1", "2026-10-21T07:00+01:00", "2026-10-21T07:20+01:00", "cold:T04"),
        ])
        items = [make_item(1, "T04", ["1a", "1b"], origin="cold:T04"),
                 make_item(2, "T02", ["2a"], origin="cold:T02", layer="reading")]
        key = write_sheet(self.ws, self.sid, "ielts-cold-01", "cold", items)
        self.remember_key(key)
        r = self.grade("ielts-cold-01", {"date": "2026-10-14", "start": "07:02", "stop": "07:14", "asks": [
            {"ask": a, "verdict": "right", "check": "filled"} for a in ("1a", "1b", "2a")]})
        self.assertIn("2-day recheck done: T04 (B-20261014-ielts-1), T02 (B-20261014-ielts-1)", r.stdout)
        blocks = dict((b["id"], b) for b in read_rows(self.ws / "plan" / "blocks.jsonl"))
        self.assertEqual(blocks["B-20261014-ielts-1"]["status"], "done")
        self.assertEqual(blocks["B-20261021-ielts-1"]["status"], "planned")   # booked for later: left open
        self.assert_no_secrets()

    def test_a_question_can_carry_its_own_topic(self):
        items = [make_item(1, "T01", ["1a", "1b"], layer="reading")]
        items[0]["asks"][1]["topic"] = "T02"
        key = write_sheet(self.ws, self.sid, "ielts-drills-09", "drills", items)
        self.remember_key(key)
        self.grade("ielts-drills-09", {"date": "2026-10-14", "start": "07:00", "stop": "07:10", "asks": [
            {"ask": "1a", "verdict": "right", "check": "filled"},
            {"ask": "1b", "verdict": "right", "check": "filled"}]})
        by_ask = dict((a["ask"], a["topic"]) for a in self.attempts())
        self.assertEqual(by_ask, {"1a": "T01", "1b": "T02"})
        self.assert_no_secrets()

    def test_the_sitting_date_follows_the_workspace_clock(self):
        # 19:30 in New York is 00:30 the next day in Lisbon, the workspace zone.
        items = [make_item(1, "T02", ["1a"], layer="reading")]
        key = write_sheet(self.ws, self.sid, "ielts-drills-10", "drills", items)
        self.remember_key(key)
        self.cli(["sheet", "sat", self.sid, "ielts-drills-10", "--start", "00:31"], now="2026-10-12T19:40-04:00")
        self.assertEqual(self.sheet("ielts-drills-10")["sat"]["date"], "2026-10-13")
        self.assert_no_secrets()


if __name__ == "__main__":
    unittest.main()
