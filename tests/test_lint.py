"""The sheet checker: every rule L1-L12 and W1-W5 has a failing and a passing fixture.

Most rules are checked in-process with ``lint.check(spec, ctx)``; the rules
that read the workspace (L4 sense words, L5 blocks, L7 exposures and errors,
L8 the sealed key) are also run through the CLI.
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
        # A lexicon word is never everyday. A drills sheet has no theory.words, so the
        # message names the resolutions it can use instead.
        spec = drills_spec(terms=[{"term": "paraphrase", "resolution": "everyday"}])
        spec["items"][0]["text"] = "Write a paraphrase of the first sentence."
        r = result(spec, "L4", sense=["paraphrase"], lexicon={"paraphrase"})
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("resolve it defined_on:<sheet> or glossary, or use plain words: 'paraphrase'", r["detail"])
        self.assertNotIn("theory.words", r["detail"])
        r = result(dict(spec, type="cold"), "L4", sense=["paraphrase"], lexicon={"paraphrase"})
        self.assertIn("resolve it defined_on:<sheet>, glossary or measured_here", r["detail"])

    def test_l4_code_is_read_for_the_subjects_own_words_only(self):
        spec = drills_spec()
        spec["items"][0]["text"] = ("What does `len([4, 1, 7])` give? Then `range(3)`?\n\n"
                                    "```\nb = [1]\nb.append(6)\n```")
        self.assertEqual(self.status(spec, "L4"), "PASS", "seed words in code are identifiers")
        r = result(spec, "L4", lexicon={"len", ".append"})
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("'.append'", r["detail"])
        self.assertIn("'len'", r["detail"])
        self.assertEqual(self.status(spec, "L4", sense_list={"len"}), "FAIL", "the sense list counts too")
        spec["terms"] = [{"term": "len", "resolution": "defined_on:ielts-code-01-theory"},
                         {"term": ".append", "resolution": "defined_on:ielts-code-01-theory"}]
        self.assertEqual(self.status(spec, "L4", lexicon={"len", ".append"}), "PASS")
        # Unicode symbols in prose are words too, once the subject lists them.
        spec = drills_spec()
        spec["items"][0]["text"] = "Data: n = 25, x̄ = 48, σ = 10. Work out x̄ − 2σ."
        self.assertEqual(self.status(spec, "L4"), "PASS")
        r = result(spec, "L4", sense=lint.sense_words({"lexicon": ["x̄", "σ"]}))
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("'x̄'", r["detail"])

    def test_l4_defined_on_names_a_sheet_that_defines_the_word(self):
        reading = lint.sense_words({"sense_list": ["gist"]})
        spec = drills_spec()
        spec["items"][0]["text"] = "What is the gist of the second paragraph?"
        spec["terms"] = [{"term": "gist", "resolution": "defined_on:never-built-sheet"}]
        # With no sheet list in the context (a pure check), the id is not looked up.
        self.assertEqual(self.status(spec, "L4", sense=reading), "PASS")
        sheets = {"ielts-headings-01-theory": {"gist", "heading"}}
        r = result(spec, "L4", sense=reading, sheet_words=sheets)
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("'gist' (never-built-sheet)", r["detail"])
        spec["terms"][0]["resolution"] = "defined_on:ielts-headings-01-theory"
        self.assertEqual(self.status(spec, "L4", sense=reading, sheet_words=sheets), "PASS")
        r = result(spec, "L4", sense=reading, sheet_words={"ielts-headings-01-theory": {"heading"}})
        self.assertEqual(r["status"], "FAIL", "the sheet exists but never defines the word")
        self.assertIn("'gist' (ielts-headings-01-theory)", r["detail"])

    def test_l4_reads_check_hints(self):
        spec = drills_spec()
        spec["items"][1]["asks"][0]["check_hint"] = "Write the meaning of 'paraphrase' you used."
        r = result(spec, "L4")
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("'paraphrase'", r["detail"])
        spec["terms"] = [{"term": "paraphrase", "resolution": "defined_on:ielts-theory-01"}]
        self.assertEqual(self.status(spec, "L4", sheet_words={"ielts-theory-01": {"paraphrase"}}), "PASS")

    def test_l4_everyday_never_covers_a_word_the_sheet_teaches(self):
        def with_valid(body, where=2, title=None):
            spec = theory_spec()
            spec["terms"].append({"term": "valid", "resolution": "everyday"})
            spec["theory"]["sections"][where]["body"] = body
            if title:
                spec["theory"]["sections"][where]["title"] = title
            return spec
        # One plain use in a box passes.
        self.assertEqual(self.status(with_valid("Only a valid ticket gets you in."), "L4"), "PASS")
        # Used 3 times, in a section title, or in a pencil question: it is being taught.
        r = result(with_valid("A valid reading keeps the idea. Is it valid? Yes, valid."), "L4")
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("one it teaches", r["detail"])
        self.assertIn("'valid'", r["detail"])
        self.assertEqual(self.status(with_valid("Keep the idea.", title="When a reading is valid"), "L4"), "FAIL")
        spec = with_valid("Keep the idea.")
        spec["items"][0]["text"] = "Is the second sentence a valid way to say the first?"
        self.assertEqual(self.status(spec, "L4"), "FAIL")
        # A drills sheet teaches nothing: there "everyday" is the builder's call.
        spec = drills_spec(terms=[{"term": "valid", "resolution": "everyday"}])
        spec["items"][0]["text"] = "A valid ticket. A valid pass. A valid card."
        self.assertEqual(self.status(spec, "L4"), "PASS")

    def test_l4_names_the_resolutions_when_one_is_missing(self):
        spec = drills_spec()
        spec["items"][0]["text"] = "What is the median of the three prices?"
        r = result(spec, "L4")
        self.assertIn("used without a resolution (use defined_here, defined_on:<sheet-id>, glossary, everyday, "
                      "measured_here, or plain words): 'median'", r["detail"])

    def test_l4_theory_terms_must_be_defined_here(self):
        self.assertEqual(self.status(theory_spec(), "L4"), "PASS")
        spec = theory_spec(terms=[{"term": "paraphrase", "resolution": "defined_on:other-sheet"}])
        r = result(spec, "L4")
        self.assertEqual(r["status"], "FAIL")
        self.assertNotIn("everyday", r["detail"], "the theory message never points at the loophole")
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
        self.assertEqual(self.status(drills_spec(est_min=20), "L5", budget=(16.0, "block")), "FAIL")

    def test_l5_a_measurement_keeps_to_its_own_minutes(self):
        mock = drills_spec(est_min=87, type="mock")
        self.assertEqual(self.status(mock, "L5", budget=(165.0, "the exam's 165 min (format.minutes)")), "PASS")
        r = result(mock, "L5", budget=(55.0, "--budget-min 55"))
        self.assertEqual(r["status"], "FAIL", "an explicit budget binds a measurement too")
        self.assertIn("over the budget of 55 min", r["detail"])
        self.assertIn("split a part Claude wrote into sittings", r["detail"])
        self.assertNotIn("cut questions", r["detail"])
        self.assertEqual(self.status(drills_spec(est_min=87, type="diagnostic"), "L5", budget=None), "PASS")
        # The pace floor holds on a measurement Claude wrote: 6 verbal questions are 8.5 minutes,
        # not 3. It is never cut, so the message doesn't say to cut questions.
        r = result(drills_spec(est_min=3, type="diagnostic"), "L5", budget=None)
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("under the pace floor of 9 min", r["detail"])
        self.assertIn("a measurement is never cut", r["detail"])
        self.assertNotIn("cut questions", r["detail"])

    def test_l5_an_official_paper_keeps_the_exams_clock(self):
        # A listening test as a checkpoint: 4 parts of 10 questions in the exam's 30 minutes.
        # At 75 s a question the pace floor would be 51 min; the exam times these, not the pace.
        items = []
        for p in range(4):
            items.append({"n": p + 1, "topic": "T01", "layer": "verbal", "op": "listen",
                          "origin": "official:cambridge-18-test-1",
                          "text": "Test 1, Listening part %d, questions %d-%d" % (p + 1, p * 10 + 1, p * 10 + 10),
                          "asks": [{"id": "%d%s" % (p + 1, chr(97 + k)), "label": "Q%d:" % (p * 10 + k + 1),
                                    "check": True} for k in range(10)]})
        spec = drills_spec(est_min=30, type="checkpoint")
        spec["items"], spec["blocks"] = items, []
        self.assertEqual(lint.pace_floor(spec, {}), 1)
        self.assertEqual(self.status(spec, "L5", budget=None), "PASS")
        self.assertEqual(self.status(spec, "L5", budget=(35.0, "block of 45 min, less 10 to record")), "PASS")
        # A question Claude adds to it is still counted at the learner's pace.
        spec["items"].append(dict(drills_spec()["items"][0], n=5, origin="new"))
        self.assertEqual(lint.pace_floor(spec, {}), 2.25)

    def test_l5_the_estimate_is_checked_against_the_pace(self):
        spec = drills_spec(est_min=1)
        for it in spec["items"]:
            it["layer"] = "reading"          # 70 s each: 6 × 70 s / 60 + 1 = 8 min
        r = result(spec, "L5", budget=(2.0, "--budget-min 2"))
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("est_min 1 is under the pace floor of 8 min", r["detail"])
        r = result(spec, "L5", budget=None)
        self.assertEqual(r["status"], "FAIL", "the floor holds when no budget is known")
        spec["est_min"] = 8
        self.assertEqual(self.status(spec, "L5", budget=None), "PASS")
        self.assertEqual(self.status(spec, "L5", budget=(8.0, "b")), "PASS")
        # The subject's own pace counts, and each question of an item counts.
        self.assertEqual(self.status(spec, "L5", budget=None, pace_s={"reading": 100}), "FAIL")
        spec["items"][0]["asks"].append({"id": "1b", "label": "The verb you changed:", "check": True,
                                         "check_hint": "Read the new sentence aloud with your answer in it"})
        self.assertEqual(self.status(spec, "L5", budget=None), "FAIL")   # 7 × 70 s / 60 + 1 = 9.2
        self.assertEqual(self.status(drills_spec(est_min=1, type="triage"), "L5", budget=None), "PASS",
                         "a triage sheet is not sized by pace")

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

    def test_l7_judges_a_recheck_again_by_its_window_and_a_later_serve_by_24_h_only(self):
        # T04's recheck on 8 Oct left it below 3; its fix sheet came 33 h ago.
        exposures = [{"topic": "T04", "at": "2026-10-06T08:00+01:00", "kind": "teach"},
                     {"topic": "T04", "at": "2026-10-11T00:00+01:00", "kind": "repair"},
                     {"topic": "T01", "at": "2026-10-10T08:00+01:00", "kind": "teach"}]
        below = {"T04": {"level": 2, "last_cold": "2026-10-08T08:00+01:00", "taught_at": "2026-10-06T08:00+01:00"}}
        r = result(cold_spec(), "L7", exposures=exposures, topics_state=below)
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("T04): seen 33 h ago; the recheck window opens at 44 h", r["detail"])
        # At mastery 3 the same serve is its level-4 recheck: no window, only the 24-hour rule.
        owned = {"T04": dict(below["T04"], level=3)}
        self.assertEqual(self.status(cold_spec(), "L7", exposures=exposures, topics_state=owned), "PASS")
        # A fix 3 days back: the recheck again has closed; the level-4 recheck still passes.
        exposures[1]["at"] = "2026-10-09T08:00+01:00"
        r = result(cold_spec(), "L7", exposures=exposures, topics_state=below)
        self.assertIn("the recheck window closed at 72 h", r["detail"])
        self.assertEqual(self.status(cold_spec(), "L7", exposures=exposures, topics_state=owned), "PASS")

    def test_l7_a_recheck_topic_needs_two_questions(self):
        spec = cold_spec()
        del spec["items"][3]                                   # T04, T01, T04: T01 once
        r = result(spec, "L7")
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("topic T01 has 1 question: a 2-day recheck counts only with at least 2", r["detail"])
        self.assertNotIn("T04 has", r["detail"])
        spec["items"][1]["asks"].append({"id": "2b", "label": "Your second answer:", "check": True,
                                         "check_hint": "Read the sentence again with your answer in it"})
        self.assertEqual(self.status(spec, "L7"), "PASS", "every question on the topic counts")
        # A fixed mistake on the topic is pooled with it at marking, so it counts too.
        spec = cold_spec()
        del spec["items"][3]
        spec["items"].append({"n": 5, "topic": "T01", "layer": "reading", "op": "recall",
                              "origin": "error:E-ielts-0001", "text": "Heavy rain delayed the trains.",
                              "asks": [{"id": "5a", "label": "Your answer:", "check": True}]})
        fixed = {"v": 1, "id": "E-ielts-0001", "topic": "T01", "kind": "belief", "status": "spacing",
                 "repair_at": "2026-10-10T08:00+01:00", "next_due": "2026-10-12"}
        self.assertEqual(self.status(spec, "L7", errors=[fixed]), "PASS")

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

    def hinted(self, hint, spec=None):
        spec = spec or drills_spec()
        spec["items"][1]["asks"][0]["check_hint"] = hint
        return spec

    def test_l10_a_hint_never_sends_the_learner_to_find_their_own_mistake(self):
        self.assertEqual(self.status(drills_spec(), "L10"), "PASS")
        for hint in ("Find the mistake in your solution.", "Look for any errors in your working",
                     "Can you spot your slip?", "Double-check it", "Redo the calculation",
                     "Solve it again", "Check your answer.", "Verify", "How sure are you?",
                     "Is there a mistake?", "Find what's wrong", "Find the error.",
                     "Is there an error? Look again.", "Find the error in your code",
                     "Check your work for mistakes", "Check for errors", "Where did you go wrong?",
                     "Which step is wrong?", "Did you make a mistake?", "Make sure it's right",
                     "Check your answer again", "Check your result", "Solve again",
                     "Do the question again from scratch"):
            r = result(self.hinted(hint), "L10")
            self.assertEqual(r["status"], "FAIL", hint)
            self.assertIn("2a", r["detail"])
        self.assertEqual(self.status(self.hinted("Find the mistake", cold_spec()), "L10"), "FAIL",
                         "measuring sheets too")

    def test_l10_subject_words_are_not_a_search(self):
        for hint in ("Put your answer back into the first line: does it hold?",
                     "Find the standard error from the other formula: same value?",
                     "Find the error term at x = 2: is it 0?",
                     "Does your confidence interval contain the sample mean?",
                     "Check your answer's units against the question",
                     "Read the sentence again with your answer in it.",
                     "Is the percentage error under 5%?", "Does the error message name your line?",
                     "Check for error bars that overlap zero", "Search the log for errors",
                     "Find the error of the mean from the other formula", "Run the tests again",
                     "Add error handling and feed it an empty file: does it still exit 0?"):
            self.assertEqual(self.status(self.hinted(hint), "L10"), "PASS", hint)
        spec = self.hinted("Find the mistake")
        spec["items"][1]["asks"][0]["check"] = False
        self.assertEqual(self.status(spec, "L10"), "PASS", "a hint with no check line is never printed")

    def test_w3_new_topic_checks_need_a_check_the_learner_can_run(self):
        # topics_state is empty in ctx(): every topic is below mastery 3
        for hint in ("Which step would you be pushed on? Do it another way.", "Name your weakest step",
                     "Work it out a different way"):
            r = result(self.hinted(hint), "W3")
            self.assertEqual(r["status"], "WARN", hint)
            self.assertIn("2a", r["detail"])
        spec = drills_spec()
        del spec["items"][2]["asks"][0]["check_hint"]
        r = result(spec, "W3")
        self.assertEqual(r["status"], "WARN")
        self.assertIn("no hint on 3a", r["detail"])
        spec = self.hinted("Do it another way")
        self.assertTrue(lint.passed(lint.check(spec, ctx(key=answers_for(spec)))), "a WARN never fails lint")

    def test_w3_owned_topics_may_use_a_second_method(self):
        spec = self.hinted("Which step would you be pushed on? Do it another way.")
        for level in (3, "3p", 4, 5):
            self.assertEqual(self.status(spec, "W3", topics_state={"T04": {"level": level}}), "PASS", level)
        self.assertEqual(self.status(spec, "W3", topics_state={"T04": {"level": 2}}), "WARN")
        self.assertEqual(self.status(theory_spec(), "W3"), "PASS", "theory has no check lines")

    def test_w3_subject_words_are_not_a_second_method(self):
        for hint in ("Is your weakest acid the one with the largest pKa in the table?",
                     "Does the weakest link in the chain carry the full tension?",
                     "If the cart is pushed on a level track, does your answer give a = F/m?"):
            self.assertEqual(self.status(self.hinted(hint), "W3"), "PASS", hint)

    def test_w3_judges_each_question_by_its_own_topic(self):
        spec = self.hinted("Do it another way")
        spec["items"][1]["asks"][0]["topic"] = "T09"
        levels = {"T04": {"level": 4}, "T09": {"level": 1}}
        self.assertEqual(self.status(spec, "W3", topics_state=levels), "WARN")
        levels = {"T04": {"level": 1}, "T09": {"level": 4}}
        spec = self.hinted("Do it another way")
        for it in spec["items"]:
            it["asks"][0]["topic"] = "T09"
        self.assertEqual(self.status(spec, "W3", topics_state=levels), "PASS")
        self.assertEqual(self.status(spec, "W3", topics_state={"T09": "garbled"}), "WARN",
                         "an unreadable state counts as not owned")

    def test_w4_the_worked_case_shows_its_check(self):
        self.assertEqual(self.status(theory_spec(), "W4"), "PASS")
        spec = theory_spec()
        spec["theory"]["sections"][0]["body"] = "Start: The shop shut at noon.\n\nOther words: The store closed."
        self.assertEqual(self.status(spec, "W4"), "WARN")
        spec["theory"]["sections"][0]["title"] = "A worked case, with its check"
        self.assertEqual(self.status(spec, "W4"), "WARN", "a title is not a check step")
        spec["theory"]["sections"][0]["body"] += "\n\nPack your checklist."
        self.assertEqual(self.status(spec, "W4"), "WARN", "a word starting with 'check' is not a check step")
        spec["theory"]["sections"][0]["body"] += "\n\nStep 3. Check: read both aloud."
        self.assertEqual(self.status(spec, "W4"), "PASS")
        spec = theory_spec()
        spec["theory"]["sections"] = [s for s in spec["theory"]["sections"] if s["kind"] != "worked"]
        self.assertEqual(self.status(spec, "W4"), "WARN", "no worked case at all")
        self.assertEqual(self.status(drills_spec(), "W4"), "PASS")

    def test_l6_gate_after_leaves_three_items_before_and_two_after(self):
        spec = drills_spec(n=12)                              # two blocks of 6
        spec["blocks"][0]["gate_after"] = 4
        self.assertEqual(self.status(spec, "L6"), "PASS")
        for bad in (2, 5, 9, "4"):
            spec["blocks"][0]["gate_after"] = bad
            r = result(spec, "L6")
            self.assertEqual(r["status"], "FAIL", bad)
            self.assertIn("block 1: gate_after must be one of its items", r["detail"])
        spec["blocks"][0]["gate_after"] = 3
        self.assertEqual(self.status(spec, "L6"), "PASS", "the default place, written out")

    def test_w5_a_reading_sheet_allows_time_to_read(self):
        self.assertEqual(self.status(theory_spec(), "W5"), "PASS")
        # 451 words to read and one pencil question: the pace floor alone (3 min) passes L5.
        spec = theory_spec(est_min=3)
        spec["theory"]["sections"][1]["body"] = " ".join(["word"] * 400)
        self.assertEqual(self.status(spec, "L5"), "PASS")
        r = result(spec, "W5")
        self.assertEqual(r["status"], "WARN")
        self.assertIn("words over 120 a minute", r["detail"])
        self.assertIn("at least 6 min", r["detail"])
        spec["est_min"] = 8    # 451 / 90 + 1.25 + 1, rounded up: the builder's own sum for a second language
        self.assertEqual(self.status(spec, "W5"), "PASS")
        for t in ("example", "repair"):
            self.assertEqual(self.status(theory_spec(est_min=3, type=t, theory=spec["theory"]), "W5"), "WARN", t)
        # External pages are named, not printed; drills are sized by pace alone.
        self.assertEqual(self.status(theory_spec(est_min=3, type="external", theory=spec["theory"]), "W5"), "PASS")
        self.assertEqual(self.status(drills_spec(), "W5"), "PASS")

    def test_l11_a_worked_case_comes_before_the_rule(self):
        self.assertEqual(self.status(theory_spec(), "L11"), "PASS")
        spec = theory_spec()
        spec["theory"]["sections"] = [s for s in spec["theory"]["sections"] if s["kind"] != "worked"]
        r = result(spec, "L11")
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("no worked section", r["detail"])
        spec = theory_spec()
        secs = spec["theory"]["sections"]
        secs[0], secs[1] = secs[1], secs[0]
        r = result(spec, "L11")
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("the rule comes before the first worked case", r["detail"])
        spec = theory_spec(type="repair")
        spec["theory"]["sections"] = [{"kind": "rule", "title": "The fix", "body": "Keep the idea."}]
        self.assertEqual(self.status(spec, "L11"), "FAIL", "a repair sheet too")
        spec["type"] = "external"
        self.assertEqual(self.status(spec, "L11"), "PASS", "external pages are named, never copied")
        self.assertEqual(self.status(drills_spec(), "L11"), "PASS")

    def test_l12_drills_ask_only_for_operations_a_sheet_has_shown(self):
        spec = drills_spec()                                   # T04, op swap-word
        self.assertEqual(self.status(spec, "L12"), "PASS", "no sheets read")
        self.assertEqual(self.status(spec, "L12", shown_ops={}), "PASS", "no teaching sheet for T04")
        r = result(spec, "L12", shown_ops={"T04": {"complete"}})
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("item 1 (T04): 'swap-word'", r["detail"])
        self.assertIn("never rename an op", r["detail"])
        self.assertEqual(self.status(spec, "L12", shown_ops={"T04": {"complete", "swap-word"}}), "PASS")
        for it in spec["items"]:
            it["origin"] = "official:book"
        self.assertEqual(self.status(spec, "L12", shown_ops={"T04": set()}), "PASS", "only new items")
        self.assertEqual(self.status(cold_spec(), "L12", shown_ops={"T04": set()}), "PASS", "drills only")

    def test_shown_ops_come_from_pencils_and_worked_sections(self):
        theory = theory_spec()
        external = theory_spec("ielts-external-01", type="external")
        external["items"][0].update(topic="T01", op="pick-heading")
        shown = lint.shown_ops([({}, theory), ({}, external), ({}, drills_spec(n=3))])
        self.assertEqual(shown, {"T04": {"complete", "swap-word"}, "T01": {"pick-heading", "swap-word"}})

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
        self.assertEqual(len(data["rules"]), len(lint.RULES))

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

    def test_defined_on_needs_the_sheet_on_file_and_issued_first(self):
        theory = theory_spec()                     # defines 'paraphrase'
        spec = drills_spec(title="Paraphrase practice",
                           terms=[{"term": "paraphrase", "resolution": "defined_on:ielts-theory-01"}])
        self.assertEqual(new_sheet(self.ws, spec).returncode, 0)
        r = self.lint(spec["id"])
        self.assertEqual(r.returncode, 1, "no sheet ielts-theory-01 yet")
        self.assertIn("'paraphrase' (ielts-theory-01)", self.line(r, "L4"))
        # Built ahead with its theory (rendered, not issued yet): lint passes ...
        self.assertEqual(new_sheet(self.ws, theory).returncode, 0)
        self.assertEqual(self.lint(theory["id"]).returncode, 0)
        self.assertEqual(run(["sheet", "build", SUBJECT, theory["id"], "--format", "md"], ws=self.ws, now=NOW).returncode, 0)
        self.assertEqual(self.lint(spec["id"]).returncode, 0)
        self.assertEqual(run(["sheet", "build", SUBJECT, spec["id"], "--format", "md"], ws=self.ws, now=NOW).returncode, 0)
        # ... but the drills go out only after the theory.
        r = run(["sheet", "issue", SUBJECT, spec["id"]], ws=self.ws, now=NOW)
        self.assertEqual(r.returncode, 1)
        self.assertIn("defined on ielts-theory-01, which is rendered: issue that sheet first", r.stdout + r.stderr)
        self.assertEqual(run(["sheet", "issue", SUBJECT, theory["id"]], ws=self.ws, now=NOW).returncode, 0)
        self.assertEqual(run(["sheet", "issue", SUBJECT, spec["id"]], ws=self.ws, now=NOW).returncode, 0)

    def test_drills_ask_only_for_what_the_theory_worked(self):
        theory = theory_spec()
        theory["theory"]["sections"][0]["ops"] = []           # its pencil op 'complete' only
        self.assertEqual(new_sheet(self.ws, theory).returncode, 0)
        spec = drills_spec()                                  # op 'swap-word' on T04
        self.assertEqual(new_sheet(self.ws, spec).returncode, 0)
        r = self.lint(spec["id"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("'swap-word'", self.line(r, "L12"))
        # The theory is rebuilt with a worked case for that operation.
        theory["theory"]["sections"][0]["ops"] = ["swap-word"]
        self.assertEqual(new_sheet(self.ws, theory, extra=["--replace"]).returncode, 0)
        r = self.lint(spec["id"])
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(self.line(r, "L12").startswith("L12 PASS"))
        # A malformed ops list is refused when the spec is sealed.
        theory["theory"]["sections"][0]["ops"] = "swap-word"
        r = new_sheet(self.ws, theory, extra=["--replace"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ops must be a list", r.stdout + r.stderr)

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

    def test_the_subjects_own_words_are_read_in_code(self):
        from lib import ws as wsmod
        subj = wsmod.Workspace(self.ws).subject(SUBJECT)
        cfg = subj.load()
        cfg["sense_list"] = ["append"]
        subj.save(cfg)
        spec = drills_spec()
        spec["items"][2]["text"] = "What is in b after `b = [1]; b.append(6)`?"
        self.assertEqual(new_sheet(self.ws, spec).returncode, 0)
        r = self.lint(spec["id"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("'append'", self.line(r, "L4"))

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

    def plan_block(self, kind, start, minutes):
        r = run(["plan", "add", SUBJECT, "--kind", kind, "--start", start, "--min", str(minutes)],
                ws=self.ws, now=NOW)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout.split()[0]

    def test_a_measurement_keeps_to_its_blocks_minutes_at_lint_and_issue(self):
        bid = self.plan_block("diagnostic", "2026-10-13T07:00+01:00", 60)
        spec = drills_spec("ielts-diagnostic-02", est_min=90, type="diagnostic", blocks=[])
        self.assertEqual(new_sheet(self.ws, spec, extra=["--block", bid]).returncode, 0)
        r = self.lint(spec["id"])
        self.assertEqual(r.returncode, 1)
        l5 = self.line(r, "L5")
        self.assertIn("over the budget of 50 min (block %s of 60 min, less 10 to record)" % bid, l5)
        self.assertIn("split a part Claude wrote into sittings", l5)
        r = self.lint(spec["id"], "--budget-min", "55")
        self.assertIn("over the budget of 55 min", self.line(r, "L5"))
        # Linted against a longer part, it is still refused at issue into the 60-minute block.
        self.assertEqual(self.lint(spec["id"], "--budget-min", "100").returncode, 0)
        self.assertEqual(run(["sheet", "build", SUBJECT, spec["id"], "--format", "md"], ws=self.ws, now=NOW).returncode, 0)
        r = run(["sheet", "issue", SUBJECT, spec["id"], "--block", bid], ws=self.ws, now=NOW)
        self.assertEqual(r.returncode, 1)
        self.assertIn("over the budget of 50 min", r.stdout + r.stderr)
        self.assertNotIn("cut questions", r.stdout + r.stderr)
        self.assertEqual(sheet_row(self.ws, spec["id"])["status"], "rendered")
        # A mock with no block keeps to the exam's own minutes (persona A: 165).
        mock = drills_spec("ielts-mock-01", est_min=170, type="mock", blocks=[])
        self.assertEqual(new_sheet(self.ws, mock).returncode, 0)
        self.assertIn("over the budget of 165 min (the exam's 165 min", self.line(self.lint(mock["id"]), "L5"))

    def test_sheets_on_one_block_are_sized_together(self):
        bid = self.plan_block("teach", "2026-10-13T07:00+01:00", 60)
        one = drills_spec("ielts-x-01", est_min=35)
        two = drills_spec("ielts-x-02", est_min=35)
        self.assertEqual(new_sheet(self.ws, one, extra=["--block", bid]).returncode, 0)
        self.assertIn("within 48 min", self.line(self.lint(one["id"]), "L5"))
        self.assertEqual(run(["sheet", "build", SUBJECT, one["id"], "--format", "md"], ws=self.ws, now=NOW).returncode, 0)
        self.assertEqual(run(["sheet", "issue", SUBJECT, one["id"], "--block", bid], ws=self.ws, now=NOW).returncode, 0)
        self.assertEqual(new_sheet(self.ws, two, extra=["--block", bid]).returncode, 0)
        r = self.lint(two["id"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("over the budget of 13 min (0.8 × block %s of 60 min, less 35 min on ielts-x-01)" % bid,
                      self.line(r, "L5"))
        # The issue check adds them up too, even when lint was given a looser budget.
        self.assertEqual(self.lint(two["id"], "--budget-min", "40").returncode, 0)
        self.assertEqual(run(["sheet", "build", SUBJECT, two["id"], "--format", "md"], ws=self.ws, now=NOW).returncode, 0)
        r = run(["sheet", "issue", SUBJECT, two["id"], "--block", bid], ws=self.ws, now=NOW)
        self.assertEqual(r.returncode, 1)
        self.assertIn("less 35 min on ielts-x-01", r.stdout + r.stderr)
        # A dropped sheet no longer takes the block's minutes.
        self.assertEqual(run(["sheet", "void", SUBJECT, one["id"], "--reason", "not sat"], ws=self.ws,
                             now=NOW).returncode, 0)
        self.assertEqual(run(["sheet", "issue", SUBJECT, two["id"], "--block", bid], ws=self.ws, now=NOW).returncode, 0)

    def test_a_sheet_built_for_a_block_takes_its_minutes_only_once_issued(self):
        # The builder links each sheet to its block at build. A practice sheet built at
        # the close and waiting as rendered may still be cut, so the sheet issued first
        # (the recheck, at the open) is never refused for it; the one issued last is.
        bid = self.plan_block("teach", "2026-10-13T07:00+01:00", 60)   # 48 min
        ahead = drills_spec("ielts-x-01", est_min=40)
        first = drills_spec("ielts-x-02", est_min=10)
        for spec in (ahead, first):
            self.assertEqual(new_sheet(self.ws, spec, extra=["--block", bid]).returncode, 0)
            self.assertEqual(self.lint(spec["id"], "--budget-min", "40").returncode, 0)
            self.assertEqual(run(["sheet", "build", SUBJECT, spec["id"], "--format", "md"], ws=self.ws,
                                 now=NOW).returncode, 0)
        self.assertEqual(sheet_row(self.ws, ahead["id"])["block"], bid)
        r = run(["sheet", "issue", SUBJECT, first["id"], "--block", bid], ws=self.ws, now=NOW)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run(["sheet", "issue", SUBJECT, ahead["id"], "--block", bid], ws=self.ws, now=NOW)
        self.assertEqual(r.returncode, 1)
        self.assertIn("over the budget of 38 min (0.8 × block %s of 60 min, less 10 min on ielts-x-02)" % bid,
                      r.stdout + r.stderr)

    def test_a_mixed_sheet_built_ahead_is_judged_at_its_block_and_again_at_issue(self):
        # Built at Monday's close for Wednesday's block: a slip due Tuesday on T04, a
        # topic drilled an hour ago. Judged now it fails; at the block's start it holds.
        add_exposure(self.ws, "T04", "2026-10-10T08:00+01:00")
        add_exposure(self.ws, "T04", "2026-10-12T08:00+01:00", kind="drill")
        r = run(["error", "add", SUBJECT, "--topic", "T04", "--kind", "slip", "--mode", "C",
                 "--belief", "copied the wrong line", "--account", "slip"], ws=self.ws, now=NOW)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        eid = re.search(r"E-ielts-\d+", r.stdout).group(0)
        spec = cold_spec("ielts-mixed-01", type="mixed", title="Part A")
        for it in spec["items"]:
            it["origin"] = "new"
        spec["items"][0]["origin"] = "error:%s" % eid
        self.assertEqual(new_sheet(self.ws, spec).returncode, 0)
        l7 = self.line(self.lint(spec["id"], "--budget-min", "20"), "L7")
        self.assertTrue(l7.startswith("L7 FAIL"), l7)
        self.assertIn("not due until", l7)
        bid = self.plan_block("teach", "2026-10-14T07:00+01:00", 30)
        r = self.lint(spec["id"], "--budget-min", "20", "--block", bid)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("eligible at the start of block %s" % bid, self.line(r, "L7"))
        self.assertEqual(run(["sheet", "build", SUBJECT, spec["id"], "--format", "md"], ws=self.ws,
                             now=NOW).returncode, 0)
        # T04 is drilled again the evening before: issue judges the mixed sheet again.
        add_exposure(self.ws, "T04", "2026-10-13T20:00+01:00", kind="drill")
        r = run(["sheet", "issue", SUBJECT, spec["id"], "--block", bid], ws=self.ws, now="2026-10-14T06:30+01:00")
        self.assertEqual(r.returncode, 1)
        self.assertIn("a recheck or mistake item is not valid when it will be sat", r.stdout + r.stderr)
        self.assertIn("less than 24 h", r.stdout + r.stderr)
        self.assertEqual(sheet_row(self.ws, spec["id"])["status"], "rendered")

    def test_the_open_sessions_minutes_count_on_its_own_block(self):
        bid = self.plan_block("teach", "2026-10-12T09:30+01:00", 30)   # a slot split: 30 recheck + 30
        spec = drills_spec(est_min=30)
        self.assertEqual(new_sheet(self.ws, spec, extra=["--block", bid]).returncode, 0)
        self.assertIn("over the budget of 24 min", self.line(self.lint(spec["id"]), "L5"))
        r = run(["session", "open", SUBJECT, "--planned", "60", "--block", bid], ws=self.ws, now=NOW)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Budget: 36.7 work minutes", r.stdout)
        # The session's work minutes, as session open printed them, not 0.8 × its 60 (48).
        r = self.lint(spec["id"])
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("within 36.7 min (the session's 36.7 work minutes on block %s)" % bid, self.line(r, "L5"))
        # A 45-minute sheet linted against a looser budget is refused at issue.
        big = drills_spec("ielts-drills-02", est_min=45)
        self.assertEqual(new_sheet(self.ws, big, extra=["--block", bid]).returncode, 0)
        self.assertEqual(self.lint(big["id"], "--budget-min", "50").returncode, 0)
        self.assertEqual(run(["sheet", "build", SUBJECT, big["id"], "--format", "md"], ws=self.ws,
                             now=NOW).returncode, 0)
        r = run(["sheet", "issue", SUBJECT, big["id"], "--block", bid], ws=self.ws, now=NOW)
        self.assertEqual(r.returncode, 1)
        self.assertIn("over the budget of 36.7 min (the session's 36.7 work minutes on block %s)" % bid,
                      r.stdout + r.stderr)
        self.assertEqual(sheet_row(self.ws, big["id"])["status"], "rendered")

    def test_a_session_opened_short_of_its_block_has_less_time(self):
        bid = self.plan_block("teach", "2026-10-12T09:00+01:00", 90)   # 0.8 × 90 = 72
        spec = drills_spec(est_min=30)
        self.assertEqual(new_sheet(self.ws, spec, extra=["--block", bid]).returncode, 0)
        self.assertIn("within 72 min", self.line(self.lint(spec["id"]), "L5"))
        r = run(["session", "open", SUBJECT, "--planned", "30", "--block", bid], ws=self.ws, now=NOW)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Budget: 18.5 work minutes", r.stdout)
        r = self.lint(spec["id"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("over the budget of 18.5 min (the session's 18.5 work minutes on block %s)" % bid,
                      self.line(r, "L5"))

    def test_the_pace_floor_reads_the_subjects_pace(self):
        from lib import ws as wsmod
        spec = drills_spec(est_min=2)          # 6 verbal questions at 75 s: 8.5 min
        self.assertEqual(new_sheet(self.ws, spec).returncode, 0)
        r = self.lint(spec["id"], "--budget-min", "40")
        self.assertEqual(r.returncode, 1)
        self.assertIn("under the pace floor of 9 min", self.line(r, "L5"))
        subj = wsmod.Workspace(self.ws).subject(SUBJECT)
        cfg = subj.load()
        cfg["pace_s"] = dict(cfg.get("pace_s") or {}, verbal=10)   # 6 × 10 s / 60 + 1 = 2 min
        subj.save(cfg)
        self.assertEqual(self.lint(spec["id"], "--budget-min", "40").returncode, 0)

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
