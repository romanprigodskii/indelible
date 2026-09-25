"""Brief, due and render (views, views/week.md, generated CLAUDE.md sections)."""

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

from lib import dates
from lib import io as fio
from lib import ws as wsmod

NOW = "2026-10-12T09:00+01:00"          # a Monday, persona A (Europe/Lisbon, +01:00)
SEP = "-- for Claude, do not read aloud --"
ANY_ID = re.compile(r"\b[EBSL]-(?:\d|[a-z]+-\d)")


class BriefBase(unittest.TestCase):
    persona = "A"

    def setUp(self):
        self._old_now = os.environ.get("INDELIBLE_NOW")
        os.environ["INDELIBLE_NOW"] = NOW
        self.tmp = Path(tempfile.mkdtemp(prefix="indelible-brief-"))
        self.ws = make_ws(self.tmp, self.persona)
        self.sid = {"A": "ielts", "B": "spanish", "C": "stats", "D": "rust"}[self.persona]
        self.s = self.ws / self.sid

    def tearDown(self):
        if self._old_now is None:
            os.environ.pop("INDELIBLE_NOW", None)
        else:
            os.environ["INDELIBLE_NOW"] = self._old_now
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def ind(self, *args, **kw):
        return run(list(args), ws=self.ws, now=kw.get("now", NOW), stdin=kw.get("stdin"))

    def brief(self, now=NOW, *extra):
        r = self.ind("brief", self.sid, *extra, now=now)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def parts(self, text):
        self.assertIn(SEP, text)
        learner, claude = text.split(SEP, 1)
        return learner, claude

    def jsonl(self, rel):
        return fio.read_jsonl(self.ws / rel)

    def put(self, rel, rows):
        fio.write_jsonl(self.ws / rel, rows)

    def set_cfg(self, dotted, value):
        cfg = fio.read_json(self.ws / "indelible.json")
        node = cfg
        keys = dotted.split(".")
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = value
        fio.write_json(self.ws / "indelible.json", cfg)

    def error(self, n, kind="belief", status="spacing", next_due="2026-10-10", topic="T04", belief=None,
              named=False):
        return {"v": 1, "id": "E-%s-%04d" % (self.sid, n), "opened": "2026-10-01", "sheet": "ielts-cold-01",
                "item": 1, "topic": topic, "kind": kind, "mode": "V",
                "belief": belief or ("confuses the paraphrase in item %d with a near synonym" % n),
                "account": "I read it too fast", "named_least_sure": named, "status": status,
                "repair_at": None, "rung": 1, "next_due": next_due if status != "untreated" else None,
                "passes": [], "fails": [], "answer_ref": None, "prov": "measured"}

    def block(self, bid, start, end, kind="teach", content="new skill", status="planned", soft=False,
              subject=None):
        return {"v": 1, "id": bid, "subject": subject or self.sid, "kind": kind, "start": start, "end": end,
                "window": None, "protected": True, "measurement": False, "soft": soft, "pair": None,
                "content": content, "status": status, "cal": None, "moved_from": None, "miss_reason": None}

    def sheet(self, sid, status="issued", type_="drills", opens=0):
        return {"v": 1, "id": sid, "subject": self.sid, "type": type_, "measures": type_ == "cold",
                "topics": ["T04"], "asks": 6, "est_min": 10, "status": status, "created": "2026-10-10T19:00+01:00",
                "lint": "PASS", "files": [], "key_sha": "0" * 64, "issued_at": "2026-10-10T19:10+01:00",
                "sat": {"start": None, "stop": None, "date": None}, "evidence": [], "graded_at": None,
                "opens_unsat": opens, "block": None}

    def lock(self, start, planned=60, end=None, sid=None):
        payload = {"v": 1, "session_id": sid or "S-%s-0001" % self.sid, "start": start, "planned_min": planned,
                   "planned_end": end, "close_start": None, "block": None, "kind": "teach"}
        fio.write_json(self.s / ".indelible" / "session.lock", payload)


class BriefTests(BriefBase):
    def test_brief_stays_under_the_cap_with_200_due_errors(self):
        errs = []
        for i in range(1, 201):
            kind = ("belief", "slip", "shaky")[i % 3]
            errs.append(self.error(i, kind=kind, belief="x" * 110))
        for i in range(201, 261):
            errs.append(self.error(i, status="untreated", topic="T02", belief="y" * 110))
        self.put("ielts/data/errors.jsonl", errs)
        for vocab in ("plain", "technical"):
            self.set_cfg("learner.vocab", vocab)
            text = self.brief()
            self.assertLessEqual(len(text.rstrip("\n")), 4500, vocab)
            self.assertIn("more (run: due ielts --list)", text)
            self.assertIn(SEP, text)
            self.assertIn("BELIEFS DUE: E-ielts-0003", text.split(SEP, 1)[1])
        r = self.ind("brief", "ielts", "--json")
        data = json.loads(r.stdout)
        self.assertLessEqual(data["chars"], 4500)
        self.assertEqual(data["subject"], "ielts")
        r = self.ind("due", "ielts")
        self.assertIn("errors due: 66 beliefs repaired, 67 slips, 67 shaky", r.stdout)   # technical vocab
        self.assertIn("untreated beliefs needing repair: 60", r.stdout)

    def test_brief_order_and_plain_vocabulary(self):
        self.put("ielts/data/errors.jsonl", [self.error(1, belief="reads 'albeit' as 'because'"),
                                             self.error(2, kind="slip"), self.error(3, status="untreated")])
        self.put("plan/blocks.jsonl", [
            self.block("B-20261012-ielts-1", "2026-10-12T07:00+01:00", "2026-10-12T08:00+01:00"),
            self.block("B-20261015-ielts-1", "2026-10-15T07:00+01:00", "2026-10-15T08:00+01:00", kind="cold",
                       content="cold:T04")])
        self.put("ielts/data/sessions.jsonl", [{
            "v": 1, "id": "S-ielts-0001", "block": "B-20261009-ielts-1", "kind": "teach",
            "planned": {"start": "2026-10-09T07:00+01:00", "min": 60},
            "actual": {"start": "2026-10-09T07:02+01:00", "end": "2026-10-09T08:00+01:00", "elapsed_min": 58},
            "sheets": [], "asks": {"n": 20, "right": 15, "half": 1, "wrong": 3, "dont_know": 1, "skip": 0},
            "overrun_min": 0, "note": "recheck 11/14; see E-ielts-0003", "closed": {"at": "x", "status": "same-day"}}])
        self.ind("ledger", "add", "owed", "--subject", "ielts", "--what", "Register for the 12 Dec sitting",
                 "--due", "2026-10-13T20:00+01:00")
        self.ind("ledger", "add", "owed", "--subject", "ielts", "--what", "Far away", "--due", "2026-10-30T20:00+01:00")
        self.lock("2026-10-12T05:30+01:00", 60, "2026-10-12T06:30+01:00")   # unclosed: > planned end + 2 h
        text = self.brief()
        learner, claude = self.parts(text)
        lines = learner.strip("\n").split("\n")
        self.assertTrue(lines[0].startswith("IELTS Academic · exam · 2026-12-12 (61 days left)"))
        heads = [l.split(":", 1)[0] for l in lines if not l.startswith("  ")]
        order = ["FLAGS", "NOW/NEXT", "DUE", "TO-DO (next 3 days)", "MASTERY (0–5)", "LAST SESSIONS"]
        found = [h for h in heads if h in order]
        self.assertEqual(found, order)
        self.assertIn("unclosed session (started today 05:30)", learner)
        self.assertIn("missed? today 07:00–08:00 new skill", learner)
        self.assertIn("Register for the 12 Dec sitting (due Tue 13 Oct 20:00)", learner)
        self.assertNotIn("Far away", learner)
        self.assertIn("mistakes due: 1 fixed, 1 slip", learner)
        self.assertIn("mistakes to fix before they come back: 1", learner)
        self.assertIn("next Thu 15 Oct 07:00–08:00 2-day recheck (mixed)", learner)
        self.assertNotIn("T04", learner)                 # never name what is on a recheck
        self.assertNotIn("albeit", learner)
        self.assertIsNone(ANY_ID.search(learner), ANY_ID.search(learner) and ANY_ID.search(learner).group(0))
        # ids and mistake details live below the line
        for ident in ("S-ielts-0001", "L-0001", "E-ielts-0001", "E-ielts-0003"):
            self.assertIn(ident, claude)
        self.assertIn("UNCLOSED:", claude)
        self.assertIn("BELIEFS DUE:", claude)
        self.assertIn("NEEDS REPAIR:", claude)

        self.set_cfg("learner.vocab", "technical")
        learner, _ = self.parts(self.brief())
        self.assertIn("TO-DO (≤3 days): L-0001 Register", learner)
        self.assertIn("unclosed session S-ielts-0001", learner)
        self.assertIn("LEVELS: T01 Matching headings 0", learner)

    def test_unclosed_is_lock_older_than_planned_end_plus_2_h(self):
        self.lock("2026-10-12T05:59+01:00", 60, "2026-10-12T06:59+01:00")
        self.assertIn("unclosed session", self.brief().split(SEP)[0])
        self.lock("2026-10-12T06:30+01:00", 60, "2026-10-12T07:30+01:00")
        learner = self.brief().split(SEP)[0]
        self.assertNotIn("unclosed", learner)
        self.assertIn("session open since 06:30", learner)
        (self.s / ".indelible" / "unclosed").write_text("{}", encoding="utf-8")   # parked
        self.assertIn("unclosed session", self.brief().split(SEP)[0])

    def test_opens_unsat_counts_once_per_open_and_forces_a_decision(self):
        self.put("ielts/data/sheets.jsonl", [self.sheet("ielts-headings-01-drills"),
                                             self.sheet("ielts-cold-01", type_="cold"),
                                             self.sheet("ielts-old-01", status="graded")])

        def opens():
            return {s["id"]: s["opens_unsat"] for s in self.jsonl("ielts/data/sheets.jsonl")}

        self.brief()
        self.assertEqual(opens(), {"ielts-headings-01-drills": 1, "ielts-cold-01": 1, "ielts-old-01": 0})
        self.brief(now="2026-10-12T09:05+01:00")          # the session-open brief right after the setup brief
        self.assertEqual(opens()["ielts-headings-01-drills"], 1)
        text = self.brief(now="2026-10-14T07:00+01:00")    # the next open
        self.assertEqual(opens()["ielts-headings-01-drills"], 2)
        learner, claude = self.parts(text)
        self.assertIn("sheet ielts-headings-01-drills (drills) issued", learner)
        self.assertIn("not taken after 2 opens", learner)
        self.assertIn("a 2-day recheck issued", learner)
        self.assertNotIn("ielts-cold-01", learner)
        self.assertIn("ielts-cold-01", claude)
        # not counted while a session is running
        self.lock("2026-10-16T07:00+01:00", 60, "2026-10-16T08:00+01:00")
        self.brief(now="2026-10-16T07:10+01:00")
        self.assertEqual(opens()["ielts-headings-01-drills"], 2)

    def test_missed_blocks_are_computed_read_only(self):
        rows = [
            self.block("B-20261010-ielts-1", "2026-10-10T10:00+01:00", "2026-10-10T11:00+01:00"),
            self.block("B-20261009-ielts-1", "2026-10-09T07:00+01:00", "2026-10-09T08:00+01:00", soft=True),
            self.block("B-20261008-ielts-1", "2026-10-08T07:00+01:00", "2026-10-08T08:00+01:00"),
            self.block("B-20261007-ielts-1", "2026-10-07T07:00+01:00", "2026-10-07T08:00+01:00", status="done"),
        ]
        self.put("plan/blocks.jsonl", rows)
        self.put("ielts/data/sessions.jsonl", [{
            "v": 1, "id": "S-ielts-0001", "block": None, "kind": "teach",
            "planned": {"start": "2026-10-08T07:05+01:00", "min": 60},
            "actual": {"start": "2026-10-08T07:05+01:00", "end": "2026-10-08T08:01+01:00", "elapsed_min": 56},
            "sheets": [], "asks": {"n": 0}, "overrun_min": 0, "note": "", "closed": {"at": "x", "status": "same-day"}}])
        before = (self.ws / "plan" / "blocks.jsonl").read_bytes()
        learner, claude = self.parts(self.brief())
        flags = [l for l in learner.splitlines() if l.startswith("FLAGS:")][0]
        self.assertEqual(flags, "FLAGS: missed? %s 10 Oct 10:00–11:00 new skill" % dates.WEEKDAYS[5])
        self.assertNotIn("9 Oct", flags)     # soft
        self.assertNotIn("8 Oct", flags)     # a session overlaps it
        self.assertIn("MISSED?: B-20261010-ielts-1", claude)
        self.assertEqual((self.ws / "plan" / "blocks.jsonl").read_bytes(), before)
        week = (self.ws / "views" / "week.md").read_text(encoding="utf-8")
        self.assertNotIn("B-2026", week)

    def test_quarantine_and_safeguard_flags(self):
        path = self.s / "data" / "errors.jsonl"
        path.write_text('{"v": 1, "id": "E-ielts-0001", "status": "spacing"\n', encoding="utf-8")
        self.ind("ledger", "add", "decision", "--subject", "ielts", "--summary", "Timed section moves to 09:00",
                 "--why", "mornings are clearer", "--check-on", "2026-10-11", "--rule", "timed accuracy < 0.70",
                 "--action", "revert")
        learner, claude = self.parts(self.brief())
        self.assertIn("could not be read; kept aside", learner)
        self.assertIn("a check on an earlier decision is due (2026-10-11): Timed section moves to 09:00", learner)
        self.assertIn("SAFEGUARD DUE: L-0001", claude)

    def test_notes_from_the_subject_claude_md(self):
        md = self.s / "CLAUDE.md"
        text = md.read_text(encoding="utf-8")
        text = text.replace("## Learner notes\n", "## Learner notes\n\n- Reads English slowly; gloss in Portuguese.\n"
                            "- Says 'I wrote the essay plan myself; Claude only asked questions.'\n")
        text = text.replace("## Do not calibrate on\n", "## Do not calibrate on\n\n- Practice test 1 (seen before)\n")
        md.write_text(text, encoding="utf-8")
        learner, _ = self.parts(self.brief())
        self.assertIn("NOTES:", learner)
        self.assertIn("[notes] Reads English slowly; gloss in Portuguese.", learner)
        self.assertIn("[do not calibrate on] Practice test 1 (seen before)", learner)
        self.assertNotIn("Learner-owned", learner)      # template placeholders are skipped

    def test_shadow_brief_is_marked_and_writes_nothing(self):
        self.put("ielts/data/sheets.jsonl", [self.sheet("ielts-headings-01-drills")])
        self.set_cfg("subjects", [{"id": "ielts", "dir": "ielts", "state": "shadow", "priority": 1,
                                   "target_weekly_min": 240, "min_weekly_min": None}])
        text = self.brief()
        self.assertTrue(text.startswith("SHADOW (read-only)"))
        self.assertEqual(self.jsonl("ielts/data/sheets.jsonl")[0]["opens_unsat"], 0)
        self.assertEqual(self.ind("session", "open", "ielts", "--planned", "60").returncode, 1)
        self.set_cfg("subjects", [{"id": "ielts", "dir": "ielts", "state": "legacy", "priority": 1,
                                   "target_weekly_min": 240, "min_weekly_min": None}])
        self.assertIn("legacy", self.brief())

    def test_overview_for_several_subjects(self):
        r = self.ind("subject", "add", "stats", "--title", "Statistics final", "--profile", "course")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.ind("brief")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Subjects: ielts, stats", r.stdout)
        self.assertIn("IELTS Academic · exam", r.stdout)
        self.assertIn("Statistics final · course · no date", r.stdout)
        self.assertLessEqual(len(r.stdout.rstrip("\n")), 4500)


class DueTests(BriefBase):
    def test_due_list_tiers(self):
        exposures = [{"v": 1, "topic": "T02", "at": "2026-10-10T08:00+01:00", "kind": "teach"}]
        self.put("ielts/data/exposures.jsonl", exposures)
        self.put("ielts/data/errors.jsonl", [
            self.error(1, kind="slip", next_due="2026-10-05", topic="T01"),
            self.error(2, kind="slip", next_due="2026-10-01", topic="T01", named=True),
            self.error(3, kind="belief", next_due="2026-10-12", topic="T03"),
            self.error(4, kind="shaky", next_due="2026-10-11", topic="T03"),
            self.error(5, kind="belief", status="untreated", topic="T04"),
            self.error(6, kind="slip", next_due="2026-10-20", topic="T01"),       # not due yet
            self.error(7, kind="slip", status="retired", topic="T01"),
        ])
        r = self.ind("due", "ielts", "--list")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        pos = [out.index(x) for x in ("1. 2-day rechecks", "T02 True, false or not given · 49 h",
                                      "2. fixed mistakes due", "E-ielts-0003", "3. shaky answers due",
                                      "E-ielts-0004", "4. oldest due", "E-ielts-0001", "E-ielts-0002",
                                      "5. needs repair", "E-ielts-0005")]
        self.assertEqual(pos, sorted(pos))      # unnamed-wrong first within a tier, then oldest
        self.assertNotIn("E-ielts-0006", out)
        self.assertNotIn("E-ielts-0007", out)
        r = self.ind("due", "ielts")
        self.assertIn("2-day rechecks ready now: 1", r.stdout)
        self.assertIn("mistakes due: 1 fixed, 2 slips, 1 shaky", r.stdout)
        data = json.loads(self.ind("due", "ielts", "--json").stdout)
        self.assertEqual(data["counts"]["untreated"], 1)
        self.assertEqual([e["id"] for e in data["tiers"]["4_oldest"]], ["E-ielts-0001", "E-ielts-0002"])

    def test_untreated_belief_blocks_a_topic_recheck(self):
        self.put("ielts/data/exposures.jsonl", [{"v": 1, "topic": "T04", "at": "2026-10-10T08:00+01:00",
                                                 "kind": "teach"}])
        self.put("ielts/data/errors.jsonl", [self.error(1, status="untreated", topic="T04")])
        r = self.ind("due", "ielts", "--list")
        first = r.stdout.split("2. fixed")[0]
        self.assertNotIn("T04", first)


class RenderTests(BriefBase):
    def test_render_refuses_hand_edits_and_force_keeps_a_backup(self):
        view = self.s / "views" / "progress.md"
        self.assertTrue(view.exists())                    # rendered when the subject was added
        r = self.ind("render")
        self.assertEqual(r.returncode, 0, r.stderr)
        for name in ("brief.md", "progress.md", "errors.md", "log.md"):
            first = (self.s / "views" / name).read_text(encoding="utf-8").split("\n", 1)[0]
            self.assertEqual(first, wsmod.GENERATED_BANNER)
        view.write_text(view.read_text(encoding="utf-8") + "my own line\n", encoding="utf-8")
        before = (self.s / "views" / "log.md").read_text(encoding="utf-8")
        r = self.ind("render", "ielts", now="2026-10-12T10:00+01:00")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Refused", r.stdout)
        self.assertIn("ielts/views/progress.md", r.stdout)
        self.assertEqual((self.s / "views" / "log.md").read_text(encoding="utf-8"), before)   # nothing written
        r = self.ind("render", "ielts", "--force")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("my own line", (self.s / "views" / "progress.md.bak").read_text(encoding="utf-8"))
        self.assertNotIn("my own line", view.read_text(encoding="utf-8"))
        self.assertEqual(self.ind("render").returncode, 0)

    def test_generated_claude_md_sections(self):
        md = self.s / "CLAUDE.md"
        self.put("plan/blocks.jsonl", [self.block("B-20261013-ielts-1", "2026-10-13T07:00+01:00",
                                                  "2026-10-13T08:00+01:00")])
        self.assertEqual(self.ind("render", "all").returncode, 0)
        text = md.read_text(encoding="utf-8")
        inner = wsmod.marked_section(text)
        self.assertIn("Mastery (0–5): Matching headings 0", inner)
        self.assertIn("Tue 13 Oct 07:00–08:00 new skill (60 min)", inner)
        self.assertLessEqual(len(text.splitlines()), 80)
        self.assertNotIn("$", text)
        self.assertIsNone(ANY_ID.search(inner))
        root = (self.ws / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn('Say "start ielts"', root)
        # a hand edit inside the generated section is refused too
        md.write_text(text.replace("Mastery (0–5):", "Mastery (0-5) edited:"), encoding="utf-8")
        self.assertEqual(self.ind("render").returncode, 1)

    def test_a_file_never_rendered_is_not_refused(self):
        (self.ws / ".indelible" / "render.json").unlink()
        (self.s / "views" / "errors.md").write_text("learner text\n", encoding="utf-8")
        self.assertEqual(self.ind("render").returncode, 0)

    def test_log_keeps_30_sessions_of_at_most_200_characters(self):
        rows = []
        for i in range(1, 36):
            rows.append({"v": 1, "id": "S-ielts-%04d" % i, "block": None, "kind": "teach",
                         "planned": {"start": "2026-10-01T07:00+01:00", "min": 60},
                         "actual": {"start": "2026-10-01T07:00+01:00", "end": "2026-10-01T08:00+01:00",
                                    "elapsed_min": 60},
                         "sheets": [], "asks": {"n": 10, "right": 8}, "overrun_min": 0, "note": "n%02d " % i + "z" * 116,
                         "closed": {"at": "x", "status": "same-day"}})
        self.put("ielts/data/sessions.jsonl", rows)
        self.assertEqual(self.ind("render", "ielts").returncode, 0)
        lines = [l for l in (self.s / "views" / "log.md").read_text(encoding="utf-8").splitlines()
                 if l.startswith("- ")]
        self.assertEqual(len(lines), 30)
        self.assertTrue(all(len(l) <= 200 for l in lines))
        self.assertIn("n35", lines[0])
        self.assertIsNone(ANY_ID.search("\n".join(lines)))

    def test_render_week_marks_clashes_and_hides_recheck_topics(self):
        from lib import cmd_brief
        self.put("plan/blocks.jsonl", [
            self.block("B-20261013-ielts-1", "2026-10-13T07:00+01:00", "2026-10-13T08:00+01:00"),
            self.block("B-20261013-ielts-2", "2026-10-13T07:30+01:00", "2026-10-13T07:45+01:00", kind="cold",
                       content="cold:T04"),
            self.block("B-20261016-ielts-1", "2026-10-16T07:00+01:00", "2026-10-16T08:00+01:00",
                       status="cancelled"),
            {"v": 1, "id": "B-20261014-ielts-1", "subject": "ielts", "kind": "cold", "start": None, "end": None,
             "window": {"from": "2026-10-14T05:20+01:00", "to": "2026-10-15T09:20+01:00"}, "protected": True,
             "measurement": False, "soft": False, "pair": None, "content": "cold:T04", "status": "planned",
             "cal": None, "moved_from": None, "miss_reason": None},
        ])
        ws = wsmod.Workspace(self.ws)
        text = cmd_brief.render_week(ws)
        self.assertEqual(text, (self.ws / "views" / "week.md").read_text(encoding="utf-8"))
        self.assertIn("# Week 2026-W42 (Mon 12 Oct – Sun 18 Oct)", text)
        self.assertIn("| Tue 13 Oct | 07:00–08:00 | IELTS Academic | new skill | 60 | planned · CLASH |",
                      text)
        self.assertIn("2-day recheck (mixed)", text)
        self.assertNotIn("T04", text)
        self.assertNotIn("Fri 16 Oct | 07:00", text)          # cancelled
        self.assertIn("2-day rechecks still to book:", text)
        self.assertIn("Minutes planned: IELTS Academic 75 (target 240)", text)
        for day in ("Mon 12 Oct", "Wed 14 Oct", "Sun 18 Oct"):
            self.assertIn("| %s |" % day, text)
        other = cmd_brief.render_week(ws, start="2026-10-21", write=False)
        self.assertIn("2026-W43", other)
        self.assertEqual((self.ws / "views" / "week.md").read_text(encoding="utf-8"), text)


class IntegrationTests(BriefBase):
    """Fixes found while wiring the modules together."""

    def test_a_sheet_issued_for_a_future_block_is_not_counted_until_the_block_starts(self):
        # close.md issues the next block's sheets at the close; opens before that block do not count.
        self.put("plan/blocks.jsonl", [self.block("B-20261015-ielts-1", "2026-10-15T07:00+01:00",
                                                  "2026-10-15T08:00+01:00")])
        row = self.sheet("ielts-drills-02")
        row["block"] = "B-20261015-ielts-1"
        self.put("ielts/data/sheets.jsonl", [row])

        def opens():
            return self.jsonl("ielts/data/sheets.jsonl")[0]["opens_unsat"]

        self.brief()
        self.brief(now="2026-10-14T07:00+01:00")
        self.assertEqual(opens(), 0)
        self.assertNotIn("not taken", self.brief(now="2026-10-14T20:00+01:00"))
        self.brief(now="2026-10-15T07:05+01:00")
        self.assertEqual(opens(), 1)

    def test_plan_tokens_never_reach_a_plain_learner_raw(self):
        from lib import cmd_brief
        teach = self.block("B-20261015-ielts-1", "2026-10-15T07:00+01:00", "2026-10-15T08:00+01:00",
                           content="teach:T04")
        self.assertEqual(cmd_brief.block_what(teach, True, {"T04": "Paraphrase"}), "new skill: Paraphrase")
        self.assertEqual(cmd_brief.block_what(teach, True), "new skill")
        self.assertEqual(cmd_brief.block_what(teach, False), "teach: teach:T04")
        mixed = self.block("B-20261016-ielts-1", "2026-10-16T07:00+01:00", "2026-10-16T08:00+01:00",
                           kind="mixed", content="cold:T04, then new skill")
        self.assertEqual(cmd_brief.block_topics(mixed), ["T04"])
        self.assertEqual(cmd_brief.block_what(mixed, True), "mixed practice: 2-day recheck, then new skill")
        self.put("plan/blocks.jsonl", [teach])
        learner, _ = self.parts(self.brief())
        self.assertIn("new skill: Paraphrase", learner)
        self.assertNotIn("teach:", learner)


class OnDemandTests(BriefBase):
    persona = "D"

    def test_on_demand_learner_is_never_asked_about_missed_blocks(self):
        self.put("plan/blocks.jsonl", [self.block("B-20261010-rust-1", "2026-10-10T10:00+01:00",
                                                  "2026-10-10T11:00+01:00")])
        text = self.brief()
        self.assertTrue(text.startswith("Rust · code · no date"))
        self.assertNotIn("missed?", text)
        self.assertNotIn("MISSED", text)


if __name__ == "__main__":
    unittest.main()
