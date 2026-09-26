"""The synthetic sample workspace in examples/sample-workspace (persona A).

The sample is committed to the repository for reviewers, so these tests make
sure it keeps working with the current CLI:

- at its fixed clock (SAMPLE_NOW) the brief, due and plan check run cleanly,
  the brief stays under 4,500 characters and shows the 2-day recheck as ready;
- a whole recheck session still runs on it at that clock (the recheck sheet
  passes the checker, is marked, and the session closes);
- its files stay within the plugin directory's limits (text only, small, few,
  valid names) and hold no path from anyone's machine;
- examples/build_sample.py still rebuilds it through the CLI, with the same
  files. If that test fails after a CLI change, rebuild the sample:
      python3 examples/build_sample.py --force

Two README promises a reviewer checks are tested here too, on the sample: the
scripts write nothing outside the workspace (`cal ics` refuses another place,
and `sheet new` deletes an answers file only inside the subject's tmp folder),
and a browser started for PDFs is kept off the network by its flags.

Every test works on a copy made the way a git checkout would have it (files
only, no empty folders); the committed sample is never written to.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from helpers import REPO_DIR, base_env, run
except ImportError:  # run as part of the tests package
    from tests.helpers import REPO_DIR, base_env, run

EXAMPLES = REPO_DIR / "examples"
SAMPLE = EXAMPLES / "sample-workspace"
BUILD_SCRIPT = EXAMPLES / "build_sample.py"
SAMPLE_NOW = "2026-10-15T07:00+01:00"   # also in examples/README.md and build_sample.py
SUBJECT = "ielts"

CLAUDE_LINE = "-- for Claude, do not read aloud --"
PLAIN_ID_RE = re.compile(r"\b(?:E-[a-z0-9-]+-\d{3,}|S-[a-z0-9-]+-\d{3,}|B-\d{8}-[a-z0-9-]+-\d+|L-\d{3,})\b")
TEXT_SUFFIXES = {".md", ".html", ".json", ".jsonl", ".ics", ".txt"}
NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
WINDOWS_DEVICE_NAMES = {"con", "prn", "aux", "nul"} | {"com%d" % i for i in range(1, 10)} | \
    {"lpt%d" % i for i in range(1, 10)}
LOCAL_PATH_RE = re.compile(r"(/Users/|/home/|/var/folders/|/private/|/tmp/|(?<![A-Za-z])[A-Z]:[\\/])")

# What a reviewer's session needs: a sealed key for every sheet, the typed answers, the specs.
REQUIRED = [
    "indelible.json", "CLAUDE.md", "ledger.jsonl", "plan/blocks.jsonl", "plan/ics/study-20261011.ics",
    "views/week.md",
    "ielts/CLAUDE.md", "ielts/subject.json", "ielts/data/sheets.jsonl", "ielts/data/attempts.jsonl",
    "ielts/data/errors.jsonl", "ielts/data/sessions.jsonl", "ielts/data/topics.json",
    "ielts/.indelible/keys/ielts-diagnostic-01.json", "ielts/.indelible/keys/ielts-headings-01-theory.json",
    "ielts/.indelible/keys/ielts-headings-01-drills.json",
    "ielts/.indelible/specs/ielts-diagnostic-01.json", "ielts/answers/ielts-diagnostic-01.txt",
    "ielts/sheets/2026-10/ielts-diagnostic-01.md", "ielts/sheets/2026-10/ielts-diagnostic-01.html",
]


def sample_files(root=SAMPLE):
    """Relative POSIX paths of every file under root, sorted."""
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def checkout_copy(dest):
    """Copy the sample file by file, as a git checkout has it (git keeps no empty folders)."""
    for rel in sample_files():
        target = dest.joinpath(*rel.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(SAMPLE.joinpath(*rel.split("/"))), str(target))
    return dest


class SampleBase(unittest.TestCase):
    def setUp(self):
        if not (SAMPLE / "indelible.json").is_file():
            self.fail("examples/sample-workspace is missing; build it: python3 examples/build_sample.py")
        self.tmp = Path(tempfile.mkdtemp(prefix="indelible-sample-test-"))
        self.ws = checkout_copy(self.tmp / "Study")

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def cli(self, *args, code=0, stdin=None):
        r = run([str(a) for a in args], ws=self.ws, now=SAMPLE_NOW, stdin=stdin)
        if code is not None:
            self.assertEqual(r.returncode, code, "%s -> %s\nstdout: %s\nstderr: %s"
                             % (" ".join(str(a) for a in args), r.returncode, r.stdout, r.stderr))
        return r


class SampleAtItsClock(SampleBase):
    def test_brief(self):
        r = self.cli("brief", SUBJECT)
        self.assertLessEqual(len(r.stdout), 4500)
        self.assertTrue(r.stdout.startswith("IELTS Academic · exam · 2026-12-12"), r.stdout)
        learner = r.stdout.split(CLAUDE_LINE)[0]
        self.assertNotIn("FLAGS", learner, "nothing should be flagged at the sample's clock:\n" + r.stdout)
        self.assertRegex(learner, r"2-day rechecks? ready now: 1")
        self.assertIn("mistakes due: 1 slip", learner)
        self.assertIsNone(PLAIN_ID_RE.search(learner), "an id is shown above the Claude line:\n" + r.stdout)
        self.assertIn("RECHECK NOW: T01", r.stdout)
        data = json.loads(self.cli("brief", SUBJECT, "--json").stdout)
        self.assertLessEqual(data["chars"], 4500)
        r = self.cli("brief")   # every subject
        self.assertLessEqual(len(r.stdout), 4500)

    def test_due(self):
        r = self.cli("due", SUBJECT)
        self.assertTrue(r.stdout.strip(), "due printed nothing")
        r = self.cli("due", SUBJECT, "--list")
        self.assertIn("T01 Matching headings", r.stdout)
        self.assertIn("needs repair", r.stdout)

    def test_plan_check(self):
        r = self.cli("plan", "check")
        self.assertIn("PASS", r.stdout)
        check = json.loads(self.cli("plan", "check", "--json").stdout)
        self.assertEqual(check["result"], "PASS", check)
        self.assertEqual(check["fails"], 0, check)
        self.assertEqual(json.loads(self.cli("plan", "diff", "--json").stdout), [],
                         "every planned block should already be acknowledged in the calendar file")

    def test_other_read_commands(self):
        self.cli("stats", SUBJECT)
        self.cli("topic", "show", SUBJECT)
        self.cli("error", "list", SUBJECT)
        self.cli("sheet", "show", SUBJECT)
        self.cli("ledger", "list")
        self.cli("plan", "week")

    def test_views_render_cleanly(self):
        # A hand edit (or a line-ending change) to a generated view would make render refuse.
        r = self.cli("render", "all")
        self.assertNotIn("Refused", r.stdout)


class SampleRecheckSession(SampleBase):
    """What a reviewer's "start" does at the sample's clock: the 2-day recheck opens the session."""

    def test_recheck_session(self):
        blocks = json.loads(self.cli("plan", "list", "--json").stdout)
        recheck = [b["id"] for b in blocks if b.get("kind") == "cold" and b.get("content") == "cold:T01"]
        session = [b["id"] for b in blocks if (b.get("start") or "").startswith("2026-10-15T07:15")]
        self.assertEqual(len(recheck), 1, blocks)
        self.assertEqual(len(session), 1, blocks)
        errors = [json.loads(line) for line in
                  (self.ws / SUBJECT / "data" / "errors.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        slips = [e["id"] for e in errors if e.get("kind") == "slip" and e.get("status") == "spacing"]
        self.assertEqual(len(slips), 1, errors)

        self.cli("session", "open", SUBJECT, "--planned", 60, "--block", session[0])
        sheet = "ielts-cold-01"

        def item(n, topic, layer, op, origin, text, label):
            return {"n": n, "topic": topic, "layer": layer, "op": op, "origin": origin, "text": text,
                    "asks": [{"id": "%da" % n, "label": label, "check": True,
                              "check_hint": "Read your answer back against the text."}]}
        spec = {"v": 1, "id": sheet, "type": "cold", "subject": SUBJECT, "title": "2-day recheck", "est_min": 5,
                "tools": "none", "answer_form": "short", "blocks": [], "terms": [], "theory": None,
                "least_sure": True, "items": [
                    item(1, "T01", "reading", "pick-heading", "cold:T01",
                         "Paragraph: The canal through Brayford carried coal for a century. Volunteers cleared it "
                         "in 2015, and narrowboats now bring visitors through the town.\n\nHeadings:\n"
                         "A. Coal in the north\nB. A working canal with a second life\nC. Steering a narrowboat",
                         "Letter of the heading for this paragraph:"),
                    item(2, "T04", "verbal", "match-meaning", "error:%s" % slips[0],
                         "Sentence: 'Ticket sales dropped steeply after the price went up.'\n\n"
                         "A. After the price went up, far fewer tickets were sold.\n"
                         "B. The price went up because tickets sold well.",
                         "Letter of the sentence that says the same:"),
                    item(3, "T01", "reading", "pick-heading", "cold:T01",
                         "Paragraph: Dunmore library opened in 1905 with 300 books. Today it lends laptops and "
                         "hosts a repair cafe on Saturdays.\n\nHeadings:\nA. An old library with new jobs\n"
                         "B. Mending bicycles\nC. Books in 1905",
                         "Letter of the heading for this paragraph:")]}
        key = dict(("%da" % n, {"accept": [a], "check": "read back", "solution": "synthetic"})
                   for n, a in ((1, "B"), (2, "A"), (3, "A")))
        tmpd = self.ws / SUBJECT / ".indelible" / "tmp"
        tmpd.mkdir(parents=True, exist_ok=True)
        sp, ap = tmpd / (sheet + ".spec.json"), tmpd / (sheet + ".answers.json")
        sp.write_text(json.dumps(spec), encoding="utf-8")
        ap.write_text(json.dumps(key), encoding="utf-8")
        self.cli("sheet", "new", SUBJECT, sheet, "--spec", sp, "--answers", ap)
        r = self.cli("sheet", "lint", SUBJECT, sheet, "--budget-min", 12)
        self.assertIn("lint PASS", r.stdout)
        self.assertRegex(r.stdout, r"L7 PASS")   # the recheck is inside its window at the sample's clock
        self.cli("sheet", "build", SUBJECT, sheet, "--format", "md")
        self.cli("sheet", "issue", SUBJECT, sheet, "--block", recheck[0])
        typed = self.tmp / "typed.txt"
        typed.write_text("1 B\n2 A\n3 A\nLeast sure of: none\n", encoding="utf-8")
        self.cli("scan", "ingest", SUBJECT, sheet, "--typed", typed)
        self.cli("key", "open", SUBJECT, sheet)
        grades = self.tmp / "grades.json"
        grades.write_text(json.dumps({"start": "07:02", "stop": "07:07", "date": "2026-10-15", "asks": [
            {"ask": "%da" % n, "verdict": "right", "check": "filled"} for n in (1, 2, 3)]}), encoding="utf-8")
        r = self.cli("grade", "record", SUBJECT, sheet, "--from", grades, "--shaky")
        self.assertIn("[measured n=3]", r.stdout)
        self.assertIn("2-day recheck done: T01", r.stdout)
        self.assertIn("T01 2 → 3", r.stdout)
        r = self.cli("session", "close", SUBJECT)
        self.assertNotIn("FAIL", r.stdout)
        self.assertIn("Saved:", r.stdout)


class ScriptsStayInTheWorkspace(SampleBase):
    """README, "What it writes": the scripts write and delete files only inside the workspace."""

    def test_cal_ics_refuses_a_path_outside_the_workspace(self):
        outside = self.tmp / "outside.ics"
        r = self.cli("cal", "ics", outside, code=2)
        self.assertIn("only inside the workspace", r.stderr + r.stdout)
        self.assertFalse(outside.exists())
        inside = self.ws / "plan" / "ics" / "inside.ics"
        self.cli("cal", "ics", inside)
        self.assertTrue(inside.is_file())

    def test_sheet_new_leaves_an_answers_file_outside_tmp(self):
        spec = json.loads((self.ws / SUBJECT / ".indelible" / "specs" / "ielts-headings-01-drills.json")
                          .read_text(encoding="utf-8"))
        key = (self.ws / SUBJECT / ".indelible" / "keys" / "ielts-headings-01-drills.json").read_text(encoding="utf-8")
        tmpd = self.ws / SUBJECT / ".indelible" / "tmp"
        tmpd.mkdir(parents=True, exist_ok=True)
        for sheet, folder in (("ielts-headings-08-drills", self.tmp), ("ielts-headings-09-drills", tmpd)):
            spec["id"] = sheet
            sp, ap = folder / (sheet + ".spec.json"), folder / (sheet + ".answers.json")
            sp.write_text(json.dumps(spec), encoding="utf-8")
            ap.write_text(key, encoding="utf-8")
            r = self.cli("sheet", "new", SUBJECT, sheet, "--spec", sp, "--answers", ap)
            self.assertIn("key sealed", r.stdout)
            if folder == tmpd:
                self.assertFalse(ap.exists(), "the answers file in tmp is deleted once the key is sealed")
            else:
                self.assertTrue(ap.exists(), "a file outside the workspace is never deleted")
                self.assertIn("left where it is", r.stderr)


class BrowserStaysOffline(unittest.TestCase):
    """README, "What it runs": a headless browser that prints a PDF has its network blocked.

    No browser is started: the launch is intercepted and its command line checked,
    for the sheet printer (lib.render) and for doctor's fallback test print (lib.cmd_setup).
    """

    REQUIRED = ("--disable-background-networking", "--disable-component-update",
                "--proxy-server=127.0.0.1:9", "--host-resolver-rules=MAP * ~NOTFOUND",
                "--disable-extensions", "--headless")

    def _launch(self, call):
        seen = []

        def fake_popen(cmd, *args, **kwargs):
            seen.append(list(cmd))
            raise OSError("no browser in tests")

        with mock.patch("subprocess.Popen", side_effect=fake_popen):
            call()
        self.assertEqual(len(seen), 1, seen)
        return seen[0]

    def test_both_launches_carry_the_offline_flags(self):
        from lib import cmd_setup, render
        self.assertEqual(tuple(render.BROWSER_OFFLINE_FLAGS), tuple(cmd_setup.BROWSER_OFFLINE_FLAGS),
                         "the two copies of the offline flags differ")
        tmp = Path(tempfile.mkdtemp(prefix="indelible-offline-test-"))
        try:
            page = tmp / "t.html"
            page.write_text("<!doctype html><p>t</p>", encoding="utf-8")
            fake = str(tmp / "chrome")
            for name, call in (("render", lambda: render.print_html_to_pdf(page, tmp / "t.pdf", exe=fake)),
                               ("doctor", lambda: cmd_setup._test_chrome(fake))):
                cmd = self._launch(call)
                self.assertEqual(cmd[0], fake, name)
                for flag in self.REQUIRED + tuple(render.BROWSER_OFFLINE_FLAGS):
                    self.assertIn(flag, cmd, "%s launch lacks %s" % (name, flag))
                self.assertTrue(cmd[-1].startswith("file:"), "%s prints a local file only: %s" % (name, cmd[-1]))
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)


class SampleFiles(unittest.TestCase):
    """The plugin directory's limits, and nothing from anyone's machine."""

    def test_limits_and_names(self):
        files = sample_files()
        self.assertLess(len(files), 80)
        seen = {}
        for rel in files:
            path = SAMPLE.joinpath(*rel.split("/"))
            self.assertLessEqual(path.stat().st_size, 256 * 1024, rel)
            self.assertIn(path.suffix.lower(), TEXT_SUFFIXES, "not a text file: %s" % rel)
            for part in rel.split("/"):
                self.assertRegex(part, NAME_RE, rel)
                self.assertFalse(part.endswith((".", " ")), rel)
                self.assertNotIn(part.split(".")[0].lower(), WINDOWS_DEVICE_NAMES, rel)
                self.assertNotIn(part, (".DS_Store", "__pycache__", "Thumbs.db", "desktop.ini", "__MACOSX"), rel)
            self.assertFalse(rel.endswith(".bak"), rel)
            folded = rel.lower()
            self.assertNotIn(folded, seen, "names differ only by case: %s, %s" % (rel, seen.get(folded)))
            seen[folded] = rel
        for p in SAMPLE.rglob("*"):
            self.assertFalse(p.is_symlink(), p)

    def test_required_files(self):
        files = set(sample_files())
        for rel in REQUIRED:
            self.assertIn(rel, files, "missing from the sample (was it left out of git?): %s" % rel)

    def test_text_is_utf8_and_holds_no_local_paths(self):
        for rel in sample_files():
            text = SAMPLE.joinpath(*rel.split("/")).read_bytes().decode("utf-8")   # raises if not UTF-8
            m = LOCAL_PATH_RE.search(text)
            self.assertIsNone(m, "%s holds a path from someone's machine: %r" % (rel, m.group(0) if m else ""))

    def test_root_claude_md_points_nowhere_local(self):
        text = (SAMPLE / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("<skill>/scripts/indelible.py", text)
        self.assertIn("synthetic sample learner", text)


class SampleRebuild(unittest.TestCase):
    """build_sample.py still runs through the current CLI and makes the same set of files."""

    def test_rebuild_matches_the_committed_file_list(self):
        tmp = Path(tempfile.mkdtemp(prefix="indelible-sample-rebuild-"))
        try:
            out = tmp / "sample-workspace"
            env = base_env()
            env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
            r = subprocess.run([sys.executable, str(BUILD_SCRIPT), "--out", str(out)], capture_output=True,
                               text=True, encoding="utf-8", errors="replace", env=env, cwd=str(tmp), timeout=600)
            self.assertEqual(r.returncode, 0, "build_sample.py failed:\n%s\n%s" % (r.stdout, r.stderr))
            self.assertEqual(sample_files(out), sample_files(),
                             "the committed sample differs from a rebuild; run: "
                             "python3 examples/build_sample.py --force")
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
