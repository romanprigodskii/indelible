"""Sheets, keys and evidence: sheet new|lint|build|issue|sat|void|show, scan ingest, key open.

Synthetic learner A (IELTS Academic) only. The fixture keys use made-up words
(KEY_WORDS) so a test can prove that no key text ever reaches stdout or stderr.
"""

import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

try:
    from helpers import make_ws, run
except ImportError:  # run as part of the tests package
    from tests.helpers import make_ws, run

from lib import io as fio

NOW = "2026-10-12T09:00+01:00"          # a Monday
SUBJECT = "ielts"
KEY_WORDS = ["zephyrine", "quillomatic", "marrowlight", "tessellant", "brindlewick", "vorpaline",
             "glimmerfast", "ostrevane"]

# Sentences chosen to use none of the words in assets/lists/sense_seed.txt.
SENTENCES = [
    "The bridge was closed for repairs last winter.",
    "Prices climbed quickly in the spring.",
    "Few people came to the first meeting.",
    "The museum opens early on Fridays.",
    "Heavy rain delayed the trains.",
    "The team finished the project ahead of schedule.",
    "Our neighbours painted the fence green.",
    "The old library moved to a new building.",
]


# ==========================================================================
# Fixtures (plain functions; test_lint and test_render import them)
# ==========================================================================

def drills_spec(sheet_id="ielts-drills-01", n=6, est_min=12, **over):
    items = []
    for i in range(1, n + 1):
        items.append({
            "n": i, "topic": "T04", "layer": "verbal", "op": "swap-word", "origin": "new",
            "text": SENTENCES[(i - 1) % len(SENTENCES)],
            "asks": [{"id": "%da" % i, "label": "Write it again with a new verb:", "check": True,
                      "check_hint": "Read the new sentence aloud with your answer in it"}],
        })
    half = n // 2
    blocks = [{"title": "Block A: swap one word", "items": list(range(1, half + 1))},
              {"title": "Block B: swap one word", "items": list(range(half + 1, n + 1))}]
    spec = {"v": 1, "id": sheet_id, "type": "drills", "subject": SUBJECT, "title": "Other words, same idea",
            "est_min": est_min, "tools": "none", "answer_form": "short", "items": items, "blocks": blocks,
            "terms": [], "theory": None, "least_sure": True}
    spec.update(over)
    return spec


def cold_spec(sheet_id="ielts-cold-01", **over):
    topics = ["T04", "T01", "T04", "T01"]
    items = []
    for i, t in enumerate(topics, start=1):
        items.append({
            "n": i, "topic": t, "layer": "verbal" if t == "T04" else "reading", "op": "recall",
            "origin": "cold:%s" % t, "text": SENTENCES[i - 1],
            "asks": [{"id": "%da" % i, "label": "Your answer:", "check": True,
                      "check_hint": "Read the sentence again with your answer in it"}],
        })
    spec = {"v": 1, "id": sheet_id, "type": "cold", "subject": SUBJECT, "title": "2-day recheck",
            "est_min": 10, "tools": "none", "answer_form": "short", "items": items, "blocks": [],
            "terms": [], "theory": None, "least_sure": True}
    spec.update(over)
    return spec


def theory_spec(sheet_id="ielts-theory-01", **over):
    spec = {
        "v": 1, "id": sheet_id, "type": "theory", "subject": SUBJECT, "title": "Saying it another way",
        "est_min": 8, "tools": "none", "answer_form": "short",
        "items": [{"n": 1, "topic": "T04", "layer": "verbal", "op": "complete", "origin": "new",
                   "text": "Finish the second sentence so it keeps the idea of the first.",
                   "asks": [{"id": "1a", "label": "Second sentence:", "check": False}]}],
        "blocks": [],
        "terms": [{"term": "paraphrase", "resolution": "defined_here"}],
        "theory": {
            "floor": ["You can find the verb in a sentence."],
            "words": [{"term": "paraphrase", "gloss": "paráfrase",
                       "def": "the same idea said with other words"}],
            "sections": [
                {"kind": "worked", "title": "A worked case",
                 "body": "Start: The shop shut at noon.\n\nOther words: The store closed at midday."},
                {"kind": "rule", "title": "How to paraphrase", "body": "Keep the idea. Change the words."},
                {"kind": "warning", "title": "Watch out", "body": "Do not add new facts."},
            ],
            "pages": None,
        },
        "least_sure": False,
    }
    spec.update(over)
    return spec


def answers_for(spec, words=None):
    words = list(words or KEY_WORDS)
    out = {}
    k = 0
    for it in spec["items"]:
        for a in it["asks"]:
            out[a["id"]] = {"accept": [words[k % len(words)]], "check": "the sentence still reads true",
                            "solution": "worked: " + words[k % len(words)]}
            k += 1
    return out


def subject_dir(ws):
    return Path(ws) / SUBJECT


def write_inputs(ws, spec, answers=None):
    """Write the builder's spec and answers into <subject>/.indelible/tmp/. Returns (spec_path, answers_path)."""
    tmp = subject_dir(ws) / ".indelible" / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    sp = tmp / ("%s.spec.json" % spec["id"])
    ap = tmp / ("%s.answers.json" % spec["id"])
    sp.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    ap.write_text(json.dumps(answers if answers is not None else answers_for(spec), ensure_ascii=False),
                  encoding="utf-8")
    return sp, ap


def new_sheet(ws, spec, answers=None, extra=None, now=NOW):
    sp, ap = write_inputs(ws, spec, answers)
    return run(["sheet", "new", SUBJECT, spec["id"], "--spec", sp, "--answers", ap] + list(extra or []),
               ws=ws, now=now)


def sheet_row(ws, sheet_id):
    for r in fio.read_jsonl(subject_dir(ws) / "data" / "sheets.jsonl"):
        if r.get("id") == sheet_id:
            return r
    return None


def add_exposure(ws, topic, at, kind="teach"):
    fio.append_jsonl(subject_dir(ws) / "data" / "exposures.jsonl", {"v": 1, "topic": topic, "at": at, "kind": kind})


def assert_no_key_text(test, *results):
    for r in results:
        for w in KEY_WORDS:
            test.assertNotIn(w, r.stdout, "key text on stdout")
            test.assertNotIn(w, r.stderr, "key text on stderr")


def tiny_png(path):
    """A valid 2x2 grey PNG (standard library only)."""
    def chunk(kind, data):
        c = struct.pack(">I", len(data)) + kind + data
        return c + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x80\x80\x80" * 2 for _ in range(2))
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    Path(path).write_bytes(png)
    return Path(path)


# ==========================================================================
# Tests
# ==========================================================================

class SheetBase(unittest.TestCase):
    persona = "A"

    def setUp(self):
        self._old_now = os.environ.get("INDELIBLE_NOW")
        os.environ["INDELIBLE_NOW"] = NOW
        self.tmp = Path(tempfile.mkdtemp(prefix="indelible-sheet-"))
        self.ws = make_ws(self.tmp, self.persona)

    def tearDown(self):
        if self._old_now is None:
            os.environ.pop("INDELIBLE_NOW", None)
        else:
            os.environ["INDELIBLE_NOW"] = self._old_now
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def cli(self, *args, **kw):
        return run([str(a) for a in args], ws=self.ws, now=kw.pop("now", NOW), **kw)

    def ok(self, r):
        self.assertEqual(r.returncode, 0, "stdout: %s\nstderr: %s" % (r.stdout, r.stderr))
        return r

    def to_rendered(self, spec, fmt="html"):
        self.ok(new_sheet(self.ws, spec))
        self.ok(self.cli("sheet", "lint", SUBJECT, spec["id"]))
        self.ok(self.cli("sheet", "build", SUBJECT, spec["id"], "--format", fmt))

    def to_issued(self, spec):
        self.to_rendered(spec)
        self.ok(self.cli("sheet", "issue", SUBJECT, spec["id"]))


class SheetNewTests(SheetBase):
    def test_new_prints_one_line_seals_key_and_deletes_answers(self):
        spec = drills_spec()
        sp, ap = write_inputs(self.ws, spec)
        r = self.ok(self.cli("sheet", "new", SUBJECT, spec["id"], "--spec", sp, "--answers", ap))
        self.assertRegex(r.stdout, r"^ielts-drills-01 built: 6 questions, ~12 min, key sealed sha256:[0-9a-f]{12}\n$")
        self.assertEqual(r.stderr, "")
        assert_no_key_text(self, r)
        self.assertFalse(ap.exists(), "the answers file must be deleted")
        key = subject_dir(self.ws) / ".indelible" / "keys" / "ielts-drills-01.json"
        self.assertTrue(key.is_file())
        self.assertEqual(json.loads(key.read_text(encoding="utf-8")), answers_for(spec))
        if os.name == "posix":
            self.assertEqual(key.stat().st_mode & 0o777, 0o600)
        sealed = json.loads((subject_dir(self.ws) / ".indelible" / "specs" / "ielts-drills-01.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(sealed["items"], spec["items"])
        row = sheet_row(self.ws, "ielts-drills-01")
        self.assertEqual(row["status"], "built")
        self.assertEqual(row["asks"], 6)
        self.assertEqual(row["topics"], ["T04"])
        self.assertFalse(row["measures"])
        self.assertEqual(row["key_sha"], hashlib.sha256(key.read_bytes()).hexdigest())
        self.assertIn(row["key_sha"][:12], r.stdout)
        self.assertEqual(row["sat"], {"start": None, "stop": None, "date": None})

    def test_new_fills_missing_layer_from_topic(self):
        spec = drills_spec()
        for it in spec["items"]:
            del it["layer"]
        self.ok(new_sheet(self.ws, spec))
        sealed = fio.read_json(subject_dir(self.ws) / ".indelible" / "specs" / "ielts-drills-01.json")
        self.assertEqual(set(it["layer"] for it in sealed["items"]), {"verbal"})

    def test_new_refuses_an_invalid_spec_and_keeps_the_answers(self):
        cases = [
            drills_spec("another-id"),                       # spec id is not the sheet id
            drills_spec("ielts-bad-01", subject="spanish"),  # wrong subject
            drills_spec("ielts-bad-01", type="homework"),    # unknown type
            drills_spec("ielts-bad-01", items=[dict(drills_spec()["items"][0], topic="T99")]),  # unknown topic
        ]
        for spec in cases:
            sp, ap = write_inputs(self.ws, spec, answers_for(drills_spec()))
            r = self.cli("sheet", "new", SUBJECT, "ielts-bad-01", "--spec", sp, "--answers", ap)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("refused", r.stdout)
            self.assertTrue(ap.exists(), "a refused build keeps the answers file")
            assert_no_key_text(self, r)
        self.assertIsNone(sheet_row(self.ws, "ielts-bad-01"))

    def test_new_refuses_missing_or_unknown_key_entries(self):
        spec = drills_spec()
        answers = answers_for(spec)
        del answers["3a"]
        answers["9z"] = {"accept": ["x"]}
        r = new_sheet(self.ws, spec, answers)
        self.assertEqual(r.returncode, 1)
        self.assertIn("3a", r.stdout)
        self.assertIn("9z", r.stdout)
        assert_no_key_text(self, r)

    def test_new_refuses_a_bad_id_and_missing_files(self):
        r = self.cli("sheet", "new", SUBJECT, "Bad_ID", "--spec", self.tmp / "x.json", "--answers", self.tmp / "y.json")
        self.assertEqual(r.returncode, 2)
        r = self.cli("sheet", "new", SUBJECT, "ielts-x-01", "--spec", self.tmp / "x.json", "--answers", self.tmp / "y.json")
        self.assertEqual(r.returncode, 2)
        self.assertIn("does not exist", r.stderr)

    def test_existing_id_needs_replace_and_sealed_is_never_edited(self):
        spec = drills_spec()
        self.ok(new_sheet(self.ws, spec))
        r = new_sheet(self.ws, spec)
        self.assertEqual(r.returncode, 1)
        self.assertIn("--replace", r.stdout)
        r = self.ok(new_sheet(self.ws, dict(spec, est_min=10), extra=["--replace"]))
        self.assertIn("~10 min", r.stdout)
        self.assertEqual(sheet_row(self.ws, spec["id"])["est_min"], 10)
        self.ok(self.cli("sheet", "lint", SUBJECT, spec["id"]))
        self.ok(self.cli("sheet", "build", SUBJECT, spec["id"], "--format", "md"))
        self.ok(self.cli("sheet", "issue", SUBJECT, spec["id"]))
        r = new_sheet(self.ws, spec, extra=["--replace"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("never edited after issue", r.stdout)
        self.assertEqual(sheet_row(self.ws, spec["id"])["status"], "issued")


class SheetFlowTests(SheetBase):
    def test_build_requires_lint_pass(self):
        spec = drills_spec()
        self.ok(new_sheet(self.ws, spec))
        r = self.cli("sheet", "build", SUBJECT, spec["id"], "--format", "html")
        self.assertEqual(r.returncode, 1)
        self.assertIn("has not passed lint", r.stdout)

    def test_full_flow_statuses(self):
        spec = drills_spec()
        self.ok(new_sheet(self.ws, spec))
        self.ok(self.cli("sheet", "lint", SUBJECT, spec["id"]))
        self.assertEqual(sheet_row(self.ws, spec["id"])["status"], "linted")
        r = self.cli("sheet", "issue", SUBJECT, spec["id"])
        self.assertEqual(r.returncode, 1, "issue needs a rendered sheet")
        r = self.ok(self.cli("sheet", "build", SUBJECT, spec["id"], "--format", "html"))
        out = Path(r.stdout.strip().splitlines()[0])
        self.assertTrue(out.is_file())
        row = sheet_row(self.ws, spec["id"])
        self.assertEqual(row["status"], "rendered")
        self.assertEqual(row["files"], ["sheets/2026-10/ielts-drills-01.html"])
        r = self.cli("sheet", "sat", SUBJECT, spec["id"])
        self.assertEqual(r.returncode, 1, "sat needs an issued sheet")
        self.ok(self.cli("sheet", "issue", SUBJECT, spec["id"]))
        row = sheet_row(self.ws, spec["id"])
        self.assertEqual(row["status"], "issued")
        self.assertEqual(row["issued_at"], "2026-10-12T09:00+01:00")
        r = self.cli("sheet", "issue", SUBJECT, spec["id"])
        self.assertEqual(r.returncode, 1)
        r = self.cli("sheet", "build", SUBJECT, spec["id"], "--format", "html")
        self.assertEqual(r.returncode, 1, "a sealed sheet is not rebuilt")
        self.ok(self.cli("sheet", "sat", SUBJECT, spec["id"], "--start", "07:05", "--stop", "7:17"))
        row = sheet_row(self.ws, spec["id"])
        self.assertEqual(row["status"], "sat")
        self.assertEqual(row["sat"], {"start": "07:05", "stop": "07:17", "date": "2026-10-12"})
        r = self.cli("sheet", "sat", SUBJECT, spec["id"], "--start", "7h05")
        self.assertEqual(r.returncode, 2)

    def test_issue_links_a_block_and_rejects_unknown_blocks(self):
        spec = drills_spec()
        self.to_rendered(spec)
        r = self.cli("sheet", "issue", SUBJECT, spec["id"], "--block", "B-20261012-ielts-9")
        self.assertEqual(r.returncode, 2)
        block = {"v": 1, "id": "B-20261012-ielts-1", "subject": SUBJECT, "kind": "teach",
                 "start": "2026-10-12T07:00+01:00", "end": "2026-10-12T08:00+01:00", "window": None,
                 "protected": False, "measurement": False, "soft": False, "pair": None, "content": "drills",
                 "status": "planned", "cal": None, "moved_from": None, "miss_reason": None}
        fio.write_jsonl(Path(self.ws) / "plan" / "blocks.jsonl", [block])
        r = self.ok(self.cli("sheet", "issue", SUBJECT, spec["id"], "--block", "B-20261012-ielts-1"))
        self.assertIn("B-20261012-ielts-1", r.stdout)
        self.assertEqual(sheet_row(self.ws, spec["id"])["block"], "B-20261012-ielts-1")

    def test_void_and_show(self):
        a, b = drills_spec("ielts-drills-01"), drills_spec("ielts-drills-02")
        self.ok(new_sheet(self.ws, a))
        self.ok(new_sheet(self.ws, b))
        r = self.ok(self.cli("sheet", "void", SUBJECT, b["id"], "--reason", "built for the wrong day"))
        self.assertIn("void", r.stdout)
        row = sheet_row(self.ws, b["id"])
        self.assertEqual(row["status"], "void")
        self.assertEqual(row["void"]["reason"], "built for the wrong day")
        self.assertEqual(self.cli("sheet", "void", SUBJECT, b["id"], "--reason", "again").returncode, 1)
        r = self.ok(self.cli("sheet", "show", SUBJECT))
        self.assertIn("ielts-drills-01", r.stdout)
        self.assertIn("ielts-drills-02", r.stdout)
        r = self.ok(self.cli("sheet", "show", SUBJECT, "--status", "void"))
        self.assertNotIn("ielts-drills-01", r.stdout)
        self.assertIn("ielts-drills-02", r.stdout)
        rows = json.loads(self.ok(self.cli("sheet", "show", "--json")).stdout)
        self.assertEqual([x["id"] for x in rows], ["ielts-drills-01", "ielts-drills-02"])
        r = self.ok(self.cli("sheet", "show", SUBJECT, "--status", "graded"))
        self.assertIn("No sheets", r.stdout)

    def test_unknown_sheet_is_a_usage_error(self):
        r = self.cli("sheet", "lint", SUBJECT, "ielts-nope-01")
        self.assertEqual(r.returncode, 2)
        self.assertIn("No sheet", r.stderr)


class KeyTests(SheetBase):
    def test_key_is_never_printed_by_new_lint_build_or_show(self):
        spec = drills_spec()
        results = [new_sheet(self.ws, spec)]
        results.append(self.cli("sheet", "lint", SUBJECT, spec["id"]))
        results.append(self.cli("sheet", "lint", SUBJECT, spec["id"], "--json"))
        results.append(self.cli("sheet", "build", SUBJECT, spec["id"], "--format", "html"))
        results.append(self.cli("sheet", "build", SUBJECT, spec["id"], "--format", "md"))
        results.append(self.cli("sheet", "show", SUBJECT))
        results.append(self.cli("sheet", "show", SUBJECT, "--json"))
        results.append(self.cli("sheet", "issue", SUBJECT, spec["id"]))
        results.append(self.cli("key", "open", SUBJECT, spec["id"]))
        for r in results[:-1]:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        assert_no_key_text(self, *results)
        for f in (subject_dir(self.ws) / "sheets" / "2026-10").iterdir():
            text = f.read_text(encoding="utf-8")
            for w in KEY_WORDS:
                self.assertNotIn(w, text, "key text in %s" % f.name)

    def test_key_open_refused_before_evidence_then_allowed(self):
        spec = drills_spec()
        self.ok(new_sheet(self.ws, spec))
        r = self.cli("key", "open", SUBJECT, spec["id"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("Refused", r.stdout)
        assert_no_key_text(self, r)
        self.ok(self.cli("sheet", "lint", SUBJECT, spec["id"]))
        self.ok(self.cli("sheet", "build", SUBJECT, spec["id"], "--format", "md"))
        self.ok(self.cli("sheet", "issue", SUBJECT, spec["id"]))
        self.ok(self.cli("sheet", "sat", SUBJECT, spec["id"], "--start", "07:00"))
        r = self.cli("key", "open", SUBJECT, spec["id"])
        self.assertEqual(r.returncode, 1, "sat without evidence is still refused")
        assert_no_key_text(self, r)
        opened = subject_dir(self.ws) / ".indelible" / "keys" / "opened.jsonl"
        self.assertFalse(opened.exists())

        typed = self.tmp / "typed.txt"
        typed.write_text("1a: the bridge shut\n2a: prices rose\n", encoding="utf-8")
        self.ok(self.cli("scan", "ingest", SUBJECT, spec["id"], "--typed", typed))
        r = self.ok(self.cli("key", "open", SUBJECT, spec["id"]))
        self.assertEqual(json.loads(r.stdout), answers_for(spec))
        rows = fio.read_jsonl(opened)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sheet"], spec["id"])
        self.assertEqual(rows[0]["at"], "2026-10-12T09:00+01:00")


class ScanTests(SheetBase):
    def test_ingest_refused_before_issue(self):
        spec = drills_spec()
        self.ok(new_sheet(self.ws, spec))
        photo = tiny_png(self.tmp / "p.png")
        r = self.cli("scan", "ingest", SUBJECT, spec["id"], photo)
        self.assertEqual(r.returncode, 1)
        self.assertIn("sheet issue", r.stdout)

    def test_ingest_needs_some_evidence_and_real_files(self):
        spec = drills_spec()
        self.to_issued(spec)
        self.assertEqual(self.cli("scan", "ingest", SUBJECT, spec["id"]).returncode, 2)
        self.assertEqual(self.cli("scan", "ingest", SUBJECT, spec["id"], self.tmp / "missing.jpg").returncode, 2)
        self.assertEqual(sheet_row(self.ws, spec["id"])["status"], "issued")

    def test_ingest_files_are_numbered_indexed_and_mark_sat(self):
        spec = drills_spec()
        self.to_issued(spec)
        p1 = tiny_png(self.tmp / "IMG_0001.png")
        p2 = self.tmp / "IMG_0002.jpg"
        p2.write_bytes(b"\xff\xd8\xff\xe0fake jpeg bytes")
        pdf = self.tmp / "scan.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
        r = self.ok(self.cli("scan", "ingest", SUBJECT, spec["id"], p1, p2, pdf, "--date", "2026-10-11"))
        self.assertIn("marked as taken", r.stdout)
        scans = subject_dir(self.ws) / "scans"
        for name in ("2026-10-11-ielts-drills-01-answers-p1.png", "2026-10-11-ielts-drills-01-answers-p2.jpg",
                     "2026-10-11-ielts-drills-01-answers-p3.pdf"):
            self.assertTrue((scans / name).is_file(), name)
        self.assertTrue(p1.exists(), "the learner's originals are copied, not moved")
        index = fio.read_jsonl(scans / "index.jsonl")
        self.assertEqual(len(index), 3)
        self.assertEqual(index[0]["sha256"], hashlib.sha256(p1.read_bytes()).hexdigest())
        self.assertTrue(all(x["sheet"] == spec["id"] and x["kind"] == "scan" for x in index))
        row = sheet_row(self.ws, spec["id"])
        self.assertEqual(row["status"], "sat")
        self.assertEqual(row["sat"]["date"], "2026-10-11")
        self.assertEqual(len(row["evidence"]), 3)
        self.assertEqual(row["evidence"][0]["file"], "scans/2026-10-11-ielts-drills-01-answers-p1.png")
        # A single later photo never overwrites an earlier one.
        p3 = tiny_png(self.tmp / "late.png")
        self.ok(self.cli("scan", "ingest", SUBJECT, spec["id"], p3))
        self.assertTrue((scans / "2026-10-11-ielts-drills-01-answers-p4.png").is_file())
        self.assertEqual(len(sheet_row(self.ws, spec["id"])["evidence"]), 4)

    def test_single_file_has_no_page_suffix(self):
        spec = drills_spec()
        self.to_issued(spec)
        self.ok(self.cli("scan", "ingest", SUBJECT, spec["id"], tiny_png(self.tmp / "a.png")))
        self.assertTrue((subject_dir(self.ws) / "scans" / "2026-10-12-ielts-drills-01-answers.png").is_file())

    def test_typed_and_transcript(self):
        spec = drills_spec()
        self.to_issued(spec)
        typed = self.tmp / "t.txt"
        typed.write_text("1a: shut\n", encoding="utf-8")
        self.ok(self.cli("scan", "ingest", SUBJECT, spec["id"], "--typed", typed))
        self.assertEqual((subject_dir(self.ws) / "answers" / "ielts-drills-01.txt").read_text(encoding="utf-8"),
                         "1a: shut\n")
        r = self.ok(self.cli("scan", "ingest", SUBJECT, spec["id"], "--transcript", "-",
                             stdin="1a: shut\n2a: rose\nLeast sure of: 2\n"))
        self.assertIn("2026-10-12-ielts-drills-01-answers.txt", r.stdout)
        saved = subject_dir(self.ws) / "scans" / "2026-10-12-ielts-drills-01-answers.txt"
        self.assertIn("Least sure of: 2", saved.read_text(encoding="utf-8"))
        kinds = [e["kind"] for e in sheet_row(self.ws, spec["id"])["evidence"]]
        self.assertEqual(kinds, ["typed", "chat-image+transcript"])
        r = self.cli("scan", "ingest", SUBJECT, spec["id"], "--transcript", "-", stdin="   \n")
        self.assertEqual(r.returncode, 2, "an empty transcript is refused")

    @unittest.skipUnless(sys.platform == "darwin" and shutil.which("sips"), "needs sips (macOS) to make a HEIC file")
    def test_heic_is_converted_and_the_original_kept(self):
        spec = drills_spec()
        self.to_issued(spec)
        png = tiny_png(self.tmp / "src.png")
        heic = self.tmp / "IMG_0042.HEIC"
        made = subprocess.run(["sips", "-s", "format", "heic", str(png), "--out", str(heic)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if made.returncode != 0 or not heic.is_file():
            self.skipTest("this sips cannot write HEIC")
        r = self.ok(self.cli("scan", "ingest", SUBJECT, spec["id"], heic))
        scans = subject_dir(self.ws) / "scans"
        self.assertTrue((scans / "2026-10-12-ielts-drills-01-answers.jpg").is_file())
        self.assertTrue((scans / "2026-10-12-ielts-drills-01-answers.heic").is_file())
        ev = sheet_row(self.ws, spec["id"])["evidence"][0]
        self.assertEqual(ev["file"], "scans/2026-10-12-ielts-drills-01-answers.jpg")
        self.assertEqual(ev["original"], "scans/2026-10-12-ielts-drills-01-answers.heic")
        self.assertNotIn("could not convert", r.stdout)


if __name__ == "__main__":
    unittest.main()
