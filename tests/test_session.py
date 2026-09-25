"""Session commands: open, status, expose, taught, override and the close checklist (C1-C8)."""

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
from lib import learning

NOW = "2026-10-12T09:00+01:00"          # a Monday, persona A (Europe/Lisbon, +01:00)
ANY_ID = re.compile(r"\b[EBSL]-(?:\d|[a-z]+-\d)")


class SessionBase(unittest.TestCase):
    persona = "A"

    def setUp(self):
        self._old_now = os.environ.get("INDELIBLE_NOW")
        os.environ["INDELIBLE_NOW"] = NOW
        self.tmp = Path(tempfile.mkdtemp(prefix="indelible-session-"))
        self.ws = make_ws(self.tmp, self.persona)
        self.s = self.ws / "ielts"

    def tearDown(self):
        if self._old_now is None:
            os.environ.pop("INDELIBLE_NOW", None)
        else:
            os.environ["INDELIBLE_NOW"] = self._old_now
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    # ---- helpers -------------------------------------------------------------
    def ind(self, *args, **kw):
        return run(list(args), ws=self.ws, now=kw.get("now", NOW), stdin=kw.get("stdin"))

    def jsonl(self, rel):
        return fio.read_jsonl(self.ws / rel)

    def put(self, rel, rows):
        fio.write_jsonl(self.ws / rel, rows)

    def add(self, rel, row):
        fio.append_jsonl(self.ws / rel, row)

    def sheet(self, sid, type_="drills", status="graded", sat_date="2026-10-12", evidence=True, block=None):
        measures = type_ in ("cold", "diagnostic", "mock", "checkpoint", "probe", "words")
        return {"v": 1, "id": sid, "subject": "ielts", "type": type_, "measures": measures, "topics": ["T04"],
                "asks": 4, "est_min": 10, "status": status, "created": "2026-10-11T19:00+01:00", "lint": "PASS",
                "files": [], "key_sha": "0" * 64, "issued_at": "2026-10-11T19:10+01:00",
                "sat": {"start": "09:05", "stop": "09:15", "date": sat_date},
                "evidence": [{"kind": "photo", "path": "scans/x.jpg"}] if evidence else [],
                "graded_at": None, "opens_unsat": 0, "block": block}

    def attempt(self, sheet, ask, verdict, at="2026-10-12T09:20+01:00", topic="T04"):
        return {"v": 1, "sheet": sheet, "item": int(ask[0]), "ask": ask, "topic": topic, "layer": "verbal",
                "instrument": "practice", "cold": False, "interval_h": None, "verdict": verdict,
                "score": {"right": 1, "half": 0.5}.get(verdict, 0), "check": "filled", "least_sure": False,
                "at": at, "prov": "practice"}

    def error(self, eid, opened="2026-10-12", kind="belief", status="untreated", account="read it too fast",
              mode="R", next_due=None, topic="T04"):
        return {"v": 1, "id": eid, "opened": opened, "sheet": "ielts-cold-01", "item": 1, "topic": topic,
                "kind": kind, "mode": mode, "belief": "reads 'albeit' as 'because'", "account": account,
                "named_least_sure": False, "status": status, "repair_at": None, "rung": 0, "next_due": next_due,
                "passes": [], "fails": [], "answer_ref": None, "prov": "measured"}

    def block(self, bid, start, end, kind="teach", content="new skill", status="planned"):
        return {"v": 1, "id": bid, "subject": "ielts", "kind": kind, "start": start, "end": end, "window": None,
                "protected": True, "measurement": False, "soft": False, "pair": None, "content": content,
                "status": status, "cal": None, "moved_from": None, "miss_reason": None}

    def open_session(self, planned=60, now=NOW, *extra):
        r = self.ind("session", "open", "ielts", "--planned", str(planned), *extra, now=now)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def lock(self):
        p = self.s / ".indelible" / "session.lock"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def close(self, *extra, **kw):
        return self.ind("session", "close", "ielts", *extra, now=kw.get("now", "2026-10-12T09:56+01:00"))


class OpenStatusTests(SessionBase):
    def test_open_writes_the_lock_and_prints_the_budget(self):
        r = self.open_session(60)
        lock = self.lock()
        self.assertEqual(lock["session_id"], "S-ielts-0001")
        self.assertEqual(lock["start"], "2026-10-12T09:00+01:00")
        self.assertEqual(lock["planned_min"], 60)
        self.assertEqual(lock["planned_end"], "2026-10-12T10:00+01:00")
        self.assertEqual(lock["close_start"], "2026-10-12T09:55+01:00")
        self.assertEqual(lock["kind"], "teach")
        self.assertIsNone(lock["block"])
        self.assertIn("31 questions", r.stdout)          # 60 min of reading (contract formula)
        self.assertIn("close starts 09:55", r.stdout)
        self.assertIn("Breaks: none", r.stdout)

        r = self.ind("session", "open", "ielts", "--planned", "60", now="2026-10-12T09:10+01:00")
        self.assertEqual(r.returncode, 1)
        self.assertIn("already open", r.stdout)
        self.assertEqual(self.lock()["start"], "2026-10-12T09:00+01:00")

        r = self.ind("session", "open", "ielts", "--planned", "0")
        self.assertEqual(r.returncode, 2)

    def test_long_session_prints_break_times(self):
        r = self.open_session(150)
        budget = learning.session_budget(150, "reading")
        self.assertIn("%d questions" % budget["asks_budget"], r.stdout)
        self.assertIn("Breaks: 10 min at 10:15", r.stdout)
        self.assertIn("close starts 11:22", r.stdout)

    def test_open_with_a_block_takes_its_kind(self):
        self.put("plan/blocks.jsonl", [self.block("B-20261012-ielts-1", "2026-10-12T09:00+01:00",
                                                  "2026-10-12T10:00+01:00", kind="review")])
        r = self.ind("session", "open", "ielts", "--planned", "60", "--block", "B-20261012-ielts-9")
        self.assertEqual(r.returncode, 2)
        self.assertIsNone(self.lock())
        self.open_session(60, NOW, "--block", "B-20261012-ielts-1")
        self.assertEqual(self.lock()["block"], "B-20261012-ielts-1")
        self.assertEqual(self.lock()["kind"], "review")

    def test_status_line(self):
        r = self.ind("session", "status", "ielts")
        self.assertIn("no session open", r.stdout)
        self.open_session(60)
        self.put("ielts/data/attempts.jsonl", [self.attempt("ielts-drills-01", "1a", "right"),
                                               self.attempt("ielts-drills-01", "2a", "wrong"),
                                               self.attempt("ielts-drills-00", "1a", "right",
                                                            at="2026-10-11T19:00+01:00")])
        r = self.ind("session", "status", "ielts", now="2026-10-12T09:47+01:00")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "[indelible] 47/60 min · close starts 09:55 · questions so far 2")
        self.assertIsNone(ANY_ID.search(r.stdout))
        r = self.ind("session", "status", "ielts", now="2026-10-12T09:56+01:00")
        self.assertIn("closing time", r.stdout)
        r = self.ind("session", "status", "ielts", now="2026-10-12T12:30+01:00")
        self.assertIn("not closed", r.stdout)

    def test_open_refuses_over_an_unclosed_lock(self):
        self.open_session(60)
        r = self.ind("session", "open", "ielts", "--planned", "60", now="2026-10-12T13:00+01:00")
        self.assertEqual(r.returncode, 1)
        self.assertIn("never closed", r.stdout)
        self.assertIn("session close ielts", r.stdout)

    def test_another_subject_needs_park_other(self):
        r = self.ind("subject", "add", "stats", "--title", "Statistics final", "--profile", "course")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.open_session(60)
        r = self.ind("session", "open", "stats", "--planned", "30", now="2026-10-12T09:20+01:00")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Another subject has a session open", r.stdout)
        self.assertIn("--park-other", r.stdout)
        self.assertFalse((self.ws / "stats" / ".indelible" / "session.lock").exists())
        self.assertFalse((self.s / ".indelible" / "unclosed").exists())

        r = self.ind("session", "open", "stats", "--planned", "30", "--park-other", now="2026-10-12T09:20+01:00")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Parked: IELTS Academic", r.stdout)
        self.assertTrue((self.s / ".indelible" / "unclosed").exists())
        self.assertTrue((self.ws / "stats" / ".indelible" / "session.lock").exists())

        r = self.ind("brief", "ielts", now="2026-10-12T09:25+01:00")
        self.assertIn("unclosed session", r.stdout)
        # the parked session closes late, with its own mistake logged
        r = self.close(now="2026-10-12T09:30+01:00")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        row = self.jsonl("ielts/data/sessions.jsonl")[-1]
        self.assertEqual(row["closed"]["status"], "late")
        self.assertFalse((self.s / ".indelible" / "unclosed").exists())
        self.assertIn("late_close", [x.get("category") for x in self.jsonl("ledger.jsonl")])


class ExposeTaughtOverrideTests(SessionBase):
    def test_expose_appends_an_exposure(self):
        r = self.ind("session", "expose", "ielts", "T04", now="2026-10-12T09:25+01:00")
        self.assertEqual(r.returncode, 0, r.stderr)
        x = self.jsonl("ielts/data/exposures.jsonl")[-1]
        self.assertEqual(x, {"v": 1, "topic": "T04", "at": "2026-10-12T09:25+01:00", "kind": "chat"})
        r = self.ind("session", "expose", "ielts", "T04", "--kind", "repair")
        self.assertEqual(self.jsonl("ielts/data/exposures.jsonl")[-1]["kind"], "repair")
        r = self.ind("session", "expose", "ielts", "T99")
        self.assertEqual(r.returncode, 2)

    def test_expose_warns_about_a_recheck_within_24_h(self):
        self.put("plan/blocks.jsonl", [self.block("B-20261013-ielts-1", "2026-10-13T07:00+01:00",
                                                  "2026-10-13T07:15+01:00", kind="cold", content="cold:T04")])
        r = self.ind("session", "expose", "ielts", "T04")
        self.assertIn("WARN", r.stdout)

    def test_taught_books_one_cold_obligation_with_its_window(self):
        self.put("plan/blocks.jsonl", [self.block("B-20261012-ielts-1", "2026-10-12T09:00+01:00",
                                                  "2026-10-12T10:00+01:00")])
        self.open_session(60, NOW, "--block", "B-20261012-ielts-1")
        r = self.ind("session", "taught", "ielts", "T04", now="2026-10-12T09:20+01:00")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Wed 14 Oct 05:20", r.stdout)
        self.assertIn("Thu 15 Oct 09:20", r.stdout)
        blocks = self.jsonl("plan/blocks.jsonl")
        obl = [b for b in blocks if b["kind"] == "cold"]
        self.assertEqual(len(obl), 1)
        o = obl[0]
        self.assertIsNone(o["start"])
        self.assertEqual(o["window"], {"from": "2026-10-14T05:20+01:00", "to": "2026-10-15T09:20+01:00"})
        self.assertEqual(o["content"], "cold:T04")
        self.assertTrue(o["protected"])
        self.assertEqual(o["pair"], "B-20261012-ielts-1")
        self.assertEqual(o["status"], "planned")
        self.assertRegex(o["id"], r"^B-20261014-ielts-\d+$")
        x = self.jsonl("ielts/data/exposures.jsonl")[-1]
        self.assertEqual((x["topic"], x["kind"]), ("T04", "teach"))
        topics = json.loads((self.s / "data" / "topics.json").read_text(encoding="utf-8"))
        self.assertEqual(topics["T04"]["taught_at"], "2026-10-12T09:20+01:00")
        self.assertEqual(topics["T04"]["taught_by"], "sheet")

        # taught again: no second obligation; the window follows the last teaching
        r = self.ind("session", "taught", "ielts", "T04", "--by", "chat", now="2026-10-12T09:40+01:00")
        self.assertEqual(r.returncode, 0, r.stderr)
        obl = [b for b in self.jsonl("plan/blocks.jsonl") if b["kind"] == "cold"]
        self.assertEqual(len(obl), 1)
        self.assertEqual(obl[0]["window"]["from"], "2026-10-14T05:40+01:00")

    def test_override_is_logged_with_its_prediction(self):
        self.open_session(60)
        r = self.ind("session", "override", "ielts", "I know headings, skip the theory",
                     "--predict", "items 1 to 4 right")
        self.assertEqual(r.returncode, 0, r.stderr)
        row = self.jsonl("ledger.jsonl")[-1]
        self.assertEqual((row["kind"], row["id"], row["subject"]), ("override", "L-0001", "ielts"))
        self.assertEqual(row["said"], "I know headings, skip the theory")
        self.assertEqual(row["predict"], "items 1 to 4 right")
        self.assertIsNone(row["scored"])
        self.assertEqual(row["session"], "S-ielts-0001")
        r = self.ind("session", "override", "ielts", "x", "--predict", " ")
        self.assertEqual(r.returncode, 2)


class CloseTests(SessionBase):
    def test_pass_appends_the_session_row_and_removes_the_lock(self):
        self.put("plan/blocks.jsonl", [
            self.block("B-20261012-ielts-1", "2026-10-12T09:00+01:00", "2026-10-12T10:00+01:00"),
            self.block("B-20261015-ielts-1", "2026-10-15T07:00+01:00", "2026-10-15T08:00+01:00")])
        self.open_session(60, NOW, "--block", "B-20261012-ielts-1")
        self.put("ielts/data/sheets.jsonl", [self.sheet("ielts-drills-01", block="B-20261012-ielts-1"),
                                             self.sheet("ielts-cold-02", type_="cold", status="issued",
                                                        sat_date=None, evidence=False, block="B-20261015-ielts-1")])
        self.put("ielts/data/attempts.jsonl", [self.attempt("ielts-drills-01", "1a", "right"),
                                               self.attempt("ielts-drills-01", "2a", "right"),
                                               self.attempt("ielts-drills-01", "3a", "right"),
                                               self.attempt("ielts-drills-01", "4a", "wrong")])
        r = self.close("--note", "drills A done; recheck ready")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for code in ("C1", "C2", "C3", "C4", "C5", "C6", "C7"):
            self.assertIn("PASS %s" % code, r.stdout)
        self.assertIn("INFO C8", r.stdout)
        self.assertIn("1 sheet ready", r.stdout)
        self.assertIn("Saved:", r.stdout)
        self.assertIn("4 questions graded: 3 right, 1 wrong", r.stdout)
        self.assertIn("Next: Thu 15 Oct 07:00 · new skill", r.stdout)
        learner_lines = [l for l in r.stdout.splitlines() if l.startswith(("Saved:", "Next:", "To do:"))]
        for l in learner_lines:
            self.assertIsNone(ANY_ID.search(l), l)

        self.assertIsNone(self.lock())
        rows = self.jsonl("ielts/data/sessions.jsonl")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["id"], "S-ielts-0001")
        self.assertEqual(row["block"], "B-20261012-ielts-1")
        self.assertEqual(row["planned"], {"start": "2026-10-12T09:00+01:00", "min": 60})
        self.assertEqual(row["actual"], {"start": "2026-10-12T09:00+01:00", "end": "2026-10-12T09:56+01:00",
                                         "elapsed_min": 56})
        self.assertEqual(row["asks"], {"n": 4, "right": 3, "half": 0, "wrong": 1, "dont_know": 0, "skip": 0})
        self.assertEqual(row["sheets"], ["ielts-drills-01"])
        self.assertEqual(row["overrun_min"], 0)
        self.assertEqual(row["note"], "drills A done; recheck ready")
        self.assertEqual(row["closed"], {"at": "2026-10-12T09:56+01:00", "status": "same-day"})
        blocks = {b["id"]: b for b in self.jsonl("plan/blocks.jsonl")}
        self.assertEqual(blocks["B-20261012-ielts-1"]["status"], "done")
        self.assertEqual(blocks["B-20261015-ielts-1"]["status"], "planned")
        log = (self.s / "views" / "log.md").read_text(encoding="utf-8")
        self.assertIn("drills A done", log)

        # nothing left to close
        r = self.close()
        self.assertEqual(r.returncode, 1)
        self.assertIn("nothing to close", r.stdout)

    def test_overrun_is_recorded(self):
        self.open_session(60)
        r = self.close(now="2026-10-12T10:12+01:00")
        self.assertEqual(r.returncode, 0, r.stdout)
        row = self.jsonl("ielts/data/sessions.jsonl")[-1]
        self.assertEqual((row["actual"]["elapsed_min"], row["overrun_min"]), (72, 12))

    def test_fail_on_missing_evidence_keeps_the_lock(self):
        self.open_session(60)
        self.put("ielts/data/sheets.jsonl", [self.sheet("ielts-cold-01", type_="cold", status="sat", evidence=False)])
        r = self.close()
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL C1 evidence", r.stdout)
        self.assertIn("ielts-cold-01", r.stdout)
        self.assertIn("Not closed", r.stdout)
        self.assertIsNotNone(self.lock())
        self.assertEqual(self.jsonl("ielts/data/sessions.jsonl"), [])

    def test_fail_on_an_ungraded_cold_sheet(self):
        self.open_session(60)
        self.put("ielts/data/sheets.jsonl", [
            self.sheet("ielts-cold-01", type_="cold", status="sat"),
            self.sheet("ielts-drills-02", type_="drills", status="sat"),
            self.sheet("ielts-drills-03", type_="drills", status="sat")])
        self.ind("ledger", "add", "owed", "--subject", "ielts", "--what", "grade ielts-drills-02 and ielts-cold-01",
                 "--due", "2026-10-12T21:00+01:00", "--by", "claude")
        r = self.close()
        self.assertEqual(r.returncode, 1)
        line = [l for l in r.stdout.splitlines() if l.startswith("FAIL C2")][0]
        self.assertIn("ielts-cold-01 (measuring", line)       # a to-do never excuses a measuring sheet
        self.assertIn("ielts-drills-03", line)                # practice sheet without a to-do
        self.assertNotIn("ielts-drills-02", line)             # practice sheet carried by a to-do within 24 h
        self.assertIsNotNone(self.lock())

    def test_fail_on_an_error_without_an_account(self):
        self.open_session(60)
        self.put("ielts/data/errors.jsonl", [
            self.error("E-ielts-0001", account=""),
            self.error("E-ielts-0002", account="no account"),
            self.error("E-ielts-0003", kind="slip", status="spacing", next_due=None, mode=""),
            self.error("E-ielts-0004", opened="2026-10-01", account="")])
        r = self.close()
        self.assertEqual(r.returncode, 1)
        line = [l for l in r.stdout.splitlines() if l.startswith("FAIL C3")][0]
        self.assertIn("E-ielts-0001 missing account", line)
        self.assertIn("E-ielts-0003 missing mode", line)
        self.assertIn("due date", line)
        self.assertNotIn("E-ielts-0002", line)                # the literal "no account" is an answer
        self.assertNotIn("E-ielts-0004", line)                # opened before this session

    def test_fail_on_a_taught_topic_without_its_recheck(self):
        self.open_session(60)
        self.add("ielts/data/exposures.jsonl", {"v": 1, "topic": "T04", "at": "2026-10-12T09:20+01:00",
                                                "kind": "teach"})
        r = self.close()
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL C4 cold booked", r.stdout)
        self.assertIn("session taught ielts T04", r.stdout)
        r = self.ind("session", "taught", "ielts", "T04", now="2026-10-12T09:30+01:00")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.close()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("PASS C4 cold booked: 2-day recheck booked for T04", r.stdout)

    def test_a_placed_cold_block_inside_the_window_satisfies_c4(self):
        self.open_session(60)
        self.add("ielts/data/exposures.jsonl", {"v": 1, "topic": "T04", "at": "2026-10-12T09:20+01:00",
                                                "kind": "teach"})
        self.put("plan/blocks.jsonl", [self.block("B-20261014-ielts-1", "2026-10-14T07:00+01:00",
                                                  "2026-10-14T07:15+01:00", kind="cold", content="cold:T04")])
        self.assertEqual(self.close().returncode, 0)

    def test_fail_when_a_recheck_soon_includes_an_unfixed_mistake(self):
        self.open_session(60)
        self.put("ielts/data/errors.jsonl", [self.error("E-ielts-0001", opened="2026-10-09")])
        self.put("plan/blocks.jsonl", [self.block("B-20261012-ielts-2", "2026-10-12T19:00+01:00",
                                                  "2026-10-12T19:15+01:00", kind="cold", content="cold:T01,T04")])
        r = self.close()
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL C5", r.stdout)
        self.assertIn("E-ielts-0001", r.stdout)
        # a recheck more than 12 h away is not flagged
        self.put("plan/blocks.jsonl", [self.block("B-20261013-ielts-1", "2026-10-13T08:00+01:00",
                                                  "2026-10-13T08:15+01:00", kind="cold", content="cold:T04")])
        self.assertEqual(self.close().returncode, 0)

    def test_fail_on_a_promise_without_a_to_do(self):
        self.open_session(60)
        r = self.close("--note", "block B moves to tomorrow")
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL C6 promises", r.stdout)
        # a note appended today counts too, in any language the rule knows
        r = self.close("--note", "block B cut")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.open_session(60, "2026-10-12T17:00+01:00")
        self.ind("note", "append", "ielts", "session", stdin="Acabo o bloco B amanhã.", now="2026-10-12T17:10+01:00")
        r = self.close("--note", "short one", now="2026-10-12T17:50+01:00")
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL C6", r.stdout)
        self.ind("ledger", "add", "owed", "--subject", "ielts", "--what", "Finish block B",
                 "--due", "2026-10-13T07:30+01:00", now="2026-10-12T17:51+01:00")
        r = self.close("--note", "short one", now="2026-10-12T17:52+01:00")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("PASS C6", r.stdout)

    def test_defer_turns_failures_into_to_dos(self):
        self.open_session(60)
        self.put("ielts/data/sheets.jsonl", [self.sheet("ielts-drills-04", status="sat", evidence=False)])
        r = self.close("--note", "left early, rest later", "--defer", "learner had to leave",
                       now="2026-10-12T09:40+01:00")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("FAIL C1", r.stdout)
        self.assertIn("FAIL C2", r.stdout)
        self.assertIn("FAIL C6", r.stdout)
        self.assertIn("closed with 3 to-dos", r.stdout)
        self.assertIn("Logged as my mistake: a promise without a date", r.stdout)
        ledger = self.jsonl("ledger.jsonl")
        owed = [x for x in ledger if x["kind"] == "owed"]
        self.assertEqual(len(owed), 3)
        for o in owed:
            self.assertEqual(o["due"], "2026-10-13T09:40+01:00")
            self.assertEqual(o["subject"], "ielts")
            self.assertEqual(o["why"], "learner had to leave")
        self.assertEqual([o["by"] for o in owed], ["learner", "claude", "claude"])
        self.assertIn("ielts-drills-04", owed[0]["what"])
        defects = [x for x in ledger if x["kind"] == "defect"]
        self.assertEqual([(d["category"], d["fix_type"]) for d in defects], [("promise_broken", "rule")])
        row = self.jsonl("ielts/data/sessions.jsonl")[-1]
        self.assertEqual(row["closed"]["status"], "with-todos")
        self.assertEqual(row["todos"], [o["id"] for o in owed])
        self.assertIsNone(self.lock())
        for l in r.stdout.splitlines():
            if l.startswith(("Saved:", "To do:", "Next:", "Logged")):
                self.assertIsNone(ANY_ID.search(l), l)
        # the to-do naming the practice sheet now carries C2 at the next close
        self.open_session(30, "2026-10-12T18:00+01:00")
        self.put("ielts/data/sheets.jsonl", [self.sheet("ielts-drills-04", status="sat")])
        r = self.close(now="2026-10-12T18:25+01:00")
        self.assertIn("PASS C2 graded: all graded; to-do within 24 h for ielts-drills-04", r.stdout)

    def test_late_close_logs_its_own_mistake(self):
        self.open_session(60, "2026-10-12T06:00+01:00")
        self.put("ielts/data/attempts.jsonl", [self.attempt("ielts-drills-01", "1a", "right",
                                                            at="2026-10-12T06:40+01:00")])
        r = self.close(now="2026-10-12T09:30+01:00")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("closed late", r.stdout)
        row = self.jsonl("ielts/data/sessions.jsonl")[-1]
        self.assertEqual(row["closed"]["status"], "late")
        self.assertEqual(row["actual"]["end"], "2026-10-12T06:40+01:00")
        self.assertEqual(row["actual"]["time_source"], "last_activity")
        self.assertEqual(row["actual"]["elapsed_min"], 40)
        d = [x for x in self.jsonl("ledger.jsonl") if x["kind"] == "defect"]
        self.assertEqual([(x["category"], x["fix_type"]) for x in d], [("late_close", "rule")])
        # a second late close cannot be fixed by a rule again
        self.open_session(30, "2026-10-12T12:00+01:00")
        self.assertEqual(self.close(now="2026-10-12T15:00+01:00").returncode, 0)
        d = [x for x in self.jsonl("ledger.jsonl") if x["kind"] == "defect"]
        self.assertEqual([x["fix_type"] for x in d], ["rule", "planner"])
        self.assertEqual(self.jsonl("ielts/data/sessions.jsonl")[-1]["actual"]["time_source"], "planned")

    def test_hand_edited_view_fails_c7_and_defer_keeps_the_edit(self):
        self.open_session(60)
        view = self.s / "views" / "progress.md"
        self.assertTrue(view.exists())
        view.write_text(view.read_text(encoding="utf-8") + "\nmy own line\n", encoding="utf-8")
        r = self.close()
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL C7 views", r.stdout)
        self.assertIn("ielts/views/progress.md", r.stdout)
        r = self.close("--defer", "ask the learner about their edit")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("my own line", view.read_text(encoding="utf-8"))
        owed = [x for x in self.jsonl("ledger.jsonl") if x["kind"] == "owed"]
        self.assertEqual(len(owed), 1)
        self.assertIn("views", owed[0]["what"])
        self.assertIn("left as they are", r.stdout)

    def test_note_is_capped(self):
        self.open_session(60)
        r = self.close("--note", "x" * 121)
        self.assertEqual(r.returncode, 2)
        self.assertIsNotNone(self.lock())


if __name__ == "__main__":
    unittest.main()
