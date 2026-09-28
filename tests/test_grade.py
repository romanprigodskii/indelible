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
    from helpers import HAS_TZDB, make_ws, run
except ImportError:  # run as part of the tests package
    from tests.helpers import HAS_TZDB, make_ws, run

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


def write_sheet(ws, sid, sheet_id, stype, items, status="issued", evidence=True, key=None, sitting=None,
                block=None, issued="2026-10-13T19:20+01:00"):
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
           "key_sha": "0" * 64, "issued_at": issued,
           "sat": sitting or {"start": None, "stop": None, "date": None},
           "evidence": [{"path": "scans/%s-answers.jpg" % sheet_id, "kind": "photo"}] if evidence else [],
           "graded_at": None, "opens_unsat": 0, "block": block}
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

    def test_a_failed_check_with_the_answer_kept_is_recorded_apart(self):
        # The learner marked the checks on 3 and 7 with a cross and left both answers: `failed`.
        self.grades["asks"][2]["check"] = "failed"
        self.grades["asks"][6]["check"] = "failed"
        out = self.record().stdout
        self.assertIn("Check lines written: 7 of 8; caught a mistake: 1; failed, answer kept: 2 (1 of them right)",
                      out)
        by_ask = dict((a["ask"], a) for a in self.attempts())
        self.assertEqual((by_ask["3a"]["check"], by_ask["7a"]["check"]), ("failed", "failed"))

    def test_a_check_in_the_head_is_recorded_apart_as_self_report(self):
        # The learner declined the lines on this sheet: 8a's empty line was checked in the head.
        # It stays out of the written count (7 of 8) and is reported apart, with its miss.
        self.grades["asks"][7]["check"] = "head"
        out = self.record().stdout
        self.assertIn("Check lines written: 7 of 8; caught a mistake: 1; checked in the head [self-report]: 1, 1 missed",
                      out)
        self.assertEqual(dict((a["ask"], a["check"]) for a in self.attempts())["8a"], "head")

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
        self.assertNotIn("cold_passes", topics["T04"])   # cold passes live in attempts.jsonl only
        # T01's right answers were all on the Least-sure line, so they never count: one counted
        # question is too few for a cold pass, so T01's recheck stays open and last_cold unset.
        self.assertEqual(topics["T01"]["level"], 0)
        self.assertIsNone(topics["T01"]["last_cold"])
        self.assertIn("T01: 1 counted question; a cold pass needs at least 2, so this sitting can't raise "
                      "mastery. Its 2-day recheck stays open: serve it again, with at least 2 questions, "
                      "before Thu 15 Oct 07:40.", out)
        self.assertIn("2-day recheck done: T04 (B-20261014-ielts-1)", out)

        blocks = dict((b["id"], b) for b in read_rows(self.ws / "plan" / "blocks.jsonl"))
        self.assertEqual(blocks["B-20261014-ielts-1"]["status"], "done")
        self.assertEqual(blocks["B-20261014-ielts-2"]["status"], "planned")

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

    def test_one_wrong_idea_on_two_questions_is_one_mistake_with_the_account_on_both(self):
        # session-grade.md §5: the same wrong idea on 3 and 7 is one mistake. `kind` goes on the
        # first question only; the second gets the same account and no kind, so it keeps the
        # learner's words on its row without opening a second fix sheet for one fix.
        account = "didn't know 'albeit'; guessed 'because'"
        self.grades["asks"][2] = dict(self.grades["asks"][6], ask="3a")
        self.grades["asks"][6] = {"ask": "7a", "verdict": "wrong", "check": "filled", "least_sure": False,
                                  "mode": "V", "account": account}
        out = self.record().stdout
        self.assertIn("Misses with no kind (no mistake opened): 7a", out)
        errs = [e for e in self.errors() if e["kind"] == "belief"]
        self.assertEqual([(e["topic"], e["account"]) for e in errs], [("T04", account)])
        by_ask = dict((a["ask"], a) for a in self.attempts())
        self.assertEqual(by_ask["3a"]["error_id"], errs[0]["id"])
        self.assertIsNone(by_ask["7a"]["error_id"])
        self.assertEqual((by_ask["7a"]["account"], by_ask["7a"]["mode"]), (account, "V"))

    def test_an_older_topics_file_with_cold_passes_still_grades(self):
        old = [{"at": "2026-10-10T07:00+01:00", "sheet": "ielts-cold-00", "score": "2/2"}]
        fio.write_json(self.sdir / "data" / "topics.json", {"T04": {
            "level": 0, "level_basis": "no evidence yet", "taught_at": "2026-10-12T07:20+01:00",
            "taught_by": "sheet", "last_cold": None, "cold_passes": old, "explanation_on_file": False, "note": ""}})
        r = self.record()
        self.assertIn("T04 0 → 2", r.stdout)
        topics = self.topics()
        self.assertEqual(topics["T04"]["cold_passes"], old)   # left as it was: nothing reads or adds to it
        self.assertEqual(topics["T04"]["last_cold"], "2026-10-14T08:00+01:00")
        self.assertNotIn("cold_passes", topics["T01"])

    def test_a_question_left_out_of_the_grades_file_is_named_in_a_note(self):
        # A page read as missing: 5a and 6a never reached the grades file. The rest is
        # recorded, and the note names both, so a missed page can't pass silently.
        self.grades["asks"] = [g for g in self.grades["asks"] if g["ask"] not in ("5a", "6a")]
        out = self.record().stdout
        self.assertIn("Note: no entry for 5a, 6a in the grades file, so they were not recorded.", out)
        self.assertIn("session-grade.md §8", out)
        self.assertEqual(sorted(a["ask"] for a in self.attempts()), ["1a", "2a", "3a", "4a", "7a", "8a"])
        self.assert_no_secrets()

    def test_an_untaught_case_left_out_of_a_recheck_does_not_count_against_it(self):
        # session-grade.md §5: 7a tested a case no sheet the learner read had worked. On a
        # recheck it is left out of the grades file, with no kind: T04 is judged on the
        # other three, so Claude's mistake neither fails the recheck nor holds it below 3.
        self.grades["asks"] = [g for g in self.grades["asks"] if g["ask"] != "7a"]
        out = self.record().stdout
        self.assertIn("Note: no entry for 7a in the grades file, so it was not recorded.", out)
        self.assertIn("T04 0 → 3", out)
        self.assertIn("cold 3/3 on ielts-cold-01", self.topics()["T04"]["level_basis"])
        self.assertNotIn("E-ielts-0001 (belief", out)

    def test_a_complete_grades_file_gets_no_left_out_note(self):
        self.assertNotIn("no entry for", self.record().stdout)

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
        self.assertNotIn("cold_passes", topics["T01"])
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

    def test_the_least_sure_line_is_recorded_named_none_or_blank(self):
        # With a question named, the line is "named", on every row of the sheet.
        self.record()
        self.assertEqual(set(a["least_sure_line"] for a in self.attempts()), {"named"})

    def test_a_line_naming_nothing_must_say_none_or_blank(self):
        # A blank line is not "sure of everything": with nothing named, the grades file says which.
        for g in self.grades["asks"]:
            g["least_sure"] = False
        r = self.record(expect=2)
        self.assertIn('ends with the Least-sure line: give least_sure_line "none"', r.stderr)
        self.assertEqual(self.attempts(), [])
        self.grades["least_sure_line"] = "blank"
        out = self.record().stdout
        self.assertIn("Least-sure line: left blank", out)
        self.assertNotIn("Wrong answers not on the Least-sure line", out)
        self.assertEqual(set(a["least_sure_line"] for a in self.attempts()), {"blank"})

    def test_a_least_sure_line_that_contradicts_the_asks_is_refused(self):
        self.grades["least_sure_line"] = "none"     # but 2a, 4a and 6a are named
        r = self.record(expect=2)
        self.assertIn("grades.least_sure_line is none, but 2a, 4a, 6a have least_sure true", r.stderr)
        self.grades["least_sure_line"] = "sure"
        r = self.record(expect=2)
        self.assertIn("grades.least_sure_line must be one of: named, none, blank", r.stderr)
        # "named" with nothing named, and nothing left out of the file, is refused too.
        self.grades["least_sure_line"] = "named"
        for g in self.grades["asks"]:
            g["least_sure"] = False
        r = self.record(expect=2)
        self.assertIn("grades.least_sure_line is named, but no question has least_sure true", r.stderr)
        self.assertEqual(self.attempts(), [])

    def test_a_line_whose_only_named_question_was_left_out_is_still_named(self):
        # The learner named only 6, and 6 was withdrawn as unclear: out of the file, the line still named.
        self.grades["asks"] = [g for g in self.grades["asks"] if g["ask"] != "6a"]
        for g in self.grades["asks"]:
            g["least_sure"] = False
        r = self.record(expect=2)
        self.assertIn('or, when every question named is left out of this file, "named"', r.stderr)
        self.grades["least_sure_line"] = "named"
        out = self.record().stdout
        self.assertIn("no entry for 6a in the grades file", out)
        self.assertIn("Wrong answers not on the Least-sure line: 2 of 2", out)
        self.assertNotIn("left blank", out)
        self.assertEqual(set(a["least_sure_line"] for a in self.attempts()), {"named"})
        self.assertEqual(len(self.attempts()), 7)

    def test_a_sheet_without_the_line_records_none_of_it(self):
        spec_path = self.sdir / ".indelible" / "specs" / "ielts-cold-01.json"
        spec = fio.read_json(spec_path)
        spec["least_sure"] = False
        fio.write_json(spec_path, spec)
        for g in self.grades["asks"]:
            g["least_sure"] = False
        self.grades["least_sure_line"] = "none"
        r = self.record(expect=2)
        self.assertIn("ielts-cold-01 has no Least-sure line: leave least_sure_line out", r.stderr)
        del self.grades["least_sure_line"]
        out = self.record().stdout
        self.assertNotIn("Least-sure line", out)
        self.assertFalse(any("least_sure_line" in a for a in self.attempts()))

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
# Right answers named on the Least-sure line
# ==========================================================================

class NamedRightAnswerTests(GradeBase):
    """T01 was taught Mon 12 Oct. Its 2-day recheck on Wed 14 Oct has item 1 (1a, 1b) and item 2 (2a),
    all right, and the learner names item 1: one shaky mistake, back on Sat 17 Oct."""

    def setUp(self):
        GradeBase.setUp(self)
        add_exposure(self.ws, self.sid, "T01", "2026-10-12T07:40+01:00")
        add_blocks(self.ws, [cold_obligation("B-20261014-ielts-2", self.sid, "T01",
                                             "2026-10-14T03:40+01:00", "2026-10-15T07:40+01:00")])
        items = [make_item(1, "T01", ["1a", "1b"], origin="cold:T01", layer="reading"),
                 make_item(2, "T01", ["2a"], origin="cold:T01", layer="reading")]
        self.remember_key(write_sheet(self.ws, self.sid, "ielts-cold-01", "cold", items))
        path = write_grades(self.tmp, "g1.json", {"date": "2026-10-14", "start": "08:00", "stop": "08:06", "asks": [
            {"ask": "1a", "verdict": "right", "check": "filled", "least_sure": True},
            {"ask": "1b", "verdict": "right", "check": "filled", "least_sure": True},
            {"ask": "2a", "verdict": "right", "check": "filled"}]})
        self.first = self.cli(["grade", "record", self.sid, "ielts-cold-01", "--from", path, "--shaky"],
                              now="2026-10-14T08:30+01:00").stdout

    def reserve(self, verdicts):
        items = [make_item(1, "T01", ["1a", "1b"], origin="error:E-ielts-0001", layer="reading")]
        self.remember_key(write_sheet(self.ws, self.sid, "ielts-cold-02", "cold", items,
                                      issued="2026-10-17T07:55+01:00"))
        path = write_grades(self.tmp, "g2.json", {"date": "2026-10-17", "start": "08:00", "stop": "08:04",
                                                  "least_sure_line": "none", "asks": [
            {"ask": "%s" % a, "verdict": v, "check": "filled"} for a, v in zip(("1a", "1b"), verdicts)]})
        return self.cli(["grade", "record", self.sid, "ielts-cold-02", "--from", path, "--shaky"],
                        now="2026-10-17T08:30+01:00").stdout

    def test_one_shaky_mistake_per_named_item(self):
        self.assertIn("Mistakes opened: E-ielts-0001 (shaky, due 2026-10-17)", self.first)
        errs = self.errors()
        self.assertEqual(len(errs), 1)
        self.assertEqual((errs[0]["kind"], errs[0]["item"], errs[0]["ask"]), ("shaky", 1, None))
        self.assertEqual(sorted(fio.read_json(self.sdir / errs[0]["answer_ref"])), ["1a", "1b"])
        by_ask = dict((a["ask"], a["error_id"]) for a in self.attempts())
        self.assertEqual(by_ask, {"1a": "E-ielts-0001", "1b": "E-ielts-0001", "2a": None})
        # One counted question: the recheck stays open, and the note says what can still make it count.
        self.assertIn("T01: 1 counted question; a cold pass needs at least 2, so this sitting can't raise mastery "
                      "unless the 2 right answers named on the Least-sure line come back right at +3 days. "
                      "Its 2-day recheck stays open", self.first)
        self.assertIsNone(self.topics()["T01"]["last_cold"])
        self.assert_no_secrets()

    def test_a_right_re_serve_lets_the_named_answers_count_at_their_recheck(self):
        out = self.reserve(("right", "right"))
        self.assertIn("E-ielts-0001 passed", out)
        self.assertIn("Levels: T01 0 → 3", out)
        self.assertIn("T01: its recheck of Wed 14 Oct 08:00 counts now that the right answers named on its "
                      "Least-sure line came back right.", out)
        self.assertIn("2-day recheck done: T01 (B-20261014-ielts-2)", out)
        t01 = self.topics()["T01"]
        self.assertEqual((t01["level"], t01["last_cold"]), (3, "2026-10-14T08:00+01:00"))
        self.assertIn("cold 3/3 on ielts-cold-01", t01["level_basis"])
        # No longer waiting for its 2-day recheck: due offers it no more.
        r = self.cli(["due", self.sid, "--list"], now="2026-10-17T09:00+01:00")
        self.assertNotIn("T01", r.stdout.split("1. 2-day rechecks", 1)[1].split("2. ", 1)[0])
        self.assert_no_secrets()

    def test_a_missed_re_serve_leaves_them_uncounted(self):
        out = self.reserve(("right", "wrong"))
        self.assertIn("E-ielts-0001 missed", out)
        self.assertNotIn("counts now", out)
        self.assertEqual(self.topics()["T01"]["level"], 0)
        self.assertIsNone(self.topics()["T01"]["last_cold"])
        blocks = dict((b["id"], b) for b in read_rows(self.ws / "plan" / "blocks.jsonl"))
        self.assertEqual(blocks["B-20261014-ielts-2"]["status"], "planned")


# ==========================================================================
# Practice sheets and the ladder through grade record
# ==========================================================================

class PracticeAndLadderTests(GradeBase):
    def test_drills_are_practice_and_log_a_drill_exposure(self):
        items = [make_item(n, "T02", ["%da" % n], layer="reading") for n in range(1, 5)]
        key = write_sheet(self.ws, self.sid, "ielts-tfng-01-drills", "drills", items)
        self.remember_key(key)
        grades = {"date": "2026-10-14", "start": "07:10", "stop": "07:30", "least_sure_line": "none", "asks": [
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

    def test_drills_under_half_on_a_new_topic_are_named_as_not_landed(self):
        # session-teach.md §4: "I don't know" and blanks count as misses; the topic is taught again
        # from a new worked case before any recheck on it.
        add_exposure(self.ws, self.sid, "T02", "2026-10-13T19:00+01:00")
        items = [make_item(n, "T02", ["%da" % n], layer="reading") for n in range(1, 5)]
        items += [make_item(5, "T01", ["5a"], layer="reading")]
        self.remember_key(write_sheet(self.ws, self.sid, "ielts-tfng-01-drills", "drills", items))
        grades = {"date": "2026-10-14", "start": "07:10", "stop": "07:30", "least_sure_line": "none", "asks": [
            {"ask": "1a", "verdict": "right", "check": "filled"},
            {"ask": "2a", "verdict": "dont_know"},
            {"ask": "3a", "verdict": "dont_know"},
            {"ask": "4a", "verdict": "skip"},
            {"ask": "5a", "verdict": "wrong", "check": "filled"}]}
        r = self.cli(["grade", "record", self.sid, "ielts-tfng-01-drills", "--from",
                      write_grades(self.tmp, "g.json", grades)])
        self.assertIn("T02: 1/4 on these drills [practice], and its 2-day recheck is still ahead: it hasn't "
                      "landed yet.", r.stdout)
        self.assertIn('ledger add owed --subject ielts --what "re-teach True, false or not given from a new '
                      'worked case"', r.stdout)
        self.assertNotIn("T01:", r.stdout, "T01 was never taught: nothing to land")
        self.assertEqual(self.errors(), [], "no wrong idea in the work: no mistake opened")
        self.assert_no_secrets()

    def test_drills_at_half_or_more_have_landed(self):
        add_exposure(self.ws, self.sid, "T02", "2026-10-13T19:00+01:00")
        items = [make_item(n, "T02", ["%da" % n], layer="reading") for n in range(1, 5)]
        write_sheet(self.ws, self.sid, "ielts-tfng-01-drills", "drills", items)
        grades = {"date": "2026-10-14", "start": "07:10", "stop": "07:30", "least_sure_line": "none", "asks": [
            {"ask": "1a", "verdict": "right", "check": "filled"},
            {"ask": "2a", "verdict": "right", "check": "filled"},
            {"ask": "3a", "verdict": "dont_know"},
            {"ask": "4a", "verdict": "skip"}]}
        r = self.cli(["grade", "record", self.sid, "ielts-tfng-01-drills", "--from",
                      write_grades(self.tmp, "g.json", grades)])
        self.assertNotIn("hasn't landed", r.stdout)

    def under_half_on_t02(self):
        """A 4-question T02 drills sheet graded 1/4 on Wed 14 Oct; returns the output."""
        items = [make_item(n, "T02", ["%da" % n], layer="reading") for n in range(1, 5)]
        write_sheet(self.ws, self.sid, "ielts-tfng-02-drills", "drills", items)
        grades = {"date": "2026-10-14", "start": "07:10", "stop": "07:30", "least_sure_line": "none", "asks": [
            {"ask": "1a", "verdict": "right", "check": "filled"},
            {"ask": "2a", "verdict": "dont_know"},
            {"ask": "3a", "verdict": "wrong", "check": "filled"},
            {"ask": "4a", "verdict": "skip"}]}
        return self.cli(["grade", "record", self.sid, "ielts-tfng-02-drills", "--from",
                         write_grades(self.tmp, "g.json", grades)]).stdout

    def test_a_repairs_drill_block_under_half_is_not_named_as_not_landed(self):
        # A wrong idea on T02 awaits repair: these are its repair's drills, and a miss there gets a new
        # repair page (session-teach.md §1), not a re-teach.
        add_exposure(self.ws, self.sid, "T02", "2026-10-13T19:00+01:00")
        self.cli(["error", "add", self.sid, "--topic", "T02", "--kind", "belief", "--mode", "D",
                  "--belief", "treats a missing fact as false", "--account", "I did it this way"])
        out = self.under_half_on_t02()
        self.assertNotIn("hasn't landed", out)
        self.assertNotIn("re-teach", out)

    def test_a_topic_taught_long_ago_is_not_named_as_not_landed(self):
        # Taught 10 days before the drills, its first recheck never sat: not "this session or the last".
        add_exposure(self.ws, self.sid, "T02", "2026-10-04T19:00+01:00")
        out = self.under_half_on_t02()
        self.assertNotIn("hasn't landed", out)
        self.assertNotIn("re-teach", out)

    def test_a_topic_taught_at_the_last_session_is_named_as_not_landed(self):
        # Taught 60 h before the drills (the last session): still inside the window's far end, 72 h.
        add_exposure(self.ws, self.sid, "T02", "2026-10-11T19:10+01:00")
        self.assertIn("T02: 1/4 on these drills [practice], and its 2-day recheck is still ahead: it hasn't "
                      "landed yet.", self.under_half_on_t02())

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
        grades = {"date": "2026-10-15", "start": "07:05", "stop": "07:15", "least_sure_line": "none", "asks": [
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
        grades = {"date": "2026-10-14", "start": "07:00", "least_sure_line": "none", "asks": [
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
        key = write_sheet(self.ws, self.sid, "ielts-diagnostic-01", "diagnostic", items,
                          issued="2026-10-12T06:55+01:00")
        self.remember_key(key)
        self.grade("ielts-diagnostic-01", {"date": "2026-10-12", "start": "07:00", "stop": "07:40", "least_sure_line": "none", "asks": [
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
                                           "least_sure_line": "none", "asks": [{"ask": "1a", "verdict": "right", "check": "n/a"}]})
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
                                         "least_sure_line": "none", "asks": [{"ask": "1a", "verdict": "right", "check": "filled"}]})
        self.assertIn("E-ielts-0001 not moved: the wrong idea is not fixed yet", r.stdout)
        e = self.errors()[0]
        self.assertEqual((e["status"], e["rung"], e["passes"]), ("untreated", 0, []))
        self.assert_no_secrets()

    def test_theory_pencils_are_recorded_but_raise_no_level(self):
        items = [make_item(n, "T01", ["%da" % n], layer="reading") for n in range(1, 6)]
        key = write_sheet(self.ws, self.sid, "ielts-headings-01-theory", "theory", items)
        self.remember_key(key)
        r = self.grade("ielts-headings-01-theory", {"date": "2026-10-14", "start": "07:00", "stop": "07:15",
                                                     "least_sure_line": "none", "asks": [{"ask": "%da" % n, "verdict": "right", "check": "n/a"}
                                                              for n in range(1, 6)]})
        self.assertIn("5/5 (100%) [practice]", r.stdout)
        self.assertIn("Levels: no change", r.stdout)
        self.assertEqual(self.topics()["T01"]["level"], 0)
        self.assertTrue(all(a["sheet_type"] == "theory" for a in self.attempts()))
        self.assert_no_secrets()

    def test_a_question_printed_without_a_check_line_takes_only_n_a(self):
        # A probe prints no check line: `missing` would lower check coverage for a check never asked for.
        items = [make_item(n, "T04", ["%da" % n]) for n in (1, 2, 3)]
        for it in items:
            for a in it["asks"]:
                a["check"] = False
                a.pop("check_hint", None)
        key = write_sheet(self.ws, self.sid, "ielts-probe-01", "probe", items)
        self.remember_key(key)
        grades = {"date": "2026-10-14", "start": "07:00", "stop": "07:05", "least_sure_line": "none", "asks": [
            {"ask": "1a", "verdict": "right", "check": "missing"},
            {"ask": "2a", "verdict": "right", "check": "head"},
            {"ask": "3a", "verdict": "right"}]}
        r = self.grade("ielts-probe-01", grades, expect=2)
        self.assertIn("1a: this question had no check line; give check n/a", r.stderr)
        # With no line printed, there was no line to leave for a check in the head.
        self.assertIn("2a: this question had no check line", r.stderr)
        self.assertNotIn("3a:", r.stderr)
        self.assertEqual(self.attempts(), [])
        grades["asks"][0]["check"] = "n/a"
        del grades["asks"][1]["check"]
        self.grade("ielts-probe-01", grades)
        self.assertEqual([a["check"] for a in self.attempts()], ["n/a", "n/a", "n/a"])
        self.assert_no_secrets()

    def test_a_recheck_seen_in_the_24_hours_before_is_not_counted(self):
        add_exposure(self.ws, self.sid, "T04", "2026-10-12T07:20+01:00")
        add_exposure(self.ws, self.sid, "T04", "2026-10-13T20:00+01:00", kind="chat")   # 12 h before the sitting
        add_blocks(self.ws, [cold_obligation("B-20261014-ielts-1", self.sid, "T04",
                                             "2026-10-14T03:20+01:00", "2026-10-15T07:20+01:00")])
        items = [make_item(1, "T04", ["1a", "1b"], origin="cold:T04")]
        key = write_sheet(self.ws, self.sid, "ielts-cold-08", "cold", items)
        self.remember_key(key)
        r = self.grade("ielts-cold-08", {"date": "2026-10-14", "start": "08:00", "stop": "08:05", "least_sure_line": "none", "asks": [
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
                 make_item(2, "T02", ["2a", "2b"], origin="cold:T02", layer="reading")]
        key = write_sheet(self.ws, self.sid, "ielts-cold-01", "cold", items)
        self.remember_key(key)
        r = self.grade("ielts-cold-01", {"date": "2026-10-14", "start": "07:02", "stop": "07:14", "least_sure_line": "none", "asks": [
            {"ask": a, "verdict": "right", "check": "filled"} for a in ("1a", "1b", "2a", "2b")]})
        self.assertIn("2-day recheck done: T04 (B-20261014-ielts-1), T02 (B-20261014-ielts-1)", r.stdout)
        blocks = dict((b["id"], b) for b in read_rows(self.ws / "plan" / "blocks.jsonl"))
        self.assertEqual(blocks["B-20261014-ielts-1"]["status"], "done")
        self.assertEqual(blocks["B-20261021-ielts-1"]["status"], "planned")   # booked for later: left open
        self.assert_no_secrets()

    def test_a_two_topic_recheck_stays_open_for_the_topic_served_too_thinly(self):
        add_exposure(self.ws, self.sid, "T01", "2026-10-12T07:40+01:00")
        add_exposure(self.ws, self.sid, "T04", "2026-10-12T07:40+01:00")
        b = cold_obligation("B-20261014-ielts-2", self.sid, "T01", "2026-10-14T03:40+01:00", "2026-10-15T07:40+01:00")
        b["content"] = "cold:T01,T04"
        add_blocks(self.ws, [b])
        items = [make_item(1, "T01", ["1a"], origin="cold:T01", layer="reading"),
                 make_item(2, "T04", ["2a"], origin="cold:T04"), make_item(3, "T04", ["3a"], origin="cold:T04")]
        key = write_sheet(self.ws, self.sid, "ielts-cold-09", "cold", items, block="B-20261014-ielts-2")
        self.remember_key(key)
        r = self.grade("ielts-cold-09", {"date": "2026-10-14", "start": "08:00", "stop": "08:03",
                                         "least_sure_line": "none", "asks": [
            {"ask": a, "verdict": "right", "check": "filled"} for a in ("1a", "2a", "3a")]})
        self.assertIn("Levels: T04 0 → 3", r.stdout)
        self.assertNotIn("2-day recheck done", r.stdout)
        self.assertIn("Recheck B-20261014-ielts-2 stays open for T01 (T04 served).", r.stdout)
        self.assertIn("Its 2-day recheck stays open: serve it again, with at least 2 questions, before Thu 15 Oct "
                      "07:40.", r.stdout)
        blocks = dict((b["id"], b) for b in read_rows(self.ws / "plan" / "blocks.jsonl"))
        self.assertEqual(blocks["B-20261014-ielts-2"]["status"], "planned")
        # Not served again in its window: a late recheck for T01 alone (T04 used its serve).
        r = self.cli(["due", self.sid, "--list"], now="2026-10-16T10:00+01:00")
        late = r.stdout.split("0. late rechecks", 1)[1].split("1. 2-day", 1)[0]
        self.assertIn("B-20261014-ielts-2 T01 Matching headings", late)
        self.assertNotIn("T04", late)
        self.assertIn("LATE RECHECK (plan.md §7): B-20261014-ielts-2 T01 Matching headings",
                      self.cli(["brief", self.sid], now="2026-10-16T10:00+01:00").stdout)
        # Had it been served again with 2 questions inside its window (due and brief write nothing), the block closes.
        items = [make_item(n, "T01", ["%da" % n], origin="cold:T01", layer="reading") for n in (1, 2)]
        key = write_sheet(self.ws, self.sid, "ielts-cold-10", "cold", items, block="B-20261014-ielts-2",
                          issued="2026-10-15T06:55+01:00")
        self.remember_key(key)
        r = self.grade("ielts-cold-10", {"date": "2026-10-15", "start": "07:00", "stop": "07:05",
                                         "least_sure_line": "none", "asks": [
            {"ask": "%da" % n, "verdict": "right", "check": "filled"} for n in (1, 2)]}, now="2026-10-15T07:10+01:00")
        self.assertIn("2-day recheck done: T01 (B-20261014-ielts-2)", r.stdout)
        blocks = dict((b["id"], b) for b in read_rows(self.ws / "plan" / "blocks.jsonl"))
        self.assertEqual(blocks["B-20261014-ielts-2"]["status"], "done")
        self.assert_no_secrets()

    def test_a_two_topic_recheck_stays_open_for_the_topic_seen_too_recently(self):
        add_exposure(self.ws, self.sid, "T02", "2026-10-12T07:40+01:00")
        add_exposure(self.ws, self.sid, "T04", "2026-10-12T07:40+01:00")
        add_exposure(self.ws, self.sid, "T02", "2026-10-13T20:00+01:00", kind="chat")   # 12 h before the sitting
        b = cold_obligation("B-20261014-ielts-2", self.sid, "T02", "2026-10-14T03:40+01:00", "2026-10-15T07:40+01:00")
        b["content"] = "cold:T02,T04"
        add_blocks(self.ws, [b])
        items = [make_item(1, "T02", ["1a", "1b"], origin="cold:T02", layer="reading"),
                 make_item(2, "T04", ["2a", "2b"], origin="cold:T04")]
        key = write_sheet(self.ws, self.sid, "ielts-cold-09", "cold", items, block="B-20261014-ielts-2")
        self.remember_key(key)
        r = self.grade("ielts-cold-09", {"date": "2026-10-14", "start": "08:00", "stop": "08:05",
                                         "least_sure_line": "none", "asks": [
            {"ask": a, "verdict": "right", "check": "filled"} for a in ("1a", "1b", "2a", "2b")]})
        self.assertIn("Not counted (seen too recently", r.stdout)
        self.assertIn("Recheck B-20261014-ielts-2 stays open for T02 (T04 served).", r.stdout)
        blocks = dict((b["id"], b) for b in read_rows(self.ws / "plan" / "blocks.jsonl"))
        self.assertEqual(blocks["B-20261014-ielts-2"]["status"], "planned")
        self.assert_no_secrets()

    def test_a_mixed_sheet_serves_no_recheck_and_moves_no_warm_mistake(self):
        # T01 taught Mon; its 2-day recheck is open. Two slips are due; T04 was drilled
        # an hour before a mixed practice sheet that carries a cold:T01 item anyway.
        add_exposure(self.ws, self.sid, "T01", "2026-10-12T07:40+01:00")
        add_exposure(self.ws, self.sid, "T04", "2026-10-14T06:00+01:00", kind="drill")
        add_blocks(self.ws, [cold_obligation("B-20261014-ielts-2", self.sid, "T01",
                                             "2026-10-14T03:40+01:00", "2026-10-15T07:40+01:00")])
        for topic in ("T04", "T02"):
            self.cli(["error", "add", self.sid, "--topic", topic, "--kind", "slip", "--mode", "C",
                      "--belief", "copied the wrong line", "--account", "slip"], now="2026-10-12T09:00+01:00")
        items = [make_item(1, "T01", ["1a"], origin="cold:T01", layer="reading"),
                 make_item(2, "T04", ["2a"], origin="error:E-ielts-0001"),
                 make_item(3, "T02", ["3a"], origin="error:E-ielts-0002", layer="reading")]
        key = write_sheet(self.ws, self.sid, "ielts-mixed-01", "mixed", items)
        self.remember_key(key)
        r = self.grade("ielts-mixed-01", {"date": "2026-10-14", "start": "07:05", "stop": "07:15", "least_sure_line": "none", "asks": [
            {"ask": a, "verdict": "right", "check": "filled"} for a in ("1a", "2a", "3a")]})
        self.assertIn("[practice]", r.stdout)
        self.assertNotIn("2-day recheck done", r.stdout)
        self.assertIn("T01: a 2-day recheck item on a mixed sheet is practice", r.stdout)
        self.assertIn("E-ielts-0001: not counted (its topic was seen in the 24 h before the sitting)", r.stdout)
        self.assertIn("E-ielts-0002 passed, rung 1", r.stdout)   # not seen in 24 h: the ladder still moves
        blocks = dict((b["id"], b) for b in read_rows(self.ws / "plan" / "blocks.jsonl"))
        self.assertEqual(blocks["B-20261014-ielts-2"]["status"], "planned")   # the recheck stays booked
        self.assertIsNone(self.topics().get("T01", {}).get("last_cold"))
        errs = dict((e["id"], e) for e in self.errors())
        self.assertEqual((errs["E-ielts-0001"]["rung"], errs["E-ielts-0001"]["passes"]), (0, []))
        # Practice rows are not marked contaminated: they still count as practice toward a level.
        self.assertFalse(any(a.get("contaminated") for a in self.attempts()))
        # Still a first serve: once the sheet's drill is 44 h old, T01 is offered as a 2-day recheck.
        r = self.cli(["due", self.sid, "--list"], now="2026-10-16T08:00+01:00")
        self.assertIn("T01", r.stdout.split("1. 2-day rechecks", 1)[1].split("2. ", 1)[0])
        self.assert_no_secrets()

    def test_an_override_of_the_24_hour_rule_is_practice_and_the_recheck_stays_booked(self):
        # session-open.md §3 step 6: T01 was explained in chat half an hour ago, and the learner
        # asks to be rechecked on it anyway. They get a mixed sheet of new items, logged as an override.
        add_exposure(self.ws, self.sid, "T01", "2026-10-12T07:40+01:00")
        add_exposure(self.ws, self.sid, "T01", "2026-10-14T06:30+01:00", kind="chat")
        add_blocks(self.ws, [cold_obligation("B-20261014-ielts-2", self.sid, "T01",
                                             "2026-10-14T06:30+01:00", "2026-10-17T06:30+01:00")])
        r = self.cli(["session", "override", self.sid, "recheck me on it today anyway", "--predict",
                      "1 and 2 right"], now="2026-10-14T06:55+01:00")
        self.assertIn("Override logged", r.stdout)
        items = [make_item(n, "T01", ["%da" % n], layer="reading") for n in (1, 2)]
        key = write_sheet(self.ws, self.sid, "ielts-mixed-03", "mixed", items, issued="2026-10-14T06:58+01:00")
        self.remember_key(key)
        r = self.grade("ielts-mixed-03", {"date": "2026-10-14", "start": "07:00", "stop": "07:05",
                                          "least_sure_line": "none", "asks": [
            {"ask": a, "verdict": "right", "check": "filled"} for a in ("1a", "2a")]})
        self.assertIn("[practice]", r.stdout)
        self.assertNotIn("2-day recheck done", r.stdout)
        blocks = dict((b["id"], b) for b in read_rows(self.ws / "plan" / "blocks.jsonl"))
        self.assertEqual(blocks["B-20261014-ielts-2"]["status"], "planned")   # the recheck stays booked
        self.assertIsNone(self.topics().get("T01", {}).get("last_cold"))
        self.assertEqual(self.exposures()[-1]["kind"], "drill")
        # The drill, logged at the stop time, moved T01's first window to 44–72 h after it.
        self.assertEqual(blocks["B-20261014-ielts-2"]["window"]["from"], "2026-10-16T03:05+01:00")
        self.assert_no_secrets()

    def test_a_recheck_topic_with_one_counted_question_uses_nothing_up(self):
        # A one-question recheck on T01 (lint L7 refuses one now; a sheet built before still grades).
        add_exposure(self.ws, self.sid, "T01", "2026-10-12T07:40+01:00")
        add_blocks(self.ws, [cold_obligation("B-20261014-ielts-2", self.sid, "T01",
                                             "2026-10-14T03:40+01:00", "2026-10-15T07:40+01:00")])
        items = [make_item(1, "T01", ["1a"], origin="cold:T01", layer="reading")]
        key = write_sheet(self.ws, self.sid, "ielts-cold-09", "cold", items, block="B-20261014-ielts-2")
        self.remember_key(key)
        r = self.grade("ielts-cold-09", {"date": "2026-10-14", "start": "08:00", "stop": "08:03", "least_sure_line": "none", "asks": [
            {"ask": "1a", "verdict": "right", "check": "filled"}]})
        self.assertIn("graded: 1/1 (100%) [measured n=1]", r.stdout)
        self.assertNotIn("2-day recheck done", r.stdout)
        self.assertIn("T01: 1 counted question; a cold pass needs at least 2", r.stdout)
        self.assertIn("before Thu 15 Oct 07:40", r.stdout)
        blocks = dict((b["id"], b) for b in read_rows(self.ws / "plan" / "blocks.jsonl"))
        self.assertEqual(blocks["B-20261014-ielts-2"]["status"], "planned")   # still booked
        self.assertIsNone(self.topics()["T01"]["last_cold"])
        # Still a first serve, so a later sitting inside the window is the 2-day recheck.
        r = self.cli(["due", self.sid, "--list"], now="2026-10-15T07:00+01:00")
        self.assertIn("T01", r.stdout.split("1. 2-day rechecks", 1)[1].split("2. ", 1)[0])
        items = [make_item(n, "T01", ["%da" % n], origin="cold:T01", layer="reading") for n in (1, 2)]
        key = write_sheet(self.ws, self.sid, "ielts-cold-10", "cold", items, block="B-20261014-ielts-2",
                          issued="2026-10-15T06:55+01:00")
        self.remember_key(key)
        r = self.grade("ielts-cold-10", {"date": "2026-10-15", "start": "07:00", "stop": "07:05", "least_sure_line": "none", "asks": [
            {"ask": "%da" % n, "verdict": "right", "check": "filled"} for n in (1, 2)]},
            now="2026-10-15T07:10+01:00")
        self.assertIn("Levels: T01 0 → 3", r.stdout)
        self.assertIn("2-day recheck done: T01 (B-20261014-ielts-2)", r.stdout)
        # A right answer named on the Least-sure line leaves one counted question, and the window has passed.
        items = [make_item(n, "T02", ["%da" % n], origin="cold:T02", layer="reading") for n in (1, 2)]
        add_exposure(self.ws, self.sid, "T02", "2026-10-12T07:40+01:00")
        key = write_sheet(self.ws, self.sid, "ielts-probe-02", "probe", items, issued="2026-10-16T06:55+01:00")
        self.remember_key(key)
        r = self.grade("ielts-probe-02", {"date": "2026-10-16", "start": "07:00", "stop": "07:05", "asks": [
            {"ask": "1a", "verdict": "right", "check": "n/a", "least_sure": True},
            {"ask": "2a", "verdict": "right", "check": "n/a"}]}, now="2026-10-16T07:10+01:00")
        self.assertIn("T02: 1 counted question; a cold pass needs at least 2, so this sitting can't raise mastery. "
                      "Its window has passed: it is a late recheck (plan.md §7).", r.stdout)
        self.assert_no_secrets()

    def test_a_recheck_that_left_a_topic_below_3_comes_back_after_its_fix(self):
        # T01 and T02 were taught Mon; the recheck on Wed leaves both at 50%: T01 with a wrong idea, T02 a slip.
        add_exposure(self.ws, self.sid, "T01", "2026-10-12T07:40+01:00")
        add_exposure(self.ws, self.sid, "T02", "2026-10-12T07:50+01:00")
        items = [make_item(n, ("T02", "T01")[n % 2], ["%da" % n], origin="cold:%s" % ("T02", "T01")[n % 2],
                           layer="reading") for n in (1, 2, 3, 4)]
        key = write_sheet(self.ws, self.sid, "ielts-cold-01", "cold", items)
        self.remember_key(key)
        r = self.grade("ielts-cold-01", {"date": "2026-10-14", "start": "08:00", "stop": "08:08", "least_sure_line": "none", "asks": [
            {"ask": "1a", "verdict": "right", "check": "filled"},
            {"ask": "2a", "verdict": "right", "check": "filled"},
            {"ask": "3a", "verdict": "wrong", "check": "filled", "mode": "D", "kind": "belief",
             "account": "picked the heading that shares a word", "belief": "matches a heading by a shared word"},
            {"ask": "4a", "verdict": "wrong", "check": "filled", "mode": "C", "kind": "slip",
             "account": "copied the wrong letter", "belief": "copied the wrong letter into the box"}]})
        self.assertIn("T01 is below 3 after this recheck: it comes back as a 2-day recheck 44–72 h after its "
                      "fix sheet (error repair logs it and books the recheck).", r.stdout)
        self.assertIn("T02 is below 3 after this recheck: log the feedback on it (session expose ielts T02 "
                      "--kind review), which books its 2-day recheck 44–72 h later.", r.stdout)
        r = self.cli(["session", "expose", self.sid, "T02", "--kind", "review"], now="2026-10-14T09:00+01:00")
        self.assertIn("Recheck to place: B-20261016-ielts-1.", r.stdout)
        r = self.cli(["due", self.sid, "--list"], now="2026-10-16T10:00+01:00")
        tier1 = r.stdout.split("1. 2-day rechecks", 1)[1].split("2. ", 1)[0]
        self.assertIn("T02 True, false or not given · 49 h since last seen", tier1)
        self.assertIn("again: its last recheck left it below 3", tier1)
        self.assertNotIn("T01", tier1)                      # its wrong idea is not fixed yet
        # T01 is fixed on Sat; it comes back 44-72 h later, and a pass there counts for level 3.
        self.cli(["error", "repair", self.sid, "E-ielts-0001"], now="2026-10-17T10:00+01:00")
        r = self.cli(["due", self.sid, "--list"], now="2026-10-19T11:00+01:00")
        tier1 = r.stdout.split("1. 2-day rechecks", 1)[1].split("2. ", 1)[0]
        self.assertIn("T01 Matching headings · 49 h since last seen", tier1)
        data = json.loads(self.cli(["due", self.sid, "--json"], now="2026-10-19T11:00+01:00").stdout)
        self.assertEqual([(c["topic"], c["again"]) for c in data["tiers"]["1_cold"]], [("T01", True)])
        items = [make_item(n, "T01", ["%da" % n], origin="cold:T01", layer="reading") for n in (1, 2)]
        key = write_sheet(self.ws, self.sid, "ielts-cold-02", "cold", items, issued="2026-10-19T10:55+01:00")
        self.remember_key(key)
        r = self.grade("ielts-cold-02", {"date": "2026-10-19", "start": "11:00", "stop": "11:05", "least_sure_line": "none", "asks": [
            {"ask": "%da" % n, "verdict": "right", "check": "filled"} for n in (1, 2)]},
            now="2026-10-19T11:10+01:00")
        self.assertIn("Levels: T01 0 → 3", r.stdout)
        self.assertNotIn("below 3 after this recheck", r.stdout)
        self.assert_no_secrets()

    def test_a_recheck_again_is_booked_and_flagged_late_when_its_window_passes(self):
        add_exposure(self.ws, self.sid, "T01", "2026-10-12T07:40+01:00")
        add_exposure(self.ws, self.sid, "T02", "2026-10-12T07:50+01:00")
        items = [make_item(n, ("T02", "T01")[n % 2], ["%da" % n], origin="cold:%s" % ("T02", "T01")[n % 2],
                           layer="reading") for n in (1, 2, 3, 4)]
        key = write_sheet(self.ws, self.sid, "ielts-cold-01", "cold", items)
        self.remember_key(key)
        self.grade("ielts-cold-01", {"date": "2026-10-14", "start": "08:00", "stop": "08:08", "least_sure_line": "none", "asks": [
            {"ask": "1a", "verdict": "right", "check": "filled"},
            {"ask": "2a", "verdict": "right", "check": "filled"},
            {"ask": "3a", "verdict": "wrong", "check": "filled", "mode": "D", "kind": "belief",
             "account": "picked the heading that shares a word", "belief": "matches a heading by a shared word"},
            {"ask": "4a", "verdict": "wrong", "check": "filled", "mode": "C", "kind": "slip",
             "account": "copied the wrong letter", "belief": "copied the wrong letter into the box"}]})

        def colds():
            return [b for b in read_rows(self.ws / "plan" / "blocks.jsonl") if b["kind"] == "cold"]

        # The feedback on T02 opens its window again and books it, as session taught does.
        r = self.cli(["session", "expose", self.sid, "T02", "--kind", "review"], now="2026-10-14T09:00+01:00")
        self.assertIn("Its 2-day recheck now falls between Fri 16 Oct 05:00 and Sat 17 Oct 09:00", r.stdout)
        self.assertIn("Recheck to place: B-20261016-ielts-1. Put it in the first session inside the window: "
                      "plan place B-20261016-ielts-1 --start ISO --min N", r.stdout)
        booked = colds()
        self.assertEqual([(b["id"], b["content"], b["start"], b["protected"], b["window"]) for b in booked],
                         [("B-20261016-ielts-1", "cold:T02", None, True,
                           {"from": "2026-10-16T05:00+01:00", "to": "2026-10-17T09:00+01:00", "basis": "exposure"})])
        # A later exposure moves that booking rather than adding another.
        r = self.cli(["session", "expose", self.sid, "T02", "--kind", "chat"], now="2026-10-14T20:00+01:00")
        self.assertIn("Recheck B-20261016-ielts-1: window moved to", r.stdout)
        self.assertNotIn("Recheck to place", r.stdout)
        self.assertEqual(len(colds()), 1)
        # T01's wrong idea is not fixed: feedback books nothing yet; the repair does.
        r = self.cli(["session", "expose", self.sid, "T01", "--kind", "review"], now="2026-10-14T09:05+01:00")
        self.assertNotIn("Recheck to place", r.stdout)
        self.assertEqual(len(colds()), 1)
        r = self.cli(["error", "repair", self.sid, "E-ielts-0001"], now="2026-10-15T10:00+01:00")
        self.assertIn("Recheck to place: B-20261017-ielts-1.", r.stdout)
        # T02's window passes unsat: a late recheck in due --list and the brief.
        r = self.cli(["due", self.sid, "--list"], now="2026-10-18T12:00+01:00")
        late = r.stdout.split("0. late rechecks", 1)[1].split("1. 2-day", 1)[0]
        self.assertIn("B-20261016-ielts-1 T02 True, false or not given", late)
        self.assertIn("LATE RECHECK (plan.md §7): B-20261016-ielts-1 T02",
                      self.cli(["brief", self.sid], now="2026-10-18T12:00+01:00").stdout)
        # Sat in its window, it is served and closed.
        items = [make_item(n, "T02", ["%da" % n], origin="cold:T02", layer="reading") for n in (1, 2)]
        key = write_sheet(self.ws, self.sid, "ielts-cold-02", "cold", items, issued="2026-10-17T06:55+01:00")
        self.remember_key(key)
        r = self.grade("ielts-cold-02", {"date": "2026-10-17", "start": "07:00", "stop": "07:05",
                                         "least_sure_line": "none", "asks": [
            {"ask": "%da" % n, "verdict": "right", "check": "filled"} for n in (1, 2)]}, now="2026-10-17T07:10+01:00")
        self.assertIn("2-day recheck done: T02 (B-20261016-ielts-1)", r.stdout)
        self.assert_no_secrets()

    def test_an_on_demand_recheck_again_is_booked_unplaced(self):
        cfg = fio.read_json(self.ws / "indelible.json")
        cfg.setdefault("time", {})["schedule"] = "on_demand"
        fio.write_json(self.ws / "indelible.json", cfg)
        add_exposure(self.ws, self.sid, "T02", "2026-10-12T07:50+01:00")
        items = [make_item(n, "T02", ["%da" % n], origin="cold:T02", layer="reading") for n in (1, 2)]
        key = write_sheet(self.ws, self.sid, "ielts-cold-01", "cold", items)
        self.remember_key(key)
        self.grade("ielts-cold-01", {"date": "2026-10-14", "start": "08:00", "stop": "08:08", "least_sure_line": "none", "asks": [
            {"ask": "1a", "verdict": "right", "check": "filled"},
            {"ask": "2a", "verdict": "wrong", "check": "filled", "mode": "C", "kind": "slip",
             "account": "copied the wrong letter", "belief": "copied the wrong letter into the box"}]})
        r = self.cli(["session", "expose", self.sid, "T02", "--kind", "review"], now="2026-10-14T09:00+01:00")
        self.assertIn("Recheck booked as B-20261016-ielts-1 (unplaced; on-demand learner: leave it unplaced and "
                      "name the window in the close message).", r.stdout)
        self.assert_no_secrets()

    def test_drills_on_a_topic_left_below_3_book_its_recheck_again(self):
        add_exposure(self.ws, self.sid, "T02", "2026-10-12T07:50+01:00")
        items = [make_item(n, "T02", ["%da" % n], origin="cold:T02", layer="reading") for n in (1, 2)]
        key = write_sheet(self.ws, self.sid, "ielts-cold-01", "cold", items)
        self.remember_key(key)
        self.grade("ielts-cold-01", {"date": "2026-10-14", "start": "08:00", "stop": "08:08", "least_sure_line": "none", "asks": [
            {"ask": "1a", "verdict": "right", "check": "filled"},
            {"ask": "2a", "verdict": "wrong", "check": "filled", "mode": "C", "kind": "slip",
             "account": "copied the wrong letter", "belief": "copied the wrong letter into the box"}]})
        items = [make_item(n, "T02", ["%da" % n], layer="reading") for n in (1, 2)]
        key = write_sheet(self.ws, self.sid, "ielts-drills-05", "drills", items, issued="2026-10-15T06:55+01:00")
        self.remember_key(key)
        r = self.grade("ielts-drills-05", {"date": "2026-10-15", "start": "07:00", "stop": "07:10",
                                           "least_sure_line": "none", "asks": [
            {"ask": "%da" % n, "verdict": "right", "check": "filled"} for n in (1, 2)]}, now="2026-10-15T07:20+01:00")
        self.assertIn("Recheck to place: B-20261017-ielts-1.", r.stdout)
        blocks = [b for b in read_rows(self.ws / "plan" / "blocks.jsonl") if b["kind"] == "cold"]
        self.assertEqual([(b["content"], b["window"]["from"]) for b in blocks], [("cold:T02", "2026-10-17T03:10+01:00")])
        self.assert_no_secrets()

    def test_a_topic_at_3_comes_back_for_level_4_then_for_upkeep(self):
        add_exposure(self.ws, self.sid, "T01", "2026-10-12T07:40+01:00")
        items = [make_item(n, "T01", ["%da" % n], origin="cold:T01", layer="reading") for n in (1, 2)]
        key = write_sheet(self.ws, self.sid, "ielts-cold-01", "cold", items)
        self.remember_key(key)
        r = self.grade("ielts-cold-01", {"date": "2026-10-14", "start": "08:00", "stop": "08:05", "least_sure_line": "none", "asks": [
            {"ask": "%da" % n, "verdict": "right", "check": "filled"} for n in (1, 2)]})
        self.assertIn("Levels: T01 0 → 3", r.stdout)
        r = self.cli(["due", self.sid, "--list"], now="2026-10-21T07:00+01:00")    # 6 days 23 h: not yet
        self.assertIn("none", r.stdout.split("6. ", 1)[1].split("7. ", 1)[0])
        r = self.cli(["due", self.sid, "--list"], now="2026-10-21T09:00+01:00")
        self.assertIn("T01 Matching headings · first pass Wed 14 Oct 08:00 (7 days ago)",
                      r.stdout.split("6. ", 1)[1].split("7. ", 1)[0])
        self.assertNotIn("T01", r.stdout.split("1. 2-day rechecks", 1)[1].split("2. ", 1)[0])
        key = write_sheet(self.ws, self.sid, "ielts-cold-02", "cold", items, issued="2026-10-21T09:00+01:00")
        self.remember_key(key)
        r = self.grade("ielts-cold-02", {"date": "2026-10-21", "start": "09:05", "stop": "09:10", "least_sure_line": "none", "asks": [
            {"ask": "%da" % n, "verdict": "right", "check": "filled"} for n in (1, 2)]}, now="2026-10-21T09:15+01:00")
        self.assertIn("Levels: T01 3 → 4", r.stdout)
        r = self.cli(["due", self.sid, "--list"], now="2026-11-11T10:00+00:00")
        upkeep = r.stdout.split("7. ", 1)[1].split("8. ", 1)[0]
        self.assertIn("T01 Matching headings · level 4 · last pass Wed 21 Oct ", upkeep)
        self.assertIn("(21 days ago)", upkeep)
        if HAS_TZDB:  # without one, the fixed-offset fallback shows 08:05 across the October clock change
            self.assertIn("last pass Wed 21 Oct 09:05 (21 days ago)", upkeep)
        self.assert_no_secrets()

    def test_a_words_recheck_still_closes_its_booking(self):
        add_exposure(self.ws, self.sid, "T01", "2026-10-12T07:40+01:00")
        add_blocks(self.ws, [cold_obligation("B-20261014-ielts-2", self.sid, "T01",
                                             "2026-10-14T03:40+01:00", "2026-10-15T07:40+01:00")])
        items = [make_item(n, "T01", ["%da" % n], origin="cold:T01") for n in (1, 2, 3)]
        key = write_sheet(self.ws, self.sid, "ielts-words-01", "words", items)
        self.remember_key(key)
        r = self.grade("ielts-words-01", {"date": "2026-10-14", "start": "08:00", "stop": "08:06", "least_sure_line": "none", "asks": [
            {"ask": "%da" % n, "verdict": "right", "check": "n/a"} for n in (1, 2, 3)]})
        self.assertIn("[measured n=3]", r.stdout)
        self.assertIn("2-day recheck done: T01 (B-20261014-ielts-2)", r.stdout)
        self.assertEqual(self.topics()["T01"]["last_cold"], "2026-10-14T08:00+01:00")
        self.assertEqual(self.topics()["T01"]["last_cold_type"], "words")
        self.assert_no_secrets()

    def test_a_words_recheck_opens_no_recheck_again(self):
        # Words sheets don't feed levels, so a words batch stays below 3 for good: a later warm
        # exposure must not bring it back as a 2-day recheck (its later rungs are placed by hand).
        self.cli(["session", "taught", self.sid, "T01"], now="2026-10-12T07:40+01:00")
        items = [make_item(n, "T01", ["%da" % n], origin="cold:T01", layer="verbal") for n in (1, 2)]
        for it in items:
            for a in it["asks"]:
                a["check"] = False
        key = write_sheet(self.ws, self.sid, "ielts-words-01", "words", items, issued="2026-10-14T07:55+01:00")
        self.remember_key(key)
        r = self.grade("ielts-words-01", {"date": "2026-10-14", "start": "08:00", "stop": "08:05",
                                          "least_sure_line": "none", "asks": [
            {"ask": "%da" % n, "verdict": "right", "check": "n/a"} for n in (1, 2)]}, now="2026-10-14T08:10+01:00")
        self.assertIn("2-day recheck done: T01", r.stdout)
        self.assertEqual(self.topics()["T01"]["level"], 0)
        r = self.cli(["session", "expose", self.sid, "T01", "--kind", "chat"], now="2026-10-15T09:00+01:00")
        self.assertIn("It cannot be on a 2-day recheck before Fri 16 Oct 09:00.", r.stdout)
        self.assertNotIn("now falls between", r.stdout)
        r = self.cli(["due", self.sid, "--list"], now="2026-10-17T07:00+01:00")
        self.assertIn("none", r.stdout.split("1. 2-day rechecks", 1)[1].split("2. ", 1)[0])
        # A cold sheet that serves it later is an ordinary recheck again.
        state = self.topics()
        state["T01"]["last_cold_type"] = "cold"
        fio.write_json(self.sdir / "data" / "topics.json", state)
        r = self.cli(["due", self.sid, "--list"], now="2026-10-17T07:00+01:00")
        self.assertIn("T01 Matching headings · 46 h since last seen",
                      r.stdout.split("1. 2-day rechecks", 1)[1].split("2. ", 1)[0])
        self.assert_no_secrets()

    def test_a_late_recheck_probe_closes_the_expired_booking(self):
        # plan.md section 7: the window passed, so the late recheck is a probe on the same
        # topic, issued on the expired block. Grading it closes that block.
        add_exposure(self.ws, self.sid, "T01", "2026-10-12T07:40+01:00")
        add_blocks(self.ws, [cold_obligation("B-20261014-ielts-2", self.sid, "T01",
                                             "2026-10-14T03:40+01:00", "2026-10-15T07:40+01:00")])
        items = [make_item(n, "T01", ["%da" % n], origin="cold:T01") for n in (1, 2, 3)]
        key = write_sheet(self.ws, self.sid, "ielts-probe-01", "probe", items, block="B-20261014-ielts-2")
        self.remember_key(key)
        r = self.grade("ielts-probe-01", {"date": "2026-10-16", "start": "08:00", "stop": "08:06", "least_sure_line": "none", "asks": [
            {"ask": "%da" % n, "verdict": "right", "check": "n/a"} for n in (1, 2, 3)]},
            now="2026-10-16T09:00+01:00")
        self.assertIn("[measured n=3]", r.stdout)
        self.assertIn("2-day recheck done: T01 (B-20261014-ielts-2)", r.stdout)
        self.assertNotIn("is practice", r.stdout)
        blocks = dict((b["id"], b) for b in read_rows(self.ws / "plan" / "blocks.jsonl"))
        self.assertEqual(blocks["B-20261014-ielts-2"]["status"], "done")
        self.assertEqual(self.topics()["T01"]["last_cold"], "2026-10-16T08:00+01:00")
        self.assertEqual(self.exposures()[1:], [])   # a measuring sheet logs no exposure
        self.assert_no_secrets()

    def test_a_question_can_carry_its_own_topic(self):
        items = [make_item(1, "T01", ["1a", "1b"], layer="reading")]
        items[0]["asks"][1]["topic"] = "T02"
        key = write_sheet(self.ws, self.sid, "ielts-drills-09", "drills", items)
        self.remember_key(key)
        self.grade("ielts-drills-09", {"date": "2026-10-14", "start": "07:00", "stop": "07:10", "least_sure_line": "none", "asks": [
            {"ask": "1a", "verdict": "right", "check": "filled"},
            {"ask": "1b", "verdict": "right", "check": "filled"}]})
        by_ask = dict((a["ask"], a["topic"]) for a in self.attempts())
        self.assertEqual(by_ask, {"1a": "T01", "1b": "T02"})
        self.assert_no_secrets()

    @unittest.skipUnless(HAS_TZDB, "no tz database")
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
