"""End to end, through the CLI only (tests.helpers.run).

Persona A (IELTS Academic, scheduled, Google Calendar) runs a full cycle:
setup -> a drills sheet built, checked, issued, taken, marked -> session close
-> 49 hours later the brief shows the 2-day recheck and the slip due -> a
recheck sheet (with the slip re-served) -> level 3 -> plan, calendar diff,
.ics, weekly review, compaction and the brief size cap.

Persona D (Rust, on demand, no date, no calendar) runs the quick path.

Every accepted answer in these keys is a made-up word, so the tests can prove
that no key text reaches any output except ``key open``.
"""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from helpers import REPO_DIR, run
except ImportError:  # run as part of the tests package
    from tests.helpers import REPO_DIR, run

FIXTURES = REPO_DIR / "evals" / "fixtures"
PLAIN_ID_RE = re.compile(r"\b(?:E-[a-z0-9-]+-\d{3,}|S-[a-z0-9-]+-\d{3,}|B-\d{8}-[a-z0-9-]+-\d+|L-\d{3,})\b")
CLAUDE_LINE = "-- for Claude, do not read aloud --"

# Persona A timeline (Europe/Lisbon, UTC+01:00 in October before the clock change).
T0 = "2026-10-12T07:00+01:00"          # Monday: first session opens
T1 = "2026-10-14T08:00+01:00"          # Wednesday, 49 h later: the 2-day recheck
T_PLAN = "2026-10-14T20:00+01:00"      # Wednesday evening: planning
T_WEEK_END = "2026-10-18T19:00+01:00"  # Sunday evening: review and compaction

DRILL_KEY = {"1a": "velvetrock", "2a": "quinsbarrow", "3a": "dromellic",
             "4a": "harrowvane", "5a": "pellucinth", "6a": "ostrevane"}
COLD_KEY = {"1a": "brackenwise", "2a": "tallowmere", "3a": "fenwickly", "4a": "ostrevane"}
ALL_ACCEPTED = sorted(set(DRILL_KEY.values()) | set(COLD_KEY.values()))

# Sentences chosen to use none of the words in assets/lists/sense_seed.txt.
DRILL_TEXTS = ["The ferry left the harbour at dawn.", "Few people came to the first meeting.",
               "The museum opens early on Fridays.",
               "Paragraph A tells how the town grew after the railway came.",
               "Paragraph B tells why the mill closed.",
               "Paragraph C tells what the river looks like in winter."]
COLD_TEXTS = ["Paragraph A tells how the bridge was built.", "Paragraph B tells why the harbour silted up.",
              "Paragraph C tells who paid for the new school.",
              "Paragraph D tells what the river looks like in winter."]


def nested(dotted_map, skip=()):
    """{"target.date": x} -> {"target": {"date": x}}."""
    out = {}
    for dotted, value in dotted_map.items():
        if dotted in skip:
            continue
        node = out
        parts = dotted.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = value
    return out


def learner_part(brief_text):
    """The part of the brief a plain-vocabulary learner may hear (above the Claude line)."""
    return brief_text.split(CLAUDE_LINE)[0]


class E2EBase(unittest.TestCase):
    persona_file = None

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="indelible-e2e-"))
        self.ws = self.tmp / "study"
        self.fx = json.loads((FIXTURES / self.persona_file).read_text(encoding="utf-8"))
        self.outputs = []   # (command, stdout + stderr) of every run except key open

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def cli(self, args, now, code=0, stdin=None, record=True):
        args = [str(a) for a in args]
        r = run(args, ws=None if args[0] == "init" else self.ws, now=now, stdin=stdin)
        if record:
            self.outputs.append((" ".join(args[:3]), r.stdout + r.stderr))
        if code is not None:
            self.assertEqual(r.returncode, code, "%s -> %s\nstdout: %s\nstderr: %s"
                             % (" ".join(args), r.returncode, r.stdout, r.stderr))
        return r

    def setup_workspace(self, subject_id, title, profile, root_keys):
        fx = self.fx
        self.cli(["init", self.ws, "--timezone", fx["timezone"]], T0)
        for key in root_keys:
            self.cli(["set", "root", key, json.dumps(fx["expected"]["root"][key])], T0)
        src = self.tmp / ("%s-subject.json" % subject_id)
        src.write_text(json.dumps(nested(fx["expected"]["subject"], skip=("id", "title", "profile")),
                                  ensure_ascii=False), encoding="utf-8")
        self.cli(["subject", "add", subject_id, "--title", title, "--profile", profile, "--from", src], T0)

    def write_builder_files(self, subject_id, spec, key):
        """What the builder subagent does: spec and answers into <subject>/.indelible/tmp/."""
        tmpd = self.ws / subject_id / ".indelible" / "tmp"
        tmpd.mkdir(parents=True, exist_ok=True)
        sp = tmpd / ("%s.spec.json" % spec["id"])
        ap = tmpd / ("%s.answers.json" % spec["id"])
        sp.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        answers = dict((k, {"accept": [v], "check": "the sentence still reads true",
                            "solution": "worked: " + v}) for k, v in key.items())
        ap.write_text(json.dumps(answers, ensure_ascii=False), encoding="utf-8")
        return sp, ap

    def assert_no_accepted_answers(self):
        for cmd, text in self.outputs:
            for word in ALL_ACCEPTED:
                self.assertNotIn(word, text, "an accepted answer appeared in the output of: %s" % cmd)

    def assert_plain_brief(self, text):
        self.assertIsNone(PLAIN_ID_RE.search(learner_part(text)),
                          "an id is shown above the Claude line:\n%s" % text)


class PersonaAFullCycle(E2EBase):
    persona_file = "persona-a.json"

    def drills_spec(self):
        def item(n, topic, layer, op, label):
            return {"n": n, "topic": topic, "layer": layer, "op": op, "origin": "new", "text": DRILL_TEXTS[n - 1],
                    "asks": [{"id": "%da" % n, "label": label, "check": True,
                              "check_hint": "Read the sentence again with your answer in it"}]}
        items = [item(n, "T04", "verbal", "swap-word", "Write it with a new verb:") for n in (1, 2, 3)]
        items += [item(n, "T01", "reading", "pick-heading", "Heading for this paragraph:") for n in (4, 5, 6)]
        return {"v": 1, "id": "ielts-drills-01", "type": "drills", "subject": "ielts",
                "title": "Other words, same idea", "est_min": 15, "tools": "none", "answer_form": "short",
                "items": items,
                "blocks": [{"title": "Block A: swap one word", "items": [1, 2, 3]},
                           {"title": "Block B: pick a heading", "items": [4, 5, 6]}],
                "terms": [], "theory": None, "least_sure": True}

    def cold_spec(self, slip_id):
        items = []
        for n, origin in ((1, "cold:T01"), (2, "cold:T01"), (3, "cold:T01"), (4, "error:%s" % slip_id)):
            items.append({"n": n, "topic": "T01", "layer": "reading", "op": "pick-heading", "origin": origin,
                          "text": COLD_TEXTS[n - 1],
                          "asks": [{"id": "%da" % n, "label": "Heading for this paragraph:", "check": True,
                                    "check_hint": "Read the paragraph again under your heading"}]})
        return {"v": 1, "id": "ielts-cold-01", "type": "cold", "subject": "ielts", "title": "2-day recheck",
                "est_min": 8, "tools": "none", "answer_form": "short", "items": items, "blocks": [],
                "terms": [], "theory": None, "least_sure": True}

    def sheet_cycle(self, spec, key, typed_text, now_build, now_ingest):
        """sheet new -> lint -> build (md) -> issue -> key refused -> scan ingest -> key open."""
        sid = spec["id"]
        sp, ap = self.write_builder_files("ielts", spec, key)
        r = self.cli(["sheet", "new", "ielts", sid, "--spec", sp, "--answers", ap], now_build)
        self.assertRegex(r.stdout.strip(), r"^%s built: %d questions, ~%d min, key sealed sha256:[0-9a-f]{12}$"
                         % (re.escape(sid), len(key), spec["est_min"]))
        self.assertFalse(ap.exists(), "sheet new must delete the answers file")
        r = self.cli(["sheet", "lint", "ielts", sid], now_build)
        self.assertNotIn("FAIL", r.stdout)
        self.assertIn("lint PASS", r.stdout)
        r = self.cli(["sheet", "build", "ielts", sid, "--format", "md"], now_build)
        built = Path(r.stdout.strip().splitlines()[-1])
        self.assertTrue(built.is_file(), r.stdout)
        sheet_text = built.read_text(encoding="utf-8")
        self.assertIn("Least sure of", sheet_text)
        self.assertIn("Check:", sheet_text)
        for word in ALL_ACCEPTED:
            self.assertNotIn(word, sheet_text, "key text on the printed sheet")
        self.cli(["sheet", "issue", "ielts", sid], now_build)
        r = self.cli(["key", "open", "ielts", sid], now_build, code=1)   # no evidence yet
        typed = self.ws / "inbox" / ("%s.txt" % sid)
        typed.write_text(typed_text, encoding="utf-8")
        self.cli(["scan", "ingest", "ielts", sid, "--typed", typed], now_ingest)
        r = self.cli(["key", "open", "ielts", sid], now_ingest, record=False)
        for word in key.values():
            self.assertIn(word, r.stdout, "key open prints the sealed key")

    def grade(self, sid, grades, now):
        gp = self.tmp / ("grades-%s.json" % sid)
        gp.write_text(json.dumps(grades, ensure_ascii=False), encoding="utf-8")
        return self.cli(["grade", "record", "ielts", sid, "--from", gp], now)

    def test_full_cycle(self):
        # ---- setup, from the persona fixture ------------------------------------------
        self.setup_workspace("ielts", "IELTS Academic", "exam",
                             ["learner.l1", "time.windows", "time.blocked", "time.sleep",
                              "calendar.provider", "calendar.target"])
        self.cli(["topic", "add", "ielts", "T01", "--name", "Matching headings", "--layer", "reading"], T0)
        self.cli(["topic", "add", "ielts", "T02", "--name", "True, false or not given", "--layer", "reading"], T0)
        self.cli(["topic", "add", "ielts", "T04", "--name", "Paraphrase", "--layer", "verbal",
                  "--confusable", "T01"], T0)
        r = self.cli(["brief", "ielts"], T0)
        self.assertIn("IELTS Academic · exam · 2026-12-12", r.stdout)

        # ---- Monday: session with a drills sheet ---------------------------------------
        r = self.cli(["session", "open", "ielts", "--planned", "60"], T0)
        self.assertIn("close starts 07:55", r.stdout)
        self.sheet_cycle(self.drills_spec(), DRILL_KEY,
                         "1 velvetrock\n2 quinsbarrow\n3 something\n4 harrowvane\n5 pellucinth\n"
                         "6 wrongthing\nLeast sure of: 3\n",
                         "2026-10-12T07:05+01:00", "2026-10-12T07:25+01:00")
        r = self.grade("ielts-drills-01", {"start": "07:08", "stop": "07:22", "date": "2026-10-12", "asks": [
            {"ask": "1a", "verdict": "right", "check": "filled"},
            {"ask": "2a", "verdict": "right", "check": "filled"},
            {"ask": "3a", "verdict": "wrong", "check": "filled", "least_sure": True, "kind": "belief",
             "mode": "V", "account": "thought any word with the same first letter keeps the meaning",
             "belief": "treats a same-letter word as a synonym"},
            {"ask": "4a", "verdict": "right", "check": "caught"},
            {"ask": "5a", "verdict": "right", "check": "filled"},
            {"ask": "6a", "verdict": "wrong", "check": "missing", "kind": "slip", "mode": "C",
             "account": "copied the letter from the line above"}]}, "2026-10-12T07:30+01:00")
        self.assertIn("[practice]", r.stdout)
        self.assertNotIn("[measured", r.stdout)
        belief_id, slip_id = re.findall(r"(E-ielts-\d{4}) \((?:belief|slip)", r.stdout)
        self.assertRegex(r.stdout, r"%s \(belief, needs repair\)" % belief_id)
        self.assertRegex(r.stdout, r"%s \(slip, due 2026-10-13\)" % slip_id)
        r = self.cli(["session", "status", "ielts"], "2026-10-12T07:30+01:00")
        self.assertIn("questions so far 6", r.stdout)
        r = self.cli(["session", "taught", "ielts", "T01", "--by", "sheet"], "2026-10-12T07:35+01:00")
        self.assertIn("Wed 14 Oct 03:35 – Thu 15 Oct 07:35", r.stdout)
        r = self.cli(["session", "close", "ielts", "--note", "headings drills went well"],
                     "2026-10-12T07:50+01:00")
        self.assertNotIn("FAIL", r.stdout)
        for c in ("C1", "C2", "C3", "C4", "C5", "C6", "C7"):
            self.assertRegex(r.stdout, r"PASS %s " % c)
        self.assertIn("Saved:", r.stdout)
        self.assertFalse((self.ws / "ielts" / ".indelible" / "session.lock").exists())

        # ---- Wednesday, 49 h later: the brief ------------------------------------------
        r = self.cli(["brief", "ielts"], T1)
        self.assert_plain_brief(r.stdout)
        due = [ln for ln in r.stdout.splitlines() if ln.startswith("DUE:")]
        self.assertEqual(len(due), 1, r.stdout)
        self.assertRegex(due[0], r"2-day rechecks? ready now: 1")
        self.assertRegex(due[0], r"mistakes due: 1 slip")
        self.assertNotIn("Matching headings (", learner_part(r.stdout))  # the recheck topic is not announced
        self.assertIn("RECHECK NOW: T01", r.stdout)                       # ...but Claude sees it
        self.assertIn(slip_id, r.stdout.split(CLAUDE_LINE)[1])
        pace = [ln for ln in r.stdout.splitlines() if ln.startswith("PACE:")]
        self.assertEqual(len(pace), 1, r.stdout)
        self.assertIn("[practice]", pace[0])        # timed on a practice sheet: never labelled measured
        self.assertNotIn("[measured]", pace[0])

        # ---- the 2-day recheck, with the slip re-served --------------------------------
        self.cli(["session", "open", "ielts", "--planned", "45"], T1)
        self.sheet_cycle(self.cold_spec(slip_id), COLD_KEY,
                         "1 brackenwise\n2 tallowmere\n3 fenwickly\n4 ostrevane\nLeast sure of: none\n",
                         "2026-10-14T08:01+01:00", "2026-10-14T08:15+01:00")
        r = self.grade("ielts-cold-01", {"start": "08:03", "stop": "08:12", "date": "2026-10-14",
                                         "asks": [{"ask": "%da" % n, "verdict": "right", "check": "filled"}
                                                  for n in range(1, 5)]}, "2026-10-14T08:18+01:00")
        self.assertIn("[measured n=4]", r.stdout)
        self.assertIn("%s passed, rung 1" % slip_id, r.stdout)
        self.assertIn("T01 0 → 3", r.stdout)
        self.assertIn("2-day recheck done: T01", r.stdout)
        r = self.cli(["topic", "show", "ielts", "--json"], "2026-10-14T08:18+01:00")
        levels = dict((t["id"], t["level"]) for t in json.loads(r.stdout))
        self.assertEqual(levels["T01"], 3)
        # practice 2 of 3: the miss named on the Least-sure line still counts (naming a miss never hides it)
        self.assertEqual(levels["T04"], 0)
        r = self.cli(["session", "taught", "ielts", "T02", "--by", "sheet"], "2026-10-14T08:20+01:00")
        self.assertIn("Fri 16 Oct 04:20 – Sat 17 Oct 08:20", r.stdout)
        r = self.cli(["session", "close", "ielts"], "2026-10-14T08:40+01:00")
        self.assertNotIn("FAIL", r.stdout)

        # ---- plan: add, place, check, diff, ack -----------------------------------------
        r = self.cli(["plan", "add", "ielts", "--kind", "teach", "--start", "2026-10-15T07:00+01:00",
                      "--min", "60", "--content", "teach:T04"], T_PLAN)
        teach_id = r.stdout.split()[0]
        self.assertRegex(teach_id, r"^B-20261015-ielts-\d+$")
        rows = json.loads(self.cli(["plan", "list", "--json"], T_PLAN).stdout)
        open_rechecks = [b for b in rows if b["kind"] == "cold" and not b.get("start")
                         and b["status"] == "planned"]
        self.assertEqual([b["content"] for b in open_rechecks], ["cold:T02"])
        recheck_id = open_rechecks[0]["id"]
        done = [b for b in rows if b["content"] == "cold:T01"]
        self.assertEqual(done[0]["status"], "done")     # closed by grading the recheck
        r = self.cli(["plan", "place", recheck_id, "--start", "2026-10-17T10:00+01:00", "--min", "45"],
                     T_PLAN, code=1)
        self.assertIn("outside the window", r.stdout)
        self.cli(["plan", "place", recheck_id, "--start", "2026-10-16T07:00+01:00", "--min", "45"], T_PLAN)
        r = self.cli(["plan", "check", "--json"], T_PLAN)
        check = json.loads(r.stdout)
        self.assertEqual(check["result"], "PASS")
        self.assertEqual(check["fails"], 0)
        r = self.cli(["plan", "diff", "--json"], T_PLAN)
        diff = json.loads(r.stdout)
        self.assertEqual(sorted((d["op"], d["block"]) for d in diff),
                         sorted([("create", teach_id), ("create", recheck_id)]))
        for d in diff:
            self.assertTrue(d["notes"].startswith("[ind:%s]" % d["block"]))
            self.assertLessEqual(len(d["notes"]), 600)
            for name in ("Matching headings", "True, false or not given", "Paraphrase", "T02", "T04"):
                self.assertNotIn(name, d["title"])
        by_block = dict((d["block"], d) for d in diff)
        self.assertEqual(by_block[recheck_id]["title"], "IELTS Academic · 2-day recheck (mixed) · 45m")
        ack = [{"block": d["block"], "provider": "google", "id": "evt-%d" % i, "etag": None, "start": d["start"]}
               for i, d in enumerate(diff)]
        ack_path = self.tmp / "ack.json"
        ack_path.write_text(json.dumps(ack), encoding="utf-8")
        self.cli(["cal", "ack", "--from", ack_path], T_PLAN)
        self.assertEqual(json.loads(self.cli(["plan", "diff", "--json"], T_PLAN).stdout), [])
        r = self.cli(["plan", "week"], T_PLAN)
        self.assertIn("| Fri 16 Oct | 07:00–07:45 | IELTS Academic | 2-day recheck (mixed) |", r.stdout)
        self.assertNotIn("teach:T04", r.stdout)

        # ---- .ics export -----------------------------------------------------------------
        ics = self.ws / "plan" / "ics" / "ielts.ics"
        self.cli(["cal", "ics", ics], T_PLAN)
        raw = ics.read_bytes()
        self.assertTrue(raw.startswith(b"BEGIN:VCALENDAR\r\n"))
        self.assertEqual(raw.count(b"BEGIN:VEVENT"), 2)
        self.assertIn(("UID:%s@indelible" % recheck_id).encode("ascii"), raw)
        self.assertIn(b"DTSTART:20261016T060000Z", raw)
        self.assertIn(b"TRIGGER:-PT15M", raw)
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
        self.assertTrue(all(len(line) <= 75 for line in raw.split(b"\r\n")))

        # ---- Sunday: weekly review, compaction, brief size -------------------------------
        r = self.cli(["review", "week", "ielts", "--week", "2026-W42"], T_WEEK_END)
        self.assertLessEqual(len(r.stdout.strip().splitlines()), 15)
        self.assertTrue((self.ws / "reviews" / "2026-W42.md").is_file())
        self.assertIn("[measured]", r.stdout)
        r = self.cli(["compact", "ielts", "--dry-run"], T_WEEK_END)
        self.assertIn("parity OK", r.stdout)
        r = self.cli(["compact", "ielts"], T_WEEK_END)
        self.assertIn("parity OK", r.stdout)
        r = self.cli(["brief", "ielts"], T_WEEK_END)
        self.assertLessEqual(len(r.stdout), 4500)
        self.assert_plain_brief(r.stdout)
        self.assertIn("Matching headings 3", r.stdout)
        data = json.loads(self.cli(["brief", "ielts", "--json"], T_WEEK_END).stdout)
        self.assertLessEqual(data["chars"], 4500)

        # ---- nothing from a key anywhere but key open ------------------------------------
        self.assert_no_accepted_answers()
        views = list((self.ws / "ielts" / "views").glob("*.md")) + [self.ws / "views" / "week.md"]
        for v in views:
            text = v.read_text(encoding="utf-8")
            for word in ALL_ACCEPTED:
                self.assertNotIn(word, text, "key text in %s" % v.name)


class PersonaDOnDemand(E2EBase):
    persona_file = "persona-d.json"

    def test_quick_path(self):
        d0 = "2026-10-12T20:00+02:00"
        self.cli(["init", self.ws, "--timezone", self.fx["timezone"]], d0)
        self.cli(["set", "root", "time.schedule", json.dumps(self.fx["expected"]["root"]["time.schedule"])], d0)
        src = self.tmp / "rust-subject.json"
        src.write_text(json.dumps(nested(self.fx["expected"]["subject"], skip=("id", "title", "profile"))),
                       encoding="utf-8")
        r = self.cli(["subject", "add", "rust", "--title", "Rust", "--profile", "code", "--from", src], d0)
        self.assertIn("no date", r.stdout)
        self.cli(["topic", "add", "rust", "T01", "--name", "Ownership and borrowing", "--layer", "code"], d0)

        r = self.cli(["brief"], d0)
        self.assertTrue(r.stdout.startswith("Rust · code · no date"), r.stdout)
        self.cli(["session", "open", "rust", "--planned", "30"], d0)
        r = self.cli(["session", "taught", "rust", "T01", "--by", "chat"], "2026-10-12T20:15+02:00")
        self.assertIn("unplaced", r.stdout)
        r = self.cli(["session", "close", "rust"], "2026-10-12T20:28+02:00")
        self.assertNotIn("FAIL", r.stdout)
        self.assertIn("Next: 2-day recheck, best between Wed 14 Oct 16:15 and Thu 15 Oct 20:15.", r.stdout)

        # 49 h later the recheck is ready; nothing asks about attendance.
        r = self.cli(["brief"], "2026-10-14T21:00+02:00")
        self.assertRegex(r.stdout, r"2-day rechecks? ready now: 1")
        self.assert_plain_brief(r.stdout)

        # 9 days away: no missed-block flags, no execution questions.
        later = "2026-10-21T21:00+02:00"
        r = self.cli(["brief"], later)
        self.assertNotIn("FLAGS", r.stdout)
        self.assertNotIn("missed", r.stdout.lower())
        self.assert_plain_brief(r.stdout)
        rows = json.loads(self.cli(["plan", "list", "--json"], later).stdout)
        self.assertTrue(all(b["status"] != "missed?" for b in rows))
        r = self.cli(["review", "week", "rust", "--week", "2026-W42"], later)
        self.assertNotIn("blocks", r.stdout)
        self.assertEqual(sorted(p.name for p in (self.ws / "plan" / "ics").glob("*")), [])
        cfg = json.loads((self.ws / "indelible.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["calendar"]["provider"], "none")
        self.assertEqual(cfg["time"]["schedule"], "on_demand")


if __name__ == "__main__":
    unittest.main()
