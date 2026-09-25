"""RFC 5545 export: lib/ics.py and ``cal ics``.

The file is checked with a tiny parser written here (unfold, split on CRLF,
unescape), so the test does not trust the module's own view of its output.
"""

import json
import os
import re
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from helpers import make_ws, run
except ImportError:  # run as part of the tests package
    from tests.helpers import make_ws, run

from lib import ics
from lib import io as fio

NOW = "2026-10-12T09:00+01:00"
SID = "ielts"
LONG = ("Résumé → naïve café; 日本語, Ελληνικά and 𝑥² ≤ 3 \\ back-slash. " * 12).strip()


# ---- a tiny independent parser ---------------------------------------------

def unfold(text):
    """RFC 5545 3.1: a CRLF followed by one space or tab is removed."""
    return re.sub(r"\r\n[ \t]", "", text)


def unescape(value):
    out, i = [], 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            out.append({"n": "\n", "N": "\n", ",": ",", ";": ";", "\\": "\\"}.get(nxt, nxt))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def parse_events(text):
    """[{prop: value}] for each VEVENT; VALARM properties are keyed ``VALARM.<NAME>``."""
    events, stack, cur = [], [], None
    for line in unfold(text).split("\r\n"):
        if not line:
            continue
        name, _, value = line.partition(":")
        name = name.split(";")[0].upper()
        if name == "BEGIN":
            stack.append(value)
            if value == "VEVENT":
                cur = {}
            continue
        if name == "END":
            if not stack or stack[-1] != value:
                raise AssertionError("unbalanced END:%s" % value)
            stack.pop()
            if value == "VEVENT":
                events.append(cur)
                cur = None
            continue
        if cur is not None:
            key = name if stack[-1] == "VEVENT" else "%s.%s" % (stack[-1], name)
            cur[key] = value
    if stack:
        raise AssertionError("unclosed: %s" % stack)
    return events


class Clocked(unittest.TestCase):
    def setUp(self):
        self._old_now = os.environ.get("INDELIBLE_NOW")
        os.environ["INDELIBLE_NOW"] = NOW

    def tearDown(self):
        if self._old_now is None:
            os.environ.pop("INDELIBLE_NOW", None)
        else:
            os.environ["INDELIBLE_NOW"] = self._old_now

    def assert_physical_lines(self, text):
        data = text.encode("utf-8")
        self.assertTrue(data.endswith(b"\r\n"))
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""), "bare LF")
        self.assertNotIn(b"\r", data.replace(b"\r\n", b""), "bare CR")
        for raw in data.split(b"\r\n")[:-1]:
            self.assertLessEqual(len(raw), 75, raw)
            raw.decode("utf-8")  # a cut inside a character would raise here


# ==========================================================================
# lib/ics.py
# ==========================================================================

class IcsModuleTests(Clocked):
    def event(self, **kw):
        tz = timezone(timedelta(hours=1))
        ev = {"uid": "B-20261015-ielts-1@indelible", "dtstamp": datetime(2026, 10, 12, 9, 0, tzinfo=tz),
              "start": datetime(2026, 10, 15, 7, 0, tzinfo=tz), "end": datetime(2026, 10, 15, 8, 0, tzinfo=tz),
              "summary": "IELTS Academic · new skill · 60m", "description": LONG, "sequence": 2,
              "alarm_min": 15, "categories": ["indelible"]}
        ev.update(kw)
        return ev

    def test_long_utf8_description_is_folded_and_parses_back(self):
        text = ics.build_calendar([self.event()])
        self.assert_physical_lines(text)
        folded = [l for l in text.split("\r\n") if l.startswith(" ")]
        self.assertGreater(len(folded), 5)
        events = parse_events(text)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(unescape(ev["DESCRIPTION"]), LONG)
        self.assertEqual(unescape(ev["SUMMARY"]), "IELTS Academic · new skill · 60m")
        self.assertEqual(ev["UID"], "B-20261015-ielts-1@indelible")
        self.assertEqual(ev["DTSTART"], "20261015T060000Z")
        self.assertEqual(ev["DTEND"], "20261015T070000Z")
        self.assertEqual(ev["DTSTAMP"], "20261012T080000Z")
        self.assertEqual(ev["SEQUENCE"], "2")
        self.assertEqual(ev["VALARM.TRIGGER"], "-PT15M")
        self.assertEqual(ev["VALARM.ACTION"], "DISPLAY")

    def test_fold_never_splits_a_character(self):
        for pad in range(8):
            for ch in ("é", "→", "𝑥"):
                line = "DESCRIPTION:" + "a" * pad + ch * 60
                folded = ics.fold_line(line)
                pieces = folded.split("\r\n")
                self.assertGreater(len(pieces), 1)
                for i, piece in enumerate(pieces):
                    self.assertLessEqual(len(piece.encode("utf-8")), 75)
                    if i:
                        self.assertTrue(piece.startswith(" "))
                self.assertEqual(unfold(folded), line)

    def test_short_lines_are_not_folded(self):
        line = "SUMMARY:" + "x" * 67
        self.assertEqual(len(line), 75)
        self.assertEqual(ics.fold_line(line), line)
        self.assertEqual(ics.fold_line(line + "x").split("\r\n")[1], " x")

    def test_escaping(self):
        raw = "a,b;c\\d\ne\r\nf\rg\x07h"
        self.assertEqual(ics.escape_text(raw), "a\\,b\\;c\\\\d\\ne\\nf\\ngh")
        self.assertEqual(unescape(ics.escape_text(raw)), "a,b;c\\d\ne\nf\ngh")
        text = ics.build_calendar([self.event(summary="Stats, part 1; mock", description=raw)])
        ev = parse_events(text)[0]
        self.assertEqual(unescape(ev["SUMMARY"]), "Stats, part 1; mock")
        self.assertEqual(ev["SUMMARY"], "Stats\\, part 1\\; mock")

    def test_calendar_frame(self):
        text = ics.build_calendar([], name="Study")
        lines = text.split("\r\n")
        self.assertEqual(lines[0], "BEGIN:VCALENDAR")
        self.assertIn("VERSION:2.0", lines)
        self.assertTrue(any(l.startswith("PRODID:") for l in lines))
        self.assertEqual(lines[-2], "END:VCALENDAR")
        self.assertEqual(lines[-1], "")
        self.assertEqual(parse_events(text), [])
        with self.assertRaises(ValueError):
            ics.fmt_utc(datetime(2026, 10, 15, 7, 0))


# ==========================================================================
# cal ics through the CLI
# ==========================================================================

class CalIcsTests(Clocked):
    @classmethod
    def setUpClass(cls):
        cls._root = Path(tempfile.mkdtemp(prefix="indelible-ics-"))
        (cls._root / "template").mkdir()
        cls._template = make_ws(cls._root / "template", "A")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(str(cls._root), ignore_errors=True)

    def setUp(self):
        Clocked.setUp(self)
        self.ws = self._root / ("case-" + self._testMethodName)
        shutil.copytree(str(self._template), str(self.ws))

    def cli(self, *args):
        r = run([str(a) for a in args], ws=self.ws, now=NOW)
        return r

    def ok(self, *args):
        r = self.cli(*args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def add(self, kind, start, minutes, *extra):
        return self.ok("plan", "add", SID, "--kind", kind, "--start", start, "--min", minutes, *extra).stdout.split()[0]

    def test_cal_ics_writes_one_event_per_timed_block(self):
        teach = self.add("teach", "2026-10-13T07:00+01:00", 60, "--content", "new skill")
        cold = self.add("cold", "2026-10-15T07:00+01:00", 20, "--content", "cold:T01", "--pair", teach)
        dropped = self.add("review", "2026-10-14T07:00+01:00", 30)
        later = self.add("review", "2026-10-30T07:00+00:00", 30)
        self.ok("plan", "cancel", dropped, "--reason", "learner said no")
        self.ok("plan", "move", teach, "--start", "2026-10-13T07:15+01:00")
        self.ok("plan", "add", SID, "--kind", "cold", "--content", "cold:T02", "--window-from",
                "2026-10-16T09:00+01:00", "--window-to", "2026-10-17T09:00+01:00")  # obligation: no event
        diff = dict((r["block"], r) for r in json.loads(self.ok("plan", "diff", "--json").stdout))

        out = self.ws / "plan" / "ics" / "study-20261012.ics"
        r = self.ok("cal", "ics", out, "--from", "2026-10-12", "--to", "2026-10-25")
        self.assertIn("2 events", r.stdout)
        text = out.read_bytes().decode("utf-8")
        self.assert_physical_lines(text)
        events = dict((e["UID"], e) for e in parse_events(text))
        self.assertEqual(sorted(events), sorted(["%s@indelible" % teach, "%s@indelible" % cold]))

        t = events["%s@indelible" % teach]
        self.assertEqual(t["DTSTART"], "20261013T061500Z")
        self.assertEqual(t["DTEND"], "20261013T071500Z")
        self.assertEqual(t["DTSTAMP"], "20261012T080000Z")
        self.assertEqual(t["SEQUENCE"], "1")
        self.assertEqual(unescape(t["SUMMARY"]), diff[teach]["title"])
        self.assertEqual(unescape(t["DESCRIPTION"]), diff[teach]["notes"])
        self.assertTrue(unescape(t["DESCRIPTION"]).startswith("[ind:%s]\n" % teach))
        self.assertEqual(t["VALARM.TRIGGER"], "-PT15M")

        c = events["%s@indelible" % cold]
        self.assertEqual(c["DTSTART"], "20261015T061500Z")
        self.assertEqual(c["SEQUENCE"], "1")
        self.assertEqual(unescape(c["SUMMARY"]), "IELTS Academic · 2-day recheck (mixed) · 20m")
        self.assertNotIn("Matching headings", unescape(c["SUMMARY"]) + unescape(c["DESCRIPTION"]))

        r = self.ok("cal", "ics", out)  # default: from today, no end
        self.assertIn("3 events", r.stdout)
        events = dict((e["UID"], e) for e in parse_events(out.read_bytes().decode("utf-8")))
        self.assertEqual(events["%s@indelible" % later]["DTSTART"], "20261030T070000Z")
        self.assertEqual(events["%s@indelible" % later]["SEQUENCE"], "0")

    def test_reminder_and_subject_filter(self):
        cfg_path = self.ws / "indelible.json"
        cfg = fio.read_json(cfg_path)
        cfg["calendar"]["reminder_min"] = 30
        fio.write_json(cfg_path, cfg)
        self.add("review", "2026-10-13T07:00+01:00", 30)
        out = self.ws / "plan" / "ics" / "one.ics"
        self.ok("cal", "ics", out, "--subject", SID)
        ev = parse_events(out.read_bytes().decode("utf-8"))[0]
        self.assertEqual(ev["VALARM.TRIGGER"], "-PT30M")
        self.assertEqual(self.cli("cal", "ics", out, "--subject", "nosuch").returncode, 2)
        self.assertEqual(self.cli("cal", "ics", out, "--from", "2026-10-20", "--to", "2026-10-19").returncode, 2)


if __name__ == "__main__":
    unittest.main()
