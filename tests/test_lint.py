"""The sheet checker: every rule L1-L9 and W1-W2 has a failing and a passing fixture.

Most rules are checked in-process with ``lint.check(spec, ctx)``; the rules
that read the workspace (L4 sense words, L5 blocks, L7 exposures and errors,
L8 the sealed key) are also run through the CLI.
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from helpers import make_ws, run
    from test_sheet import (NOW, SUBJECT, add_exposure, answers_for, assert_no_key_text,
                            cold_spec, drills_spec, new_sheet, sheet_row, subject_dir, theory_spec)
except ImportError:  # run as part of the tests package
    from tests.helpers import make_ws, run
    from tests.test_sheet import (NOW, SUBJECT, add_exposure, answers_for, assert_no_key_text,
                                  cold_spec, drills_spec, new_sheet, sheet_row, subject_dir, theory_spec)

from lib import dates, lint
from lib import io as fio


def ctx(**over):
    """A lint context for persona A where everything passes."""
    base = {
        "topics": {"T01": "Matching headings", "T02": "True, false or not given", "T03": "Task 1 overview",
                   "T04": "Paraphrase"},
        "sense": lint.sense_words({}),
        "block_size": (3, 8),
        "budget": (48.0, "0.8 × the default session of 60 min"),
        "now": dates.parse_iso(NOW),
        "exposures": [{"v": 1, "topic": "T04", "at": "2026-10-10T08:00+01:00", "kind": "teach"},
                      {"v": 1, "topic": "T01", "at": "2026-10-10T08:00+01:00", "kind": "teach"}],
        "errors": [],
        "topics_state": {},
        "window": (44.0, 72.0),
        "key": None,
    }
    base.update(over)
    return base


def result(spec, rule, **over):
    c = ctx(**over)
    if c.get("key") is None and "key" not in over:
        c["key"] = answers_for(spec)
    for r in lint.check(spec, c):
        if r["rule"] == rule:
            return r
    raise AssertionError("no result for %s" % rule)


class Base(unittest.TestCase):
    def setUp(self):
        self._old_now = os.environ.get("INDELIBLE_NOW")
        os.environ["INDELIBLE_NOW"] = NOW

    def tearDown(self):
        if self._old_now is None:
            os.environ.pop("INDELIBLE_NOW", None)
        else:
            os.environ["INDELIBLE_NOW"] = self._old_now

    def status(self, spec, rule, **over):
        return result(spec, rule, **over)["status"]


# ==========================================================================
# In-process: one failing and one passing fixture per rule
# ==========================================================================

class RuleTests(Base):
    def test_all_rules_pass_on_the_good_fixtures(self):
        for spec in (drills_spec(), cold_spec(), theory_spec()):
            rs = lint.check(spec, ctx(key=answers_for(spec)))
            self.assertEqual([r["rule"] for r in rs], lint.RULES)
            bad = [lint.format_line(r) for r in rs if r["status"] != "PASS"]
            self.assertEqual(bad, [], spec["id"])

    def test_l1_structure(self):
        self.assertEqual(self.status(drills_spec(), "L1"), "PASS")
        self.assertEqual(self.status(drills_spec(items=[]), "L1"), "FAIL")
        spec = drills_spec()
        spec["items"][1]["asks"] = []
        self.assertEqual(self.status(spec, "L1"), "FAIL")
        spec = drills_spec()
        spec["items"][2]["asks"][0]["id"] = "1a"
        r = result(spec, "L1")
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("1a is used twice", r["detail"])
        spec = drills_spec()
        spec["items"][0]["asks"][0]["label"] = "  "
        self.assertEqual(self.status(spec, "L1"), "FAIL")

    def test_l2_check_lines(self):
        spec = drills_spec()
        spec["items"][3]["asks"][0]["check"] = False
        r = result(spec, "L2")
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("4a", r["detail"])
        spec = cold_spec()
        del spec["items"][0]["asks"][0]["check"]
        self.assertEqual(self.status(spec, "L2"), "FAIL")
        # Exempt types pass without check lines.
        spec = theory_spec()
        self.assertFalse(spec["items"][0]["asks"][0]["check"])
        self.assertEqual(self.status(spec, "L2"), "PASS")
        self.assertEqual(self.status(drills_spec(), "L2"), "PASS")

    def test_l3_unlabelled(self):
        self.assertEqual(self.status(cold_spec(), "L3"), "PASS")
        r = result(cold_spec(title="Paraphrase recheck"), "L3")
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("topic name 'Paraphrase' in the title", r["detail"])
        self.assertEqual(self.status(cold_spec(title="t04 recheck"), "L3"), "FAIL")
        spec = cold_spec(blocks=[{"title": "Matching headings", "items": [1, 2, 3, 4]}])
        self.assertEqual(self.status(spec, "L3"), "FAIL")
        spec = cold_spec()
        spec["items"][2]["asks"][0]["label"] = "Heading for T01:"
        self.assertEqual(self.status(spec, "L3"), "FAIL")
        # Two same-topic items next to each other.
        spec = cold_spec()
        spec["items"][1], spec["items"][2] = spec["items"][2], spec["items"][1]
        r = result(spec, "L3")
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("next to each other", r["detail"])
        # Not a measuring type: topic names are allowed.
        self.assertEqual(self.status(drills_spec(title="Paraphrase drills"), "L3"), "PASS")
        # Whole words only: "paraphrased" is not the topic name.
        self.assertEqual(self.status(cold_spec(title="Sentences, paraphrased"), "L3"), "PASS")

    def test_l4_terms(self):
        reading = lint.sense_words({"sense_list": ["gist", "claim"]})
        spec = drills_spec()
        spec["items"][0]["text"] = "What is the gist of the writer's claim?"
        r = result(spec, "L4", sense=reading)
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("'gist'", r["detail"])
        self.assertIn("'claim'", r["detail"])
        spec["terms"] = [{"term": "gist", "resolution": "defined_on:ielts-headings-01-theory"},
                         {"term": "Claim", "resolution": "glossary"}]
        self.assertEqual(self.status(spec, "L4", sense=reading), "PASS")
        # Two-word entries and titles count; code spans do not.
        spec = drills_spec(title="At  least two ways")
        self.assertIn("at least", result(spec, "L4")["detail"])
        spec = drills_spec(title="Using `mean()` and `range`")
        self.assertEqual(self.status(spec, "L4"), "PASS")
        # Whole words only.
        spec = drills_spec()
        spec["items"][0]["text"] = "The results were invalidated by the meaning."
        self.assertEqual(self.status(spec, "L4"), "PASS")
        # The subject's own sense list and lexicon are enforced too.
        spec = drills_spec()
        spec["items"][0]["text"] = "Find the gerund."
        sense = lint.sense_words({"sense_list": ["gerund"], "lexicon": [{"term": "cohesive device"}]})
        self.assertEqual(self.status(spec, "L4", sense=sense), "FAIL")
        self.assertIn("cohesive device", sense)

    def test_l4_theory_terms_must_be_defined_here(self):
        self.assertEqual(self.status(theory_spec(), "L4"), "PASS")
        spec = theory_spec(terms=[{"term": "paraphrase", "resolution": "defined_on:other-sheet"}])
        self.assertEqual(self.status(spec, "L4"), "FAIL")
        spec = theory_spec()
        spec["theory"]["words"] = []
        self.assertEqual(self.status(spec, "L4"), "FAIL")
        # On a non-theory sheet, "defined_here" needs the word on the sheet.
        spec = drills_spec(title="Paraphrase practice", terms=[{"term": "paraphrase", "resolution": "defined_here"}])
        self.assertEqual(self.status(spec, "L4"), "FAIL")

    def test_l5_budget(self):
        self.assertEqual(self.status(drills_spec(est_min=48), "L5"), "PASS")
        r = result(drills_spec(est_min=87), "L5")
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("over the budget", r["detail"])
        self.assertEqual(self.status(drills_spec(est_min=87, type="mock"), "L5"), "PASS")
        self.assertEqual(self.status(drills_spec(est_min=20), "L5", budget=(16.0, "block")), "FAIL")

    def test_l6_drill_blocks(self):
        self.assertEqual(self.status(drills_spec(), "L6"), "PASS")
        spec = drills_spec()
        spec["items"][4]["op"] = "swap-tense"
        r = result(spec, "L6")
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("mixes operations", r["detail"])
        spec = drills_spec(blocks=[{"title": "Block A", "items": [1, 2, 3, 4, 5]}])
        self.assertIn("item 6 is in no block", result(spec, "L6")["detail"])
        spec = drills_spec(blocks=[{"title": "Block A", "items": [1, 2, 3]}, {"title": "Block B", "items": [3, 4, 5, 6]}])
        self.assertIn("more than one block", result(spec, "L6")["detail"])
        spec = drills_spec(n=4, blocks=[{"title": "Block A", "items": [1, 2]}, {"title": "Block B", "items": [3, 4]}])
        self.assertIn("allowed 3–8", result(spec, "L6")["detail"])
        self.assertEqual(self.status(drills_spec(blocks=[]), "L6"), "FAIL")
        self.assertEqual(self.status(cold_spec(), "L6"), "PASS")

    def test_l7_cold_validity(self):
        self.assertEqual(self.status(cold_spec(), "L7"), "PASS")
        taught_10h_ago = [{"topic": "T04", "at": "2026-10-11T23:00+01:00", "kind": "teach"},
                          {"topic": "T01", "at": "2026-10-10T08:00+01:00", "kind": "teach"}]
        r = result(cold_spec(), "L7", exposures=taught_10h_ago)
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("T04", r["detail"])
        self.assertIn("24 h", r["detail"])
        never = [{"topic": "T01", "at": "2026-10-10T08:00+01:00", "kind": "teach"}]
        self.assertEqual(self.status(cold_spec(), "L7", exposures=never), "FAIL")
        belief = {"v": 1, "id": "E-ielts-0001", "topic": "T02", "kind": "belief", "status": "untreated"}
        spec = cold_spec()
        spec["items"].append({"n": 5, "topic": "T02", "layer": "reading", "op": "recall",
                              "origin": "error:E-ielts-0001", "text": "Heavy rain delayed the trains.",
                              "asks": [{"id": "5a", "label": "Your answer:", "check": True}]})
        r = result(spec, "L7", errors=[belief])
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("E-ielts-0001 is untreated", r["detail"])
        repaired = dict(belief, status="spacing", repair_at="2026-10-11T08:00+01:00", next_due="2026-10-12")
        self.assertEqual(self.status(spec, "L7", errors=[repaired], key=answers_for(spec)), "PASS")
        self.assertEqual(self.status(spec, "L7", errors=[]), "FAIL")  # an unknown error id
        self.assertEqual(self.status(drills_spec(), "L7", exposures=taught_10h_ago), "PASS")

    def test_l8_key_leak_names_only_the_ask(self):
        spec = drills_spec()
        key = answers_for(spec)
        self.assertEqual(self.status(spec, "L8", key=key), "PASS")
        spec["items"][1]["text"] = "Prices climbed quickly (think: ZEPHYRINE?) in the spring."
        key["2a"]["accept"] = ["zephyrine"]
        r = result(spec, "L8", key=key)
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("2a", r["detail"])
        self.assertNotIn("zephyrine", r["detail"].lower())
        # Short answers (under 3 characters) do not count ...
        spec = drills_spec()
        key = answers_for(spec)
        key["1a"]["accept"] = ["up"]
        self.assertEqual(self.status(spec, "L8", key=key), "PASS")
        # ... but an answer inside a longer word does: the contract's test is "appears" (a substring).
        key["2a"]["accept"] = ["rid"]   # inside "bridge"
        r = result(spec, "L8", key=key)
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("2a", r["detail"])
        # Check hints and block titles are visible text too.
        spec = drills_spec()
        spec["items"][0]["asks"][0]["check_hint"] = "It starts with quillo... quillomatic"
        key = answers_for(spec, words=["quillomatic"])
        self.assertEqual(self.status(spec, "L8", key=key), "FAIL")
        self.assertEqual(result(spec, "L8", key={})["status"], "PASS")
        self.assertEqual(result(drills_spec(), "L8", key=None)["status"], "FAIL")

    def test_l9_least_sure(self):
        self.assertEqual(self.status(drills_spec(), "L9"), "PASS")
        self.assertEqual(self.status(drills_spec(least_sure=False), "L9"), "FAIL")
        spec = cold_spec()
        del spec["least_sure"]
        self.assertEqual(self.status(spec, "L9"), "FAIL")
        self.assertEqual(self.status(theory_spec(least_sure=False), "L9"), "PASS")

    def test_w1_formula_in_block_title(self):
        self.assertEqual(self.status(drills_spec(), "W1"), "PASS")
        spec = drills_spec()
        spec["blocks"][0]["title"] = "Block A: y = 2x + 1"
        self.assertEqual(self.status(spec, "W1"), "WARN")
        self.assertTrue(lint.passed(lint.check(spec, ctx(key=answers_for(spec)))), "a WARN never fails lint")

    def test_w2_sentences_first(self):
        self.assertEqual(self.status(drills_spec(), "W2"), "PASS")
        spec = drills_spec()
        spec["items"][0]["layer"] = "procedural"
        self.assertEqual(self.status(spec, "W2"), "WARN")
        spec = drills_spec()
        for it in spec["items"]:
            it["layer"] = "procedural"
        self.assertEqual(self.status(spec, "W2"), "PASS", "no verbal items: nothing to put first")

    def test_a_malformed_spec_fails_instead_of_crashing(self):
        spec = drills_spec()
        spec["blocks"] = "not a list"
        rs = lint.check(spec, ctx(key=answers_for(spec)))
        self.assertFalse(lint.passed(rs))


# ==========================================================================
# Through the CLI (workspace data, exit codes, status updates)
# ==========================================================================

class CliLintTests(Base):
    def setUp(self):
        Base.setUp(self)
        self.tmp = Path(tempfile.mkdtemp(prefix="indelible-lint-"))
        self.ws = make_ws(self.tmp, "A")

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)
        Base.tearDown(self)

    def lint(self, sheet_id, *extra):
        return run(["sheet", "lint", SUBJECT, sheet_id] + list(extra), ws=self.ws, now=NOW)

    def line(self, r, rule):
        for ln in r.stdout.splitlines():
            if ln.startswith(rule + " "):
                return ln
        self.fail("no %s line in:\n%s" % (rule, r.stdout))

    def test_prints_one_line_per_rule_and_sets_status(self):
        spec = drills_spec()
        self.assertEqual(new_sheet(self.ws, spec).returncode, 0)
        r = self.lint(spec["id"])
        self.assertEqual(r.returncode, 0, r.stdout)
        for rule in lint.RULES:
            self.assertRegex(self.line(r, rule), r"^%s (PASS|WARN) " % rule)
        self.assertIn("lint PASS: ielts-drills-01", r.stdout)
        row = sheet_row(self.ws, spec["id"])
        self.assertEqual((row["lint"], row["status"]), ("PASS", "linted"))
        data = json.loads(self.lint(spec["id"], "--json").stdout)
        self.assertEqual(data["result"], "PASS")
        self.assertEqual(len(data["rules"]), 11)

    def test_undefined_seed_word_fails_l4_and_blocks_the_build(self):
        from lib import ws as wsmod
        subj = wsmod.Workspace(self.ws).subject(SUBJECT)
        cfg = subj.load()
        cfg["sense_list"] = ["gist"]
        subj.save(cfg)
        spec = drills_spec()
        spec["items"][2]["text"] = "What is the gist of the second paragraph?"
        self.assertEqual(new_sheet(self.ws, spec).returncode, 0)
        r = self.lint(spec["id"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL", self.line(r, "L4"))
        self.assertIn("'gist'", self.line(r, "L4"))
        self.assertIn("lint FAIL: ielts-drills-01 (L4)", r.stdout)
        self.assertEqual(sheet_row(self.ws, spec["id"])["lint"], "FAIL")
        b = run(["sheet", "build", SUBJECT, spec["id"], "--format", "md"], ws=self.ws, now=NOW)
        self.assertEqual(b.returncode, 1)

    def test_subject_sense_list_is_read(self):
        from lib import ws as wsmod
        subj = wsmod.Workspace(self.ws).subject(SUBJECT)
        cfg = subj.load()
        cfg["sense_list"] = ["bridge"]
        subj.save(cfg)
        spec = drills_spec()
        self.assertEqual(new_sheet(self.ws, spec).returncode, 0)
        r = self.lint(spec["id"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("'bridge'", self.line(r, "L4"))

    def test_cold_item_on_a_topic_taught_10h_ago_fails_l7(self):
        add_exposure(self.ws, "T01", "2026-10-10T08:00+01:00")
        add_exposure(self.ws, "T04", "2026-10-11T23:00+01:00")
        spec = cold_spec()
        self.assertEqual(new_sheet(self.ws, spec).returncode, 0)
        r = self.lint(spec["id"])
        self.assertEqual(r.returncode, 1)
        l7 = self.line(r, "L7")
        self.assertTrue(l7.startswith("L7 FAIL"), l7)
        self.assertIn("T04", l7)
        self.assertNotIn("(T01)", l7)

    def test_cold_items_in_the_window_pass_l7(self):
        add_exposure(self.ws, "T01", "2026-10-10T08:00+01:00")
        add_exposure(self.ws, "T04", "2026-10-10T08:00+01:00")
        spec = cold_spec()
        self.assertEqual(new_sheet(self.ws, spec).returncode, 0)
        r = self.lint(spec["id"])
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("L7 PASS", r.stdout)

    def test_cold_item_on_an_untreated_belief_fails_l7_and_build(self):
        add_exposure(self.ws, "T01", "2026-10-10T08:00+01:00")
        add_exposure(self.ws, "T04", "2026-10-10T08:00+01:00")
        fio.write_jsonl(subject_dir(self.ws) / "data" / "errors.jsonl", [{
            "v": 1, "id": "E-ielts-0007", "opened": "2026-10-10", "sheet": "ielts-drills-01", "item": 3,
            "topic": "T02", "kind": "belief", "mode": "V", "belief": "reads 'albeit' as 'because'",
            "account": "no account", "named_least_sure": False, "status": "untreated", "repair_at": None,
            "rung": 0, "next_due": None, "passes": [], "fails": [], "answer_ref": None, "prov": "measured"}])
        spec = cold_spec()
        spec["items"].append({"n": 5, "topic": "T02", "layer": "reading", "op": "recall",
                              "origin": "error:E-ielts-0007", "text": "Our neighbours painted the fence green.",
                              "asks": [{"id": "5a", "label": "Your answer:", "check": True}]})
        self.assertEqual(new_sheet(self.ws, spec).returncode, 0)
        r = self.lint(spec["id"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("E-ielts-0007 is untreated", self.line(r, "L7"))
        b = run(["sheet", "build", SUBJECT, spec["id"], "--format", "html"], ws=self.ws, now=NOW)
        self.assertEqual(b.returncode, 1)

    def test_visible_accept_string_fails_l8_naming_only_the_ask(self):
        spec = drills_spec()
        spec["items"][4]["text"] = "Heavy rain delayed the trains; the word brindlewick fits here."
        self.assertEqual(new_sheet(self.ws, spec).returncode, 0)
        r = self.lint(spec["id"])
        self.assertEqual(r.returncode, 1)
        l8 = self.line(r, "L8")
        self.assertTrue(l8.startswith("L8 FAIL"), l8)
        self.assertIn("5a", l8)
        self.assertNotIn("1a", l8)
        assert_no_key_text(self, r)
        r = self.lint(spec["id"], "--json")
        assert_no_key_text(self, r)

    def test_blocks_mixing_ops_fail_l6(self):
        spec = drills_spec()
        spec["items"][1]["op"] = "find-the-verb"
        self.assertEqual(new_sheet(self.ws, spec).returncode, 0)
        r = self.lint(spec["id"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("mixes operations", self.line(r, "L6"))

    def test_topic_name_in_a_cold_sheet_title_fails_l3(self):
        add_exposure(self.ws, "T01", "2026-10-10T08:00+01:00")
        add_exposure(self.ws, "T04", "2026-10-10T08:00+01:00")
        spec = cold_spec(title="Matching headings recheck")
        self.assertEqual(new_sheet(self.ws, spec).returncode, 0)
        r = self.lint(spec["id"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("Matching headings", self.line(r, "L3"))

    def test_budget_from_flag_and_from_the_linked_block(self):
        spec = drills_spec(est_min=30)
        self.assertEqual(new_sheet(self.ws, spec).returncode, 0)
        self.assertEqual(self.lint(spec["id"], "--budget-min", "40").returncode, 0)
        r = self.lint(spec["id"], "--budget-min", "20")
        self.assertEqual(r.returncode, 1)
        self.assertIn("over the budget of 20 min", self.line(r, "L5"))
        block = {"v": 1, "id": "B-20261012-ielts-1", "subject": SUBJECT, "kind": "teach",
                 "start": "2026-10-12T07:00+01:00", "end": "2026-10-12T07:30+01:00", "window": None,
                 "protected": False, "measurement": False, "soft": False, "pair": None, "content": "",
                 "status": "planned", "cal": None, "moved_from": None, "miss_reason": None}
        fio.write_jsonl(Path(self.ws) / "plan" / "blocks.jsonl", [block])
        spec2 = drills_spec("ielts-drills-02", est_min=30, block="B-20261012-ielts-1")
        self.assertEqual(new_sheet(self.ws, spec2).returncode, 0)
        r = self.lint(spec2["id"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("B-20261012-ielts-1", self.line(r, "L5"))

    def test_a_failing_relint_sends_a_rendered_sheet_back_to_built(self):
        add_exposure(self.ws, "T01", "2026-10-10T08:00+01:00")
        add_exposure(self.ws, "T04", "2026-10-10T08:00+01:00")
        spec = cold_spec()
        self.assertEqual(new_sheet(self.ws, spec).returncode, 0)
        self.assertEqual(self.lint(spec["id"]).returncode, 0)
        self.assertEqual(run(["sheet", "build", SUBJECT, spec["id"], "--format", "md"], ws=self.ws, now=NOW).returncode, 0)
        # A chat explanation of T04 an hour ago contaminates the recheck.
        add_exposure(self.ws, "T04", "2026-10-12T08:00+01:00", kind="chat")
        r = self.lint(spec["id"])
        self.assertEqual(r.returncode, 1)
        row = sheet_row(self.ws, spec["id"])
        self.assertEqual((row["lint"], row["status"]), ("FAIL", "built"))
        self.assertEqual(run(["sheet", "issue", SUBJECT, spec["id"]], ws=self.ws, now=NOW).returncode, 1)


if __name__ == "__main__":
    unittest.main()
