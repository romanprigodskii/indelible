"""error list|repair|pass|fail|add and topic add|show|recompute, through the CLI.

Personas: A (IELTS, subject ``ielts``, date 2026-12-12) and C (statistics
final, subject ``stats``, date 2026-11-02, which caps the ladder).
"""

import json
import unittest

try:
    from test_grade import GradeBase, make_item, read_rows, secret_for, write_sheet
except ImportError:  # run as part of the tests package
    from tests.test_grade import GradeBase, make_item, read_rows, secret_for, write_sheet

from lib import io as fio

NOW = "2026-10-14T09:00+01:00"


class ErrorCommandTests(GradeBase):
    NOW = NOW

    def add(self, *extra, **kw):
        args = ["error", "add", self.sid, "--topic", "T04", "--kind", "slip", "--mode", "C",
                "--belief", "drops the negative when copying", "--account", "slip"]
        return self.cli(args + list(extra), **kw)

    def test_add_list_and_filters(self):
        r = self.add()
        self.assertIn("E-ielts-0001 opened: slip on T04 (C); first recheck due 2026-10-15", r.stdout)
        self.cli(["error", "add", self.sid, "--topic", "T01", "--kind", "belief", "--mode", "V",
                  "--belief", "reads 'gist' as 'detail'", "--account", "didn't know the word"])
        self.cli(["error", "add", self.sid, "--topic", "T02", "--kind", "shaky", "--mode", "E",
                  "--belief", "guessed between two options", "--account", "a guess"])
        errs = dict((e["id"], e) for e in self.errors())
        self.assertEqual(errs["E-ielts-0002"]["status"], "untreated")
        self.assertEqual((errs["E-ielts-0003"]["rung"], errs["E-ielts-0003"]["next_due"]), (1, "2026-10-17"))
        for e in errs.values():
            self.assertEqual(e["v"], 1)
            self.assertEqual(e["prov"], "practice")
            self.assertIsNone(e["answer_ref"])

        r = self.cli(["error", "list", self.sid])
        self.assertIn("3 mistakes on file", r.stdout)
        self.assertIn("1 need repair", r.stdout)
        lines = r.stdout.strip().split("\n")
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[1].startswith("E-ielts-0001"))  # the earliest due first

        r = self.cli(["error", "list", self.sid, "--status", "untreated"])
        self.assertEqual([l.split()[0] for l in r.stdout.strip().split("\n")[1:]], ["E-ielts-0002"])

        self.assertIn("(none match)", self.cli(["error", "list", self.sid, "--due"]).stdout)
        r = self.cli(["error", "list", self.sid, "--due"], now="2026-10-15T09:00+01:00")
        self.assertIn("E-ielts-0001", r.stdout)
        self.assertNotIn("E-ielts-0003", r.stdout)

        r = self.cli(["error", "list", self.sid, "--json", "--topic", "T02"])
        rows = json.loads(r.stdout)
        self.assertEqual([e["id"] for e in rows], ["E-ielts-0003"])

    def test_repair_pass_fail(self):
        self.cli(["error", "add", self.sid, "--topic", "T04", "--kind", "belief", "--mode", "D",
                  "--belief", "reads 'unless' as 'if'", "--account", "thought unless meant if"])
        r = self.cli(["error", "pass", self.sid, "E-ielts-0001"], expect=1)
        self.assertIn("untreated: repair it first", r.stdout)

        r = self.cli(["error", "repair", self.sid, "E-ielts-0001"], now="2026-10-14T20:30+01:00")
        self.assertIn("E-ielts-0001 repaired", r.stdout)
        e = self.errors()[0]
        self.assertEqual((e["status"], e["rung"], e["next_due"], e["repair_at"]),
                         ("spacing", 0, "2026-10-15", "2026-10-14T20:30+01:00"))
        exp = read_rows(self.sdir / "data" / "exposures.jsonl")
        self.assertEqual(exp[-1], {"v": 1, "topic": "T04", "at": "2026-10-14T20:30+01:00", "kind": "repair"})
        r = self.cli(["error", "repair", self.sid, "E-ielts-0001"], expect=1)
        self.assertIn("not waiting for repair", r.stdout)

        r = self.cli(["error", "pass", self.sid, "E-ielts-0001"], now="2026-10-15T09:00+01:00")
        self.assertIn("rung 1, due 2026-10-18", r.stdout)
        self.cli(["error", "pass", self.sid, "E-ielts-0001"], now="2026-10-18T09:00+01:00")
        e = self.errors()[0]
        self.assertEqual((e["rung"], e["next_due"], e["passes"]), (2, "2026-10-25", ["2026-10-15", "2026-10-18"]))
        r = self.cli(["error", "fail", self.sid, "E-ielts-0001"], now="2026-10-25T09:00+01:00")
        self.assertIn("needs repair", r.stdout)
        e = self.errors()[0]
        self.assertEqual((e["status"], e["rung"], e["next_due"], e["fails"]), ("untreated", 0, None, ["2026-10-25"]))

    def test_slip_fail_goes_back_to_rung_zero(self):
        self.add()
        self.cli(["error", "pass", self.sid, "E-ielts-0001"], now="2026-10-15T09:00+01:00")
        self.cli(["error", "fail", self.sid, "E-ielts-0001"], now="2026-10-18T09:00+01:00")
        e = self.errors()[0]
        self.assertEqual((e["status"], e["rung"], e["next_due"]), ("spacing", 0, "2026-10-19"))

    def test_unknown_error_and_topic(self):
        r = self.cli(["error", "pass", self.sid, "E-ielts-0099"], expect=2)
        self.assertIn("Unknown mistake", r.stderr)
        r = self.cli(["error", "add", self.sid, "--topic", "T99", "--kind", "slip", "--mode", "C",
                      "--belief", "x", "--account", "y"], expect=2)
        self.assertIn("Unknown topic", r.stderr)
        r = self.cli(["error", "add", self.sid, "--topic", "T01", "--kind", "slip", "--mode", "C",
                      "--belief", "b" * 121, "--account", "y"], expect=2)
        self.assertIn("limit is 120", r.stderr)

    def test_add_from_a_sheet_copies_the_key_entry_and_refuses_a_leaking_belief(self):
        items = [make_item(1, "T04", ["1a", "1b"]), make_item(2, "T01", ["2a"], layer="reading")]
        key = write_sheet(self.ws, self.sid, "ielts-cold-05", "cold", items)
        self.remember_key(key)
        r = self.cli(["error", "add", self.sid, "--topic", "T04", "--kind", "belief", "--mode", "V",
                      "--belief", "thinks the answer is %s" % secret_for("1b"), "--account", "looked since",
                      "--sheet", "ielts-cold-05", "--item", "1"], expect=1)
        self.assertIn("accepted answer", r.stdout)
        self.assertEqual(self.errors(), [])
        r = self.cli(["error", "add", self.sid, "--topic", "T04", "--kind", "belief", "--mode", "V",
                      "--belief", "reads 'albeit' as 'because'", "--account", "looked since",
                      "--sheet", "ielts-cold-05", "--item", "1"])
        e = self.errors()[0]
        self.assertEqual((e["sheet"], e["item"], e["prov"]), ("ielts-cold-05", 1, "measured"))
        self.assertEqual(e["answer_ref"], ".indelible/keys/errors/E-ielts-0001.json")
        copied = fio.read_json(self.sdir / ".indelible" / "keys" / "errors" / "E-ielts-0001.json")
        self.assertEqual(copied, {"1a": key["1a"], "1b": key["1b"]})
        self.cli(["error", "add", self.sid, "--topic", "T01", "--kind", "slip", "--mode", "C",
                  "--belief", "copied from the margin wrongly", "--account", "slip",
                  "--sheet", "ielts-cold-05", "--item", "2", "--ask", "2a"])
        copied = fio.read_json(self.sdir / ".indelible" / "keys" / "errors" / "E-ielts-0002.json")
        self.assertEqual(list(copied), ["2a"])
        self.cli(["error", "list", self.sid])
        self.assert_no_secrets()

    def test_shadow_subject_is_read_only(self):
        cfg = fio.read_json(self.ws / "indelible.json")
        cfg["subjects"][0]["state"] = "shadow"
        fio.write_json(self.ws / "indelible.json", cfg)
        r = self.add(expect=1)
        self.assertIn("shadow mode", r.stdout)
        self.cli(["error", "list", self.sid])


class DeadlineCapTests(GradeBase):
    """Persona C: the final is on 2026-11-02, so due dates stop 2 days before it."""
    PERSONA = "C"
    NOW = "2026-10-29T18:00-04:00"

    def setUp(self):
        GradeBase.setUp(self)
        self.sid = "stats"
        self.sdir = self.ws / self.sid

    def test_shaky_due_date_is_capped(self):
        r = self.cli(["error", "add", self.sid, "--topic", "T02", "--kind", "shaky", "--mode", "K",
                      "--belief", "unsure which interval formula applies", "--account", "a guess"])
        self.assertIn("due 2026-10-31", r.stdout)
        self.assertEqual(self.errors()[0]["next_due"], "2026-10-31")


class TopicCommandTests(GradeBase):
    NOW = NOW

    def subject(self):
        return fio.read_json(self.sdir / "subject.json")

    def test_add_show_recompute(self):
        r = self.cli(["topic", "add", self.sid, "T05", "--name", "Summary completion", "--layer", "reading",
                      "--weight", "0.15", "--floor", "T01,T02", "--confusable", "T04"])
        self.assertIn("T05 added to ielts: Summary completion · reading · weight 0.15", r.stdout)
        self.assertIn("T04 now lists T05", r.stdout)
        subj = self.subject()
        t5 = [t for t in subj["topics"] if t["id"] == "T05"][0]
        self.assertEqual(t5, {"id": "T05", "name": "Summary completion", "weight": 0.15, "layer": "reading",
                              "floor": ["T01", "T02"], "confusable_with": ["T04"], "scope": "in"})
        t4 = [t for t in subj["topics"] if t["id"] == "T04"][0]
        self.assertEqual(t4["confusable_with"], ["T01", "T05"])
        topics = fio.read_json(self.sdir / "data" / "topics.json")
        self.assertEqual(topics["T05"]["level"], 0)

        r = self.cli(["topic", "add", self.sid, "T05", "--name", "Again", "--layer", "reading"], expect=1)
        self.assertIn("already exists", r.stdout)
        r = self.cli(["topic", "add", self.sid, "T06", "--name", "Diagram labels", "--layer", "reading",
                      "--floor", "T00"])
        self.assertIn("not topics of ielts yet: T00", r.stdout)

        r = self.cli(["topic", "show", self.sid])
        self.assertIn("T05 Summary completion · reading · level 0 · no evidence yet", r.stdout)
        rows = json.loads(self.cli(["topic", "show", self.sid, "--json"]).stdout)
        self.assertEqual([x["id"] for x in rows], ["T01", "T02", "T03", "T04", "T05", "T06"])

        # Practice evidence written straight to attempts: show flags the stale store, recompute fixes it.
        for n in range(4):
            fio.append_jsonl(self.sdir / "data" / "attempts.jsonl", {
                "v": 1, "sheet": "ielts-sum-01-drills", "item": n + 1, "ask": "%da" % (n + 1), "topic": "T05",
                "layer": "reading", "instrument": "practice", "cold": False, "interval_h": None,
                "verdict": "right", "score": 1, "check": "filled", "least_sure": False,
                "at": "2026-10-14T07:30+01:00", "prov": "practice"})
        r = self.cli(["topic", "show", self.sid])
        self.assertIn("T05 Summary completion · reading · level 2 · practice 4/4 on ielts-sum-01-drills", r.stdout)
        self.assertIn("(stored 0)", r.stdout)
        r = self.cli(["topic", "recompute", self.sid])
        self.assertIn("T05 0 → 2", r.stdout)
        self.assertEqual(fio.read_json(self.sdir / "data" / "topics.json")["T05"]["level"], 2)
        r = self.cli(["topic", "recompute", self.sid])
        self.assertIn("no change", r.stdout)

    def test_bad_topic_id_refused(self):
        r = self.cli(["topic", "add", self.sid, "T 7", "--name", "x", "--layer", "verbal"], expect=2)
        self.assertIn("Topic id", r.stderr)


if __name__ == "__main__":
    unittest.main()
