"""Regression tests for the v0.1 review findings (one or more per fixed bug).

Synthetic personas only: A (ielts, Europe/Lisbon), D (rust, Europe/Berlin,
on demand). Accepted answers in these keys are made-up words or labels.
"""

import json
import os
import re
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

try:
    from helpers import HAS_TZDB, CLI, make_ws, run
    from test_sheet import (NOW, SUBJECT, add_exposure, answers_for, cold_spec, drills_spec, new_sheet, sheet_row,
                            subject_dir, theory_spec)
    from test_lint import ctx, result
    from test_grade import make_item, write_sheet
    from test_plan import PlanCase, SID
    from test_render import typst_balance_problems
except ImportError:  # run as part of the tests package
    from tests.helpers import HAS_TZDB, CLI, make_ws, run
    from tests.test_sheet import (NOW, SUBJECT, add_exposure, answers_for, cold_spec, drills_spec, new_sheet,
                                  sheet_row, subject_dir, theory_spec)
    from tests.test_lint import ctx, result
    from tests.test_grade import make_item, write_sheet
    from tests.test_plan import PlanCase, SID
    from tests.test_render import typst_balance_problems

from lib import LockBusy, TEMPLATES_DIR, dates, lint, render, schema
from lib import io as fio
from lib import cmd_session

CYRILLIC = re.compile("[%s-%s]" % (chr(0x0400), chr(0x04FF)))   # built from code points: no such text in the repo




class TmpCase(unittest.TestCase):
    PERSONA = "A"

    def setUp(self):
        self._old_now = os.environ.get("INDELIBLE_NOW")
        os.environ["INDELIBLE_NOW"] = NOW
        self.tmp = Path(tempfile.mkdtemp(prefix="indelible-regr-"))
        self.ws = make_ws(self.tmp, self.PERSONA)

    def tearDown(self):
        if self._old_now is None:
            os.environ.pop("INDELIBLE_NOW", None)
        else:
            os.environ["INDELIBLE_NOW"] = self._old_now
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def cli(self, args, now=NOW, code=0, stdin=None, env=None):
        r = run([str(a) for a in args], ws=self.ws, now=now, stdin=stdin, env=env)
        if code is not None:
            self.assertEqual(r.returncode, code, "%s -> %s\n%s\n%s" % (args, r.returncode, r.stdout, r.stderr))
        return r

    def set_root(self, dotted, value):
        path = self.ws / "indelible.json"
        cfg = fio.read_json(path)
        node = cfg
        parts = dotted.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = value
        fio.write_json(path, cfg)

    def blocks(self):
        return dict((b["id"], b) for b in fio.read_jsonl(self.ws / "plan" / "blocks.jsonl"))

    def save_blocks(self, rows):
        fio.write_jsonl(self.ws / "plan" / "blocks.jsonl", list(rows))

    def lint_line(self, r, rule):
        for ln in r.stdout.splitlines():
            if ln.startswith(rule + " "):
                return ln
        self.fail("no %s line in:\n%s" % (rule, r.stdout))


# ==========================================================================
# Lint
# ==========================================================================

class LintRuleRegressions(unittest.TestCase):
    def setUp(self):
        self._old_now = os.environ.get("INDELIBLE_NOW")
        os.environ["INDELIBLE_NOW"] = NOW

    def tearDown(self):
        if self._old_now is None:
            os.environ.pop("INDELIBLE_NOW", None)
        else:
            os.environ["INDELIBLE_NOW"] = self._old_now

    def two_item_cold(self, second_origin, second_topic="T01"):
        spec = cold_spec()
        spec["items"] = spec["items"][:2]
        spec["items"][1]["origin"] = second_origin
        spec["items"][1]["topic"] = second_topic
        return spec

    def test_l7_error_reserve_needs_24_hours_and_a_due_date(self):
        at = dates.parse_iso("2026-10-19T07:58+01:00")
        teach = {"topic": "T04", "at": "2026-10-17T07:58+01:00", "kind": "teach"}
        spec = self.two_item_cold("error:E-ielts-0002")
        err = {"v": 1, "id": "E-ielts-0002", "topic": "T01", "kind": "slip", "status": "spacing",
               "next_due": "2026-10-20"}
        seen_now = {"topic": "T01", "at": "2026-10-19T07:58+01:00", "kind": "repair"}
        r = result(spec, "L7", now=at, exposures=[teach, seen_now], errors=[err])
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("not due until 2026-10-20", r["detail"])
        due = dict(err, next_due="2026-10-19")
        r = result(spec, "L7", now=at, exposures=[teach, seen_now], errors=[due])
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("less than 24 h", r["detail"])
        long_ago = dict(seen_now, at="2026-10-18T01:00+01:00")
        self.assertEqual(result(spec, "L7", now=at, exposures=[teach, long_ago], errors=[due])["status"], "PASS")

    def test_l7_sentinel_serve_keeps_the_24_hour_rule(self):
        at = dates.parse_iso("2026-10-19T07:58+01:00")
        teach = {"topic": "T04", "at": "2026-10-17T07:58+01:00", "kind": "teach"}
        spec = self.two_item_cold("sentinel:E-ielts-0003")
        retired = {"v": 1, "id": "E-ielts-0003", "topic": "T01", "kind": "slip", "status": "retired",
                   "next_due": None}
        recent = {"topic": "T01", "at": "2026-10-19T05:58+01:00", "kind": "chat"}
        self.assertEqual(result(spec, "L7", now=at, exposures=[teach, recent], errors=[retired])["status"], "FAIL")
        old = dict(recent, at="2026-10-17T20:00+01:00")
        self.assertEqual(result(spec, "L7", now=at, exposures=[teach, old], errors=[retired])["status"], "PASS")

    def test_l7_a_topic_never_taught_is_not_recheck_material(self):
        spec = cold_spec()
        spec["items"] = [spec["items"][0]]
        spec["items"][0].update({"topic": "T02", "origin": "cold:T02"})
        drilled = [{"topic": "T02", "at": "2026-10-10T08:00+01:00", "kind": "drill"}]
        r = result(spec, "L7", exposures=drilled)
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("not taught yet", r["detail"])
        review = [{"topic": "T02", "at": "2026-10-10T08:00+01:00", "kind": "review"}]   # the 3p review set
        self.assertEqual(result(spec, "L7", exposures=review)["status"], "PASS")
        taught = {"T02": {"taught_at": "2026-10-10T08:00+01:00", "last_cold": None}}
        self.assertEqual(result(spec, "L7", exposures=drilled, topics_state=taught)["status"], "PASS")

    def test_l8_roman_numeral_option_labels_are_not_leaks(self):
        spec = drills_spec()
        spec["items"][0]["text"] = ("Choose the heading for paragraph B.\n\ni. How the town grew\n"
                                    "ii. Why the mill closed\niii. A river in winter\niv. Who paid for the school")
        key = answers_for(spec)
        key["1a"]["accept"] = ["iii"]
        self.assertEqual(result(spec, "L8", key=key)["status"], "PASS")
        key["1a"]["accept"] = ["(iii)"]
        self.assertEqual(result(spec, "L8", key=key)["status"], "PASS")
        # the option's own text is still a leak: key the label, not the heading
        key["1a"]["accept"] = ["A river in winter"]
        self.assertEqual(result(spec, "L8", key=key)["status"], "FAIL")

    def test_l8_passage_copy_items(self):
        spec = drills_spec()
        spec["items"][0]["text"] = "The ferry left the harbour at dawn."
        spec["items"][0]["asks"][0]["label"] = "Copy ONE word from the sentence: the ferry left the ____ at dawn."
        key = answers_for(spec)
        key["1a"]["accept"] = ["harbour"]
        self.assertEqual(result(spec, "L8", key=key)["status"], "FAIL")   # no flag: a leak
        spec["items"][0]["answer_in_passage"] = True
        self.assertEqual(result(spec, "L8", key=key)["status"], "PASS")
        spec["items"][0]["asks"][0]["check_hint"] = "It is harbour"   # still checked outside the passage
        self.assertEqual(result(spec, "L8", key=key)["status"], "FAIL")

    def test_l8_matches_inside_a_longer_word(self):
        spec = drills_spec()
        spec["items"][0]["text"] = "Photosynthesising plants release oxygen. Name the process."
        key = answers_for(spec)
        key["1a"]["accept"] = ["photosynthesis"]
        self.assertEqual(result(spec, "L8", key=key)["status"], "FAIL")

    def test_l4_skips_code_and_reads_theory_bodies(self):
        spec = drills_spec()
        spec["items"][0]["text"] = ("Read the code.\n\n```rust\nlet total: i32 = v.iter().sum();\n```\n\n"
                                    "What does `mean()` give?")
        self.assertEqual(result(spec, "L4")["status"], "PASS")
        spec = theory_spec()
        spec["theory"]["sections"][1]["body"] = "Keep the idea. Take the mean of the two."
        r = result(spec, "L4")
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("'mean'", r["detail"])

    def test_l4_everyday_and_measured_here_resolutions(self):
        spec = drills_spec()
        spec["items"][0]["text"] = "Use at most two words."
        self.assertEqual(result(spec, "L4")["status"], "FAIL")
        spec["terms"] = [{"term": "at most", "resolution": "everyday"}]
        self.assertEqual(result(spec, "L4")["status"], "PASS")
        # never "everyday" for a word the learner has stumbled on (the lexicon)
        lex = lint.sense_words({"lexicon": ["albeit"]})
        spec = drills_spec()
        spec["items"][0]["text"] = "It moved, albeit slowly."
        spec["terms"] = [{"term": "albeit", "resolution": "everyday"}]
        self.assertEqual(result(spec, "L4", sense=lex, lexicon={"albeit"})["status"], "FAIL")
        # measured_here: only where the word is being measured
        spec["terms"] = [{"term": "albeit", "resolution": "measured_here"}]
        self.assertEqual(result(spec, "L4", sense=lex)["status"], "FAIL")
        spec["type"] = "diagnostic"
        self.assertEqual(result(spec, "L4", sense=lex)["status"], "PASS")
        spec["terms"] = [{"term": "albeit", "resolution": "known"}]
        self.assertIn("unknown resolution", result(spec, "L4", sense=lex)["detail"])

    def test_l2_check_lines_are_optional_on_repair_sheets(self):
        spec = drills_spec(type="repair")
        for it in spec["items"]:
            it["asks"][0]["check"] = False
        self.assertEqual(result(spec, "L2")["status"], "PASS")

    def test_l3_a_single_topic_recheck_with_a_mistake_reserve_passes(self):
        spec = self.two_item_cold("error:E-ielts-0002", second_topic="T04")
        self.assertEqual(result(spec, "L3")["status"], "PASS")
        spec = cold_spec()
        spec["items"][1], spec["items"][2] = spec["items"][2], spec["items"][1]
        self.assertEqual(result(spec, "L3")["status"], "FAIL")   # two topics: adjacency still checked


class LintCliRegressions(TmpCase):
    TUE_CLOSE = "2026-10-13T20:00+01:00"

    def recheck_block(self):
        r = self.cli(["plan", "add", SUBJECT, "--kind", "cold", "--start", "2026-10-14T07:00+01:00", "--min", "20",
                      "--content", "cold:T04,T01"])
        return r.stdout.split()[0]

    def test_a_recheck_built_at_the_previous_close_is_judged_at_its_block(self):
        add_exposure(self.ws, "T04", "2026-10-12T07:10+01:00")
        add_exposure(self.ws, "T01", "2026-10-12T07:10+01:00")
        bid = self.recheck_block()
        spec = cold_spec()
        self.assertEqual(new_sheet(self.ws, spec, now=self.TUE_CLOSE).returncode, 0)
        r = self.cli(["sheet", "lint", SUBJECT, spec["id"]], now=self.TUE_CLOSE, code=1)
        self.assertIn("window opens at 44 h", self.lint_line(r, "L7"))
        r = self.cli(["sheet", "lint", SUBJECT, spec["id"], "--block", bid], now=self.TUE_CLOSE)
        self.assertIn("eligible at the start of block %s" % bid, self.lint_line(r, "L7"))
        self.assertEqual(sheet_row(self.ws, spec["id"])["block"], bid)
        self.cli(["sheet", "build", SUBJECT, spec["id"], "--format", "md"], now=self.TUE_CLOSE)
        self.cli(["sheet", "issue", SUBJECT, spec["id"]], now=self.TUE_CLOSE)

    def test_issue_rechecks_the_recheck_at_the_time_it_will_be_sat(self):
        add_exposure(self.ws, "T04", "2026-10-12T07:10+01:00")
        add_exposure(self.ws, "T01", "2026-10-12T07:10+01:00")
        bid = self.recheck_block()
        spec = cold_spec()
        self.assertEqual(new_sheet(self.ws, spec, extra=["--block", bid], now=self.TUE_CLOSE).returncode, 0)
        self.cli(["sheet", "lint", SUBJECT, spec["id"]], now=self.TUE_CLOSE)
        self.cli(["sheet", "build", SUBJECT, spec["id"], "--format", "md"], now=self.TUE_CLOSE)
        add_exposure(self.ws, "T04", "2026-10-13T21:00+01:00", kind="chat")   # discussed after the build
        r = self.cli(["sheet", "issue", SUBJECT, spec["id"]], now="2026-10-13T21:05+01:00", code=1)
        self.assertIn("not valid when it will be sat", r.stdout)
        self.assertEqual(sheet_row(self.ws, spec["id"])["status"], "rendered")

    def test_sheet_sat_warns_when_a_recheck_topic_was_just_seen(self):
        add_exposure(self.ws, "T04", "2026-10-10T08:00+01:00")
        add_exposure(self.ws, "T01", "2026-10-10T08:00+01:00")
        spec = cold_spec()
        self.assertEqual(new_sheet(self.ws, spec).returncode, 0)
        self.cli(["sheet", "lint", SUBJECT, spec["id"]])
        self.cli(["sheet", "build", SUBJECT, spec["id"], "--format", "md"])
        self.cli(["sheet", "issue", SUBJECT, spec["id"]])
        add_exposure(self.ws, "T01", "2026-10-12T08:30+01:00", kind="chat")
        r = self.cli(["sheet", "sat", SUBJECT, spec["id"], "--start", "08:45"], now="2026-10-12T09:00+01:00")
        self.assertIn("WARN: T01 was seen 0 h before this sitting", r.stdout)
        self.assertNotIn("T04 was seen", r.stdout)

    def test_glossary_resolution_is_checked_and_glossary_add_owns_a_word(self):
        from lib import ws as wsmod
        subj = wsmod.Workspace(self.ws).subject(SUBJECT)
        cfg = subj.load()
        cfg["sense_list"] = ["gist"]
        subj.save(cfg)
        spec = drills_spec()
        spec["items"][0]["text"] = "What is the gist of the second paragraph?"
        spec["terms"] = [{"term": "gist", "resolution": "glossary"}]
        self.assertEqual(new_sheet(self.ws, spec).returncode, 0)
        r = self.cli(["sheet", "lint", SUBJECT, spec["id"]], code=1)
        self.assertIn("not in the learner's glossary", self.lint_line(r, "L4"))
        r = self.cli(["glossary", "add", SUBJECT, "gist", "--def", "the main idea", "--gloss", "ideia principal"])
        self.assertIn("Glossary added: 'gist'", r.stdout)
        r = self.cli(["glossary", "add", SUBJECT, "Gist", "--def", "the main point"])
        self.assertIn("Glossary updated", r.stdout)
        rows = fio.read_jsonl(subject_dir(self.ws) / "data" / "glossary.jsonl")
        self.assertEqual([(g["term"], g["def"]) for g in rows], [("gist", "the main point")])
        self.assertIn("gist (ideia principal): the main point", self.cli(["glossary", "list", SUBJECT]).stdout)
        r = self.cli(["sheet", "lint", SUBJECT, spec["id"]])
        self.assertTrue(self.lint_line(r, "L4").startswith("L4 PASS"))


# ==========================================================================
# Sheets
# ==========================================================================

class SheetRegressions(TmpCase):
    def teach_block(self, start="2026-10-13T07:00+01:00", minutes=20):
        r = self.cli(["plan", "add", SUBJECT, "--kind", "teach", "--start", start, "--min", minutes,
                      "--content", "new skill"])
        return r.stdout.split()[0]

    def test_issue_refuses_a_sheet_over_its_blocks_budget(self):
        bid = self.teach_block()
        spec = drills_spec(est_min=40)
        self.assertEqual(new_sheet(self.ws, spec).returncode, 0)
        r = self.cli(["sheet", "lint", SUBJECT, spec["id"]])
        self.assertIn("0.8 × the default session", self.lint_line(r, "L5"))
        self.cli(["sheet", "build", SUBJECT, spec["id"], "--format", "md"])
        r = self.cli(["sheet", "issue", SUBJECT, spec["id"], "--block", bid], code=1)
        self.assertIn("over the budget of 16 min", r.stdout)
        self.assertEqual(sheet_row(self.ws, spec["id"])["status"], "rendered")
        # linked at build time, lint already sizes it against the block
        spec2 = drills_spec("ielts-drills-02", est_min=40)
        self.assertEqual(new_sheet(self.ws, spec2, extra=["--block", bid]).returncode, 0)
        r = self.cli(["sheet", "lint", SUBJECT, spec2["id"]], code=1)
        self.assertIn(bid, self.lint_line(r, "L5"))

    def test_new_prints_one_question_links_the_block_and_clears_the_scratch_spec(self):
        bid = self.teach_block()
        spec = drills_spec(n=1)
        r = new_sheet(self.ws, spec, extra=["--block", bid])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("built: 1 question,", r.stdout)
        self.assertEqual(sheet_row(self.ws, spec["id"])["block"], bid)
        tmp = subject_dir(self.ws) / ".indelible" / "tmp"
        self.assertEqual(sorted(p.name for p in tmp.iterdir()), [])

    def test_build_prints_the_blocks_date_not_the_build_day(self):
        bid = self.teach_block("2026-10-13T07:00+01:00", 60)
        spec = drills_spec()
        self.assertEqual(new_sheet(self.ws, spec, extra=["--block", bid]).returncode, 0)
        self.cli(["sheet", "lint", SUBJECT, spec["id"]])
        r = self.cli(["sheet", "build", SUBJECT, spec["id"], "--format", "md"])
        text = Path(r.stdout.splitlines()[0]).read_text(encoding="utf-8")
        self.assertIn("Tuesday 13 October 2026", text)
        self.assertNotIn("Monday 12 October 2026", text)

    def issued_drills(self):
        spec = drills_spec()
        self.assertEqual(new_sheet(self.ws, spec).returncode, 0)
        self.cli(["sheet", "lint", SUBJECT, spec["id"]])
        self.cli(["sheet", "build", SUBJECT, spec["id"], "--format", "md"])
        self.cli(["sheet", "issue", SUBJECT, spec["id"]])
        return spec["id"]

    def test_a_piped_transcript_is_read_as_utf8_whatever_the_locale(self):
        sid = self.issued_drills()
        text = u"1a: Ação ≤ 3\n2a: Ñandú\n"
        self.cli(["scan", "ingest", SUBJECT, sid, "--transcript", "-"], stdin=text,
                 env={"PYTHONUTF8": None, "PYTHONIOENCODING": "cp1252"})
        saved = subject_dir(self.ws) / "scans" / ("2026-10-12-%s-answers.txt" % sid)
        self.assertEqual(saved.read_text(encoding="utf-8"), text)

    def test_scan_ingest_dir_keeps_a_code_projects_layout(self):
        sid = self.issued_drills()
        proj = self.tmp / "csvtool"
        (proj / "src").mkdir(parents=True)
        (proj / "target" / "debug").mkdir(parents=True)
        (proj / ".git").mkdir()
        (proj / "Cargo.toml").write_text("[package]\nname = \"csvtool\"\n", encoding="utf-8")
        (proj / "src" / "lib.rs").write_text("pub mod parse;\n", encoding="utf-8")
        (proj / "src" / "parse.rs").write_text("pub fn rows() {}\n", encoding="utf-8")
        (proj / "target" / "debug" / "csvtool").write_text("binary", encoding="utf-8")
        (proj / ".git" / "HEAD").write_text("ref", encoding="utf-8")
        r = self.cli(["scan", "ingest", SUBJECT, sid, "--dir", proj])
        snap = subject_dir(self.ws) / "answers" / sid
        self.assertTrue((snap / "Cargo.toml").is_file(), r.stdout)
        self.assertTrue((snap / "src" / "lib.rs").is_file())
        self.assertTrue((snap / "src" / "parse.rs").is_file())
        self.assertFalse((snap / "target").exists())
        self.assertFalse((snap / ".git").exists())
        ev = sheet_row(self.ws, sid)["evidence"][-1]
        self.assertEqual((ev["kind"], ev["file"], ev["files"]), ("project", "answers/%s/" % sid, 3))
        self.assertEqual(ev["source"], str(proj.resolve()))
        self.assertEqual(sheet_row(self.ws, sid)["status"], "sat")


# ==========================================================================
# Plan and calendar
# ==========================================================================

class PlanRegressions(PlanCase):
    def test_a_missed_block_that_is_rebooked_keeps_its_miss(self):
        bid = self.add("review", "2026-10-12T07:00+01:00", 30)
        self.ok("plan", "miss", bid, "--reason", "overslept")
        self.ok("plan", "move", bid, "--start", "2026-10-14T07:00+01:00")
        b = self.blocks()[bid]
        self.assertEqual(b["status"], "planned")
        self.assertEqual(b["miss_reason"], "overslept")
        self.assertEqual([(m["slot"], m["reason"]) for m in b["misses"]], [("2026-10-12T07:00+01:00", "overslept")])
        self.assertIn("missed Mon 12 Oct 07:00 (overslept), rebooked", self.ok("plan", "list").stdout)
        r = self.ok("review", "week", SID, "--week", "2026-W42", now="2026-10-18T19:00+01:00")
        self.assertIn("0 moved, 1 missed (1 rebooked)", r.stdout)

    def test_the_same_slot_missed_twice_is_flagged(self):
        bid = self.add("review", "2026-10-12T07:00+01:00", 30)
        self.ok("plan", "miss", bid, "--reason", "overslept")
        self.ok("plan", "move", bid, "--start", "2026-10-19T07:00+01:00")
        r = self.ok("plan", "miss", bid, "--reason", "overslept again", now="2026-10-19T09:00+01:00")
        self.assertIn("was missed before (overslept)", r.stdout)

    def test_plan_check_opens_the_window_at_the_last_exposure(self):
        self.expose("T01", "2026-10-12T07:10+01:00")
        window = {"from": "2026-10-14T03:10+01:00", "to": "2026-10-15T07:10+01:00"}
        bid = self.write_block(id="B-20261014-ielts-1", start="2026-10-14T07:00+01:00",
                               end="2026-10-14T07:20+01:00", window=window)
        rc, data = self.check()
        self.assertEqual(self.findings(data, rule="cold_window", block=bid), [])
        # drills on T01 sat Monday evening: 35 h before the recheck, inside the stored window but too soon
        self.expose("T01", "2026-10-12T20:00+01:00", kind="drill")
        rc, data = self.check()
        rows = self.findings(data, level="FAIL", rule="cold_window", block=bid)
        self.assertEqual(len(rows), 1, data)
        self.assertIn("opens at 44 h", rows[0]["message"])

    def test_diff_takes_over_ics_blocks_and_ics_exports_creates_only(self):
        self.set_root("calendar.provider", "google")
        a = self.add("review", "2026-10-13T17:00+01:00", 30)
        b = self.add("review", "2026-10-14T17:00+01:00", 30)
        c = self.add("review", "2026-10-15T17:00+01:00", 30)
        rows = fio.read_jsonl(self.ws / "plan" / "blocks.jsonl")
        for row in rows:
            if row["id"] == a:
                row["cal"] = {"provider": "ics", "id": "%s@indelible" % a, "etag": None, "start": row["start"]}
                row["status"] = "synced"
            if row["id"] == c:
                row["cal"] = {"provider": "google", "id": "evt-3", "etag": None, "start": "2026-10-15T18:00+01:00"}
                row["status"] = "synced"
        fio.write_jsonl(self.ws / "plan" / "blocks.jsonl", rows)
        diff = dict((d["block"], d) for d in json.loads(self.ok("plan", "diff", "--json").stdout))
        self.assertEqual((diff[a]["op"], diff[a].get("takeover")), ("create", "ics"))
        self.assertEqual(diff[b]["op"], "create")
        self.assertEqual(diff[c]["op"], "move")
        out = self.ws / "plan" / "ics" / "new.ics"
        self.ok("cal", "ics", out, "--ops", "create")
        text = out.read_text(encoding="utf-8")
        self.assertIn("UID:%s@indelible" % b, text)
        self.assertNotIn("UID:%s@indelible" % a, text)   # already sent out in a file
        self.assertNotIn("UID:%s@indelible" % c, text)   # a move: a file cannot update an import
        full = self.ws / "plan" / "ics" / "all.ics"
        self.ok("cal", "ics", full)
        self.assertIn("UID:%s@indelible" % c, full.read_text(encoding="utf-8"))


class OnDemandRegressions(TmpCase):
    PERSONA = "D"

    def test_on_demand_learners_book_nothing(self):
        self.cli(["session", "taught", "rust", "T01", "--by", "sheet"], now="2026-10-12T20:00+02:00")
        r = self.cli(["brief", "rust"], now="2026-10-13T09:00+02:00")
        self.assertIn("2-day recheck open between", r.stdout)
        self.assertNotIn("to book", r.stdout)
        r = self.cli(["plan", "week"], now="2026-10-13T09:00+02:00")
        self.assertNotIn("(target", r.stdout)
        self.assertNotIn("Minutes planned", r.stdout)
        self.assertNotIn("still to book", r.stdout)
        self.assertIn("nothing to book", r.stdout)

    @unittest.skipUnless(HAS_TZDB, "no tz database")
    def test_the_recheck_window_is_exactly_72_elapsed_hours_across_the_clock_change(self):
        taught = "2026-10-22T20:37+02:00"   # Berlin leaves summer time on 25 Oct
        self.cli(["session", "taught", "rust", "T01"], now=taught)
        obl = [b for b in self.blocks().values() if b["kind"] == "cold"][0]
        self.assertAlmostEqual(dates.hours_between(taught, obl["window"]["from"]), 44.0)
        self.assertAlmostEqual(dates.hours_between(taught, obl["window"]["to"]), 72.0)
        self.assertEqual(obl["window"]["to"], "2026-10-25T19:37+01:00")


# ==========================================================================
# Session: elapsed hours across the clock change, C2, promise words
# ==========================================================================

class SessionRegressions(TmpCase):
    @unittest.skipUnless(HAS_TZDB, "no tz database")
    def test_c4_uses_elapsed_hours_across_the_clock_change(self):
        # Lisbon: +01:00 until 25 Oct 02:00, then +00:00. Taught Sat 24 Oct 14:00 (13:00 UTC):
        # the window closes at 13:00 UTC on Tue 27 Oct, i.e. 13:00 local (not 14:00).
        self.cli(["session", "open", SUBJECT, "--planned", "60"], now="2026-10-24T13:50+01:00")
        self.cli(["session", "taught", SUBJECT, "T01"], now="2026-10-24T14:00+01:00")
        rows = list(self.blocks().values())
        obl = [b for b in rows if b["kind"] == "cold"][0]
        self.assertEqual(obl["window"]["to"], "2026-10-27T13:00+00:00")
        obl.update({"start": "2026-10-27T13:30+00:00", "end": "2026-10-27T13:50+00:00", "window": None})
        self.save_blocks(rows)
        r = self.cli(["session", "close", SUBJECT], now="2026-10-24T14:30+01:00", code=1)
        self.assertIn("FAIL C4", r.stdout)
        obl.update({"start": "2026-10-27T12:30+00:00", "end": "2026-10-27T12:50+00:00"})
        self.save_blocks(rows)
        r = self.cli(["session", "close", SUBJECT], now="2026-10-24T14:31+01:00")
        self.assertIn("PASS C4", r.stdout)

    def test_expose_warning_counts_elapsed_hours(self):
        self.save_blocks([{"v": 1, "id": "B-20261025-ielts-1", "subject": SUBJECT, "kind": "cold",
                           "start": "2026-10-25T13:30+00:00", "end": "2026-10-25T13:50+00:00", "window": None,
                           "protected": True, "measurement": False, "soft": False, "pair": None,
                           "content": "cold:T01", "status": "planned", "cal": None, "moved_from": None,
                           "miss_reason": None}])
        # 24.5 elapsed hours before the recheck (23.5 on the wall clock): no warning
        r = self.cli(["session", "expose", SUBJECT, "T01"], now="2026-10-24T14:00+01:00")
        self.assertNotIn("WARN", r.stdout)
        r = self.cli(["session", "expose", SUBJECT, "T01"], now="2026-10-24T15:00+01:00")
        self.assertIn("WARN", r.stdout)

    def test_read_then_close_sheets_need_no_grading_at_close(self):
        self.cli(["session", "open", SUBJECT, "--planned", "60"], now="2026-10-12T09:00+01:00")
        spec = theory_spec()
        self.assertEqual(new_sheet(self.ws, spec).returncode, 0)
        self.cli(["sheet", "lint", SUBJECT, spec["id"]])
        self.cli(["sheet", "build", SUBJECT, spec["id"], "--format", "md"])
        self.cli(["sheet", "issue", SUBJECT, spec["id"]])
        typed = self.tmp / "pencils.txt"
        typed.write_text("1a: The store closed at midday.\n", encoding="utf-8")
        self.cli(["scan", "ingest", SUBJECT, spec["id"], "--typed", typed], now="2026-10-12T09:20+01:00")
        r = self.cli(["session", "close", SUBJECT], now="2026-10-12T09:40+01:00")
        self.assertIn("PASS C2 graded: nothing to grade", r.stdout)

    def test_promise_words_come_from_the_personas_languages(self):
        for text in ("fica para amanhã", "lo termino mañana", "machen wir morgen", "das mache ich später",
                     "I'll do it later", "next time"):
            self.assertTrue(cmd_session.PROMISE_RE.search(text), text)
        self.assertIsNone(CYRILLIC.search(cmd_session.PROMISE_RE.pattern))


# ==========================================================================
# Dates, lock, setup
# ==========================================================================

class DatesRegressions(unittest.TestCase):
    @unittest.skipUnless(hasattr(time, "tzset"), "needs time.tzset (POSIX)")
    def test_without_a_tz_database_the_os_zone_keeps_its_clock_changes(self):
        old_tz, old_now = os.environ.get("TZ"), os.environ.pop("INDELIBLE_NOW", None)
        os.environ["TZ"] = "Europe/Lisbon"
        time.tzset()
        try:
            with mock.patch.object(dates, "_load_zone", return_value=None):
                tz = dates.tz_for("Europe/Lisbon")
                self.assertIsInstance(tz, dates.SystemLocalTimezone)
                self.assertEqual(datetime(2026, 10, 20, 7, 0, tzinfo=tz).utcoffset(), timedelta(hours=1))
                self.assertEqual(datetime(2026, 10, 27, 7, 0, tzinfo=tz).utcoffset(), timedelta(0))
                self.assertEqual(dates.fmt_iso(dates.parse_iso("2026-10-27T07:00", tz=tz)), "2026-10-27T07:00+00:00")
                self.assertEqual(datetime(2026, 10, 27, 7, 0, tzinfo=timezone.utc).astimezone(tz).hour, 7)
                self.assertEqual(datetime(2026, 10, 20, 6, 0, tzinfo=timezone.utc).astimezone(tz).hour, 7)
                self.assertIn("cannot be loaded", dates.zone_problem("Europe/Lisbon"))
                # the test clock keeps its fixed offset, so tests never depend on the machine
                os.environ["INDELIBLE_NOW"] = "2026-10-20T09:00+01:00"
                self.assertNotIsInstance(dates.tz_for("Europe/Lisbon"), dates.SystemLocalTimezone)
        finally:
            if old_tz is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = old_tz
            time.tzset()
            if old_now is None:
                os.environ.pop("INDELIBLE_NOW", None)
            else:
                os.environ["INDELIBLE_NOW"] = old_now

    def test_plus_is_elapsed_time(self):
        from zoneinfo import ZoneInfo
        try:
            berlin = ZoneInfo("Europe/Berlin")
        except Exception:
            self.skipTest("no tz database")
        t = datetime(2026, 10, 22, 20, 37, tzinfo=berlin)
        self.assertEqual(dates.fmt_iso(dates.plus(t, hours=72)), "2026-10-25T19:37+01:00")
        self.assertAlmostEqual(dates.hours_from(t, dates.plus(t, hours=72)), 72.0)

    def test_windows_may_end_at_24_00_or_run_overnight(self):
        from lib import ws as wsmod
        cfg = wsmod.default_config()
        cfg["time"]["windows"] = [{"days": ["Mon"], "from": "21:00", "to": "24:00"},
                                  {"days": ["Fri"], "from": "22:00", "to": "01:00"}]
        self.assertEqual(schema.validate_config(cfg), [])
        cfg["time"]["windows"] = [{"days": ["Mon"], "from": "09:00", "to": "09:00"}]
        self.assertTrue(any("empty" in p for p in schema.validate_config(cfg)))


class LockRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="indelible-lock-"))
        (self.tmp / ".indelible").mkdir()
        self.lock = self.tmp / ".indelible" / "write.lock"

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def test_taking_over_a_stale_lock_never_removes_a_fresh_one(self):
        self.lock.write_text(json.dumps({"pid": 999999, "host": "other-host", "at": "old",
                                         "epoch": time.time() - 700}), encoding="utf-8")
        fresh = {"pid": 424242, "host": "other-host", "at": "new", "epoch": time.time()}
        real = fio.lock_is_stale
        calls = {"n": 0}

        def racing(info, stale_after=fio.LOCK_STALE_S):
            # A judges the old lock stale; before it acts, B takes the lock over.
            calls["n"] += 1
            if calls["n"] == 1:
                os.unlink(str(self.lock))
                self.lock.write_text(json.dumps(fresh), encoding="utf-8")
                return True
            return real(info, stale_after)

        with mock.patch.object(fio, "lock_is_stale", racing):
            with self.assertRaises(LockBusy):
                fio.WriteLock(self.tmp, timeout=0.3).acquire()
        self.assertEqual(json.loads(self.lock.read_text(encoding="utf-8"))["pid"], 424242)
        self.assertEqual(sorted(p.name for p in self.lock.parent.iterdir()), ["write.lock"])

    def test_a_stale_lock_is_still_taken_over(self):
        self.lock.write_text(json.dumps({"pid": 999999, "host": "other-host", "at": "old",
                                         "epoch": time.time() - 700}), encoding="utf-8")
        with fio.WriteLock(self.tmp, timeout=0.3):
            self.assertEqual(json.loads(self.lock.read_text(encoding="utf-8"))["pid"], os.getpid())
        self.assertFalse(self.lock.exists())


class SetupRegressions(TmpCase):
    def test_init_writes_the_real_script_path_into_claude_md(self):
        text = (self.ws / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertNotIn("<skill>", text)
        self.assertIn(CLI.resolve().as_posix(), text)

    def test_doctor_compares_zones_on_the_real_clock(self):
        from lib import cmd_setup
        name = cmd_setup.detect_iana_tz()
        if not name or dates._load_zone(name) is None:
            self.skipTest("the system time zone name is not detectable here")
        self.set_root("timezone", name)
        rep = json.loads(self.cli(["doctor", "--quick", "--json"], now="2026-10-12T09:00+05:45").stdout)
        self.assertFalse([w for w in rep["warnings"] if "this computer is on" in w], rep["warnings"])

    def test_an_unloadable_zone_is_reported_by_doctor_and_brief(self):
        self.set_root("timezone", "Europe/Nowhere")
        rep = json.loads(self.cli(["doctor", "--quick", "--json"]).stdout)
        self.assertTrue(any("cannot be loaded" in w for w in rep["warnings"]), rep["warnings"])
        r = self.cli(["brief", SUBJECT])
        claude = r.stdout.split("-- for Claude, do not read aloud --")[1]
        self.assertIn("TIME ZONE:", claude)


# ==========================================================================
# Rendering
# ==========================================================================

CODE_TEXT = ("Read the code.\n\n```rust\nfn main() {\n    let a = [1, 2];\n}\n```\n\n"
             "What does `a.len()` return?")


class RenderRegressions(unittest.TestCase):
    def setUp(self):
        self._old_now = os.environ.get("INDELIBLE_NOW")
        os.environ["INDELIBLE_NOW"] = NOW

    def tearDown(self):
        if self._old_now is None:
            os.environ.pop("INDELIBLE_NOW", None)
        else:
            os.environ["INDELIBLE_NOW"] = self._old_now

    def code_spec(self):
        spec = drills_spec()
        spec["items"][0]["text"] = CODE_TEXT
        return spec

    def test_markdown_keeps_code_verbatim(self):
        md = render.render_markdown(self.code_spec(), date="2026-10-15")
        self.assertIn("```rust\nfn main() {\n    let a = [1, 2];\n}\n```", md)
        self.assertIn("`a.len()`", md)
        self.assertNotIn("\\{", md)
        self.assertNotIn("\\`", md)

    def test_html_prints_code_in_pre_with_indentation(self):
        page = render.render_html(self.code_spec(), date="2026-10-15")
        self.assertIn('<pre class="code" data-lang="rust"><code>fn main() {\n    let a = [1, 2];\n}</code></pre>', page)
        self.assertIn("<code>a.len()</code>", page)
        self.assertNotIn("```", page)
        self.assertIn("monospace", page)

    def test_typst_uses_raw_blocks(self):
        src = render.render_typst(self.code_spec(), date="2026-10-15")
        self.assertIn('#raw(block: true, lang: "rust", "fn main() {\\n    let a = [1, 2];\\n}")', src)
        self.assertIn('#raw("a.len()")', src)
        self.assertEqual(typst_balance_problems(src), [])

    def test_answer_boxes_follow_the_answer_form(self):
        spec = drills_spec()
        spec["items"][0]["layer"] = "production"
        spec["items"][0]["asks"][0]["answer_form"] = "letter"
        spec["items"][1]["layer"] = "production"
        spec["items"][1]["asks"][0]["label"] = "Write the letter (A–D):"
        spec["items"][2]["layer"] = "production"
        spec["items"][3]["asks"][0]["answer_form"] = "none"
        m = render.build_model(spec, date="2026-10-15")
        boxes = [a["box_mm"] for g in m["groups"] for it in g["items"] for a in it["asks"]]
        self.assertEqual(boxes[:4], [12, render.SMALL_BOX_MM, 80, 0])
        md = render.render_markdown(spec, date="2026-10-15")
        block4 = md.split("**4a**", 1)[1].split("**5.**", 1)[0]
        self.assertNotIn("Answer:", block4)
        self.assertIn("Check:", block4)

    def test_rules_follow_the_profile_and_the_sheet_type(self):
        code_rules = render.rules(drills_spec(), "compiler", profile="code")
        self.assertTrue(any("in your editor" in r for r in code_rules))
        self.assertFalse(any("Answer on paper" in r for r in code_rules))
        repair = render.rules(drills_spec(type="repair"), "none")
        self.assertTrue(any("with the page open" in r for r in repair))
        self.assertFalse(any(r.startswith("Closed book: no notes") for r in repair))

    def test_a_sheet_built_ahead_without_a_block_has_a_blank_date(self):
        m = render.build_model(drills_spec(), date=False)
        self.assertEqual(m["date_line"], render.BLANK_DATE)
        self.assertNotIn(render.BLANK_DATE, render.render_html(drills_spec(), date="2026-10-15"))

    def test_no_private_markers_in_shipped_assets(self):
        self.assertIsNone(CYRILLIC.search(json.dumps(render.SAMPLE_SPEC, ensure_ascii=False)))
        page = (TEMPLATES_DIR / "html" / "sheet.html").read_text(encoding="utf-8")
        self.assertNotIn("Times New Roman", page)


# ==========================================================================
# Brief, stats, review, compact
# ==========================================================================

class ReportingRegressions(TmpCase):
    def test_pace_of_a_mixed_layer_sheet_is_labelled_mixed(self):
        items = [make_item(1, "T01", ["1a", "1b"], layer="reading"), make_item(2, "T04", ["2a", "2b"])]
        write_sheet(self.ws, SUBJECT, "ielts-diagnostic-01", "diagnostic", items)
        g = self.tmp / "g.json"
        g.write_text(json.dumps({"date": "2026-10-12", "start": "08:00", "stop": "08:10", "asks": [
            {"ask": a, "verdict": "right", "check": "filled"} for a in ("1a", "1b", "2a", "2b")]}), encoding="utf-8")
        self.cli(["grade", "record", SUBJECT, "ielts-diagnostic-01", "--from", g])
        pace = [ln for ln in self.cli(["brief", SUBJECT]).stdout.splitlines() if ln.startswith("PACE:")][0]
        self.assertIn("mixed sheet about 150 s per question", pace)
        self.assertNotIn("verbal", pace)
        self.assertNotIn("reading", pace)

    def add_defect(self, category, at):
        fio.append_jsonl(self.ws / "ledger.jsonl", {"v": 1, "id": "L-%04d" % (len(fio.read_jsonl(
            self.ws / "ledger.jsonl")) + 1), "kind": "defect", "subject": SUBJECT, "category": category,
            "what": "x", "fix_type": "lint", "fix": "y", "at": at})

    def test_tier_1_lists_only_taught_topics(self):
        # Only repaired (a mistake re-serve is a later tier), and only drilled: neither is a first recheck.
        add_exposure(self.ws, "T02", "2026-10-12T07:00+01:00", kind="repair")
        add_exposure(self.ws, "T03", "2026-10-12T07:00+01:00", kind="drill")
        add_exposure(self.ws, "T04", "2026-10-12T07:00+01:00", kind="teach")
        r = self.cli(["due", SUBJECT, "--list"], now="2026-10-14T07:00+01:00")
        tier1 = r.stdout.split("1. 2-day rechecks", 1)[1].split("2. ", 1)[0]
        self.assertIn("T04", tier1)
        self.assertNotIn("T02", tier1)
        self.assertNotIn("T03", tier1)

    def test_review_hygiene_counts_only_the_reviewed_week(self):
        self.add_defect("late_build", "2026-10-19T08:00+01:00")
        self.add_defect("late_build", "2026-10-21T08:00+01:00")
        r = self.cli(["review", "week", SUBJECT, "--week", "2026-W42"], now="2026-10-25T19:00+00:00")
        self.assertNotIn("late_build", r.stdout)
        r = self.cli(["review", "week", SUBJECT, "--week", "2026-W43"], now="2026-10-25T19:00+00:00")
        self.assertIn("late_build x2", r.stdout)

    def test_review_and_stats_share_one_execution_definition(self):
        def block(bid, start, status):
            return {"v": 1, "id": bid, "subject": SUBJECT, "kind": "teach", "start": start,
                    "end": start.replace("T07:00", "T08:00"), "window": None, "protected": False,
                    "measurement": False, "soft": False, "pair": None, "content": "", "status": status,
                    "cal": None, "moved_from": None, "miss_reason": None}
        self.save_blocks([block("B-20261019-ielts-1", "2026-10-19T07:00+01:00", "done"),
                          block("B-20261023-ielts-1", "2026-10-23T07:00+01:00", "planned")])
        now = "2026-10-21T09:00+01:00"
        r = self.cli(["review", "week", SUBJECT, "--week", "2026-W43"], now=now)
        self.assertIn("blocks 1/1 done, 0 moved, 0 missed, 1 still ahead", r.stdout)
        r = self.cli(["stats", SUBJECT], now=now)
        self.assertIn("blocks done 1 of 1 past", r.stdout)

    def test_compact_clears_old_scratch_files_and_reports_filed_inbox_files(self):
        tmpd = subject_dir(self.ws) / ".indelible" / "tmp"
        tmpd.mkdir(parents=True, exist_ok=True)
        old, new = tmpd / "ielts-cold-01.grades.json", tmpd / "ielts-cold-02.spec.json"
        old.write_text("{}", encoding="utf-8")
        new.write_text("{}", encoding="utf-8")
        long_ago = time.time() - 10 * 86400
        os.utime(str(old), (long_ago, long_ago))
        spec = drills_spec()
        self.assertEqual(new_sheet(self.ws, spec).returncode, 0)
        self.cli(["sheet", "lint", SUBJECT, spec["id"]])
        self.cli(["sheet", "build", SUBJECT, spec["id"], "--format", "md"])
        self.cli(["sheet", "issue", SUBJECT, spec["id"]])
        photo = self.ws / "inbox" / "IMG_0001.jpg"
        photo.write_bytes(b"\xff\xd8\xff\xe0 fake jpeg")
        self.cli(["scan", "ingest", SUBJECT, spec["id"], photo])
        r = self.cli(["compact", SUBJECT, "--dry-run"])
        self.assertIn("would clear 1 scratch file", r.stdout)
        self.assertTrue(old.exists())
        r = self.cli(["compact", SUBJECT])
        self.assertIn("cleared 1 scratch file", r.stdout)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())
        self.assertIn("inbox/ holds 1 file, 1 already filed as evidence", r.stdout)
        self.assertTrue(photo.exists())   # never deleted by a script


if __name__ == "__main__":
    unittest.main()
