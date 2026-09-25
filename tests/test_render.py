"""Rendering: the three templates, the renderer chain and backend detection.

HTML and Markdown builds are always tested. A typst build runs only when typst
is on PATH, and a browser PDF build only when Chrome, Chromium or Edge is found.
"""

import html as htmlmod
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from helpers import make_ws, run
    from test_sheet import (NOW, SUBJECT, cold_spec, drills_spec, new_sheet, sheet_row, subject_dir,
                            theory_spec)
except ImportError:  # run as part of the tests package
    from tests.helpers import make_ws, run
    from tests.test_sheet import (NOW, SUBJECT, cold_spec, drills_spec, new_sheet, sheet_row, subject_dir,
                                  theory_spec)

from lib import TEMPLATES_DIR, render
from lib import io as fio

DAY = "2026-10-15"  # a Thursday
GATE_1 = "If your check failed on 2 of items 1–3, or you left 2 blank: stop and send a photo of 1–3."
GATE_2 = "If your check failed on 2 of items 4–6, or you left 2 blank: stop and send a photo of 4–6."
V_RULE = "A word used and not defined on this sheet is my error: mark it V"
CLOSE = "Close this sheet now. The drills come separately."


def visible_text(page):
    """The text a reader sees in an HTML page (tags dropped, entities decoded, spaces collapsed)."""
    body = page.split("<body>", 1)[-1]
    return re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", body))).strip()


def typst_balance_problems(src):
    """Brackets that do not balance outside string literals and comments ([] if well formed)."""
    stack, i, n = [], 0, len(src)
    pairs = {")": "(", "]": "[", "}": "{"}
    while i < n:
        c = src[i]
        if c == '"':
            i += 1
            while i < n and src[i] != '"':
                if src[i] == "\\":
                    i += 1
                elif src[i] == "\n":
                    return ["newline inside a string literal at %d" % i]
                i += 1
            if i >= n:
                return ["unterminated string literal"]
        elif src.startswith("//", i):
            while i < n and src[i] != "\n":
                i += 1
            continue
        elif c in "([{":
            stack.append(c)
        elif c in ")]}":
            if not stack or stack[-1] != pairs[c]:
                return ["unbalanced %s at %d" % (c, i)]
            stack.pop()
        i += 1
    return ["unclosed %s" % "".join(stack)] if stack else []


class Base(unittest.TestCase):
    def setUp(self):
        self._old_now = os.environ.get("INDELIBLE_NOW")
        os.environ["INDELIBLE_NOW"] = NOW
        self.tmp = Path(tempfile.mkdtemp(prefix="indelible-render-"))

    def tearDown(self):
        if self._old_now is None:
            os.environ.pop("INDELIBLE_NOW", None)
        else:
            os.environ["INDELIBLE_NOW"] = self._old_now
        shutil.rmtree(str(self.tmp), ignore_errors=True)


# ==========================================================================
# Templates (in-process)
# ==========================================================================

class HtmlTemplateTests(Base):
    def setUp(self):
        Base.setUp(self)
        self.page = render.render_html(drills_spec(), date=DAY, tools="none")
        self.text = visible_text(self.page)

    def test_header_has_title_date_weekday_minutes_count_and_provenance(self):
        self.assertIn('<h1 id="sheet-title">Other words, same idea</h1>', self.page)
        self.assertIn("Thursday 15 October 2026", self.text)
        self.assertIn('datetime="2026-10-15"', self.page)
        self.assertIn("About 12 min · 6 questions · Practice — written by Claude", self.text)

    def test_rules_box(self):
        rules = visible_text(self.page.split('<section class="rules"', 1)[1].split("</section>", 1)[0])
        for s in ("Closed book", "Answer on paper, one answer in each box.",
                  "Write the check beside each answer.", "“I don't know” is always an accepted answer.",
                  "Stop after 12 minutes.", "Tools allowed: none.", V_RULE):
            self.assertIn(s, rules)

    def test_items_asks_check_lines_and_hints(self):
        self.assertLess(self.text.index("0. Start time:"), self.text.index("Question 1."))
        self.assertEqual(self.text.count("Check:"), 6)
        self.assertEqual(self.text.count("Read the new sentence aloud with your answer in it"), 6)
        self.assertEqual(self.page.count('class="box"'), 6)
        for i in range(1, 7):
            self.assertIn("%da Write it again with a new verb:" % i, self.text)

    def test_block_titles_and_failure_gate_after_item_3_of_each_block(self):
        t = self.text
        self.assertIn("Block A: swap one word", t)
        self.assertIn("Block B: swap one word", t)
        self.assertEqual(t.count("If your check failed on 2 of items"), 2)
        self.assertTrue(t.index("Question 3.") < t.index(GATE_1) < t.index("Question 4."))
        self.assertTrue(t.index("Question 6.") < t.index(GATE_2) < t.index("Stop time:"))

    def test_end_lines(self):
        t = self.text
        self.assertTrue(t.index("Question 6.") < t.index("Stop time:") < t.index("Least sure of (item numbers):"))
        page = render.render_html(drills_spec(least_sure=False), date=DAY)
        self.assertNotIn("Least sure of", visible_text(page))

    def test_print_css_a4_and_page_x_of_y(self):
        self.assertIn("size: A4", self.page)
        self.assertIn('content: "page " counter(page) " of " counter(pages)', self.page)

    def test_self_contained_and_accessible(self):
        low = self.page.lower()
        for bad in ("http://", "https://", "<script", "<link", "url(", "@import", " src="):
            self.assertNotIn(bad, low)
        self.assertTrue(self.page.startswith("<!doctype html>"))
        self.assertIn('<html lang="en">', self.page)
        self.assertIn('<main aria-labelledby="sheet-title">', self.page)
        self.assertIn('<section class="rules" aria-labelledby="rules-h">', self.page)
        self.assertEqual(self.page.count('role="group"'), 6)
        self.assertIn('<h2 id="blk-1">Block A: swap one word</h2>', self.page)
        self.assertNotIn("$", self.page.replace("$$", ""), "every template placeholder is filled")

    def test_learner_text_is_escaped(self):
        spec = drills_spec()
        spec["items"][0]["text"] = 'Tag <script>alert(1)</script> & "quotes" x² ≤ 3'
        page = render.render_html(spec, date=DAY, lang="pt")
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn('<html lang="pt">', page)
        self.assertIn("x² ≤ 3", visible_text(page))

    def test_measurement_provenance(self):
        self.assertIn("Measurement — written by Claude", visible_text(render.render_html(cold_spec(), date=DAY)))
        spec = cold_spec()
        for it in spec["items"]:
            it["origin"] = "official:Cambridge 18 Test 2"
        self.assertIn("Measurement — official", visible_text(render.render_html(spec, date=DAY)))
        self.assertNotIn("If your check failed", visible_text(render.render_html(cold_spec(), date=DAY)),
                         "the failure gate is for drills only")

    def test_theory_layout(self):
        t = visible_text(render.render_html(theory_spec(), date=DAY))
        order = ["Rules", "0. Start time:", "Before this sheet", "You can find the verb in a sentence.",
                 "Words on this sheet", "paraphrase (paráfrase)", "the same idea said with other words",
                 "A worked case", "How to paraphrase", "Watch out", "Question 1.", "Stop time:", CLOSE]
        positions = [t.index(s) for s in order]
        self.assertEqual(positions, sorted(positions))
        self.assertTrue(t.endswith(CLOSE))
        self.assertIn("Read this sheet once", t)
        self.assertNotIn("Least sure of", t)


class TypstAndMarkdownTests(Base):
    def test_typst_source_is_well_formed_and_complete(self):
        src = render.render_typst(drills_spec(), date=DAY)
        self.assertEqual(typst_balance_problems(src), [])
        self.assertIn('counter(page).display("1 of 1", both: true)', src)
        self.assertIn('paper: "a4"', src)
        self.assertIn('"Noto Serif", "Libertinus Serif", "New Computer Modern"', src)
        for s in ('#"Thursday 15 October 2026"', '#"Start time:"', '#"Stop time:"',
                  '#"Least sure of (item numbers):"', '#"%s."' % V_RULE, '#"%s"' % GATE_1, '#"%s"' % GATE_2,
                  '#"About 12 min · 6 questions · Practice — written by Claude"'):
            self.assertIn(s, src)
        self.assertEqual(src.count("#checkline()"), 6)
        self.assertEqual(src.count("#answer("), 6)
        self.assertLess(src.index(GATE_1), src.index('#"4."'))
        self.assertNotRegex(src, r"\$[a-z_]+", "every template placeholder is filled")

    def test_typst_learner_text_is_never_markup(self):
        self.assertEqual(render.ts('a"b\\c'), '"a\\"b\\\\c"')
        spec = drills_spec()
        spec["items"][0]["text"] = 'Costs #1 = $5 [draft] *bold* // not a comment "quoted" back\\slash\nline two'
        spec["title"] = "Title with $dollar and #hash"
        src = render.render_typst(spec, date=DAY)
        self.assertEqual(typst_balance_problems(src), [])
        self.assertIn('#"Costs #1 = $5 [draft] *bold* // not a comment \\"quoted\\" back\\\\slash" '
                      '#linebreak() #"line two"', src)
        self.assertIn('#set document(title: "Title with $dollar and #hash")', src)

    def test_typst_theory_ends_with_the_close_line(self):
        src = render.render_typst(theory_spec(), date=DAY)
        self.assertEqual(typst_balance_problems(src), [])
        self.assertLess(src.index('#"Stop time:"'), src.index('#"%s"' % CLOSE))
        self.assertTrue(src.rstrip().endswith('[#strong[#"%s"]]' % CLOSE))

    def test_markdown_has_every_element(self):
        md = render.render_markdown(drills_spec(), date=DAY)
        self.assertTrue(md.startswith("# Other words, same idea\n"))
        for s in ("**Thursday 15 October 2026** · About 12 min · 6 questions · Practice — written by Claude",
                  "> **Rules**", "Closed book", "Write the check beside each answer.", "Stop after 12 minutes.",
                  "Tools allowed: none.", V_RULE, "**0.** Start time: ____", "## Block A: swap one word",
                  "> **%s**" % GATE_1, "> **%s**" % GATE_2, "Stop time: ____", "Least sure of (item numbers): ____"):
            self.assertIn(s, md)
        self.assertEqual(md.count("Check: "), 6)
        self.assertLess(md.index(GATE_1), md.index("**4.**"))
        self.assertNotRegex(md, r"\$[a-z_]+")

    def test_markdown_theory_ends_with_the_close_line_and_escapes(self):
        md = render.render_markdown(theory_spec(), date=DAY)
        self.assertEqual(md.rstrip().splitlines()[-1], "**%s**" % CLOSE)
        spec = drills_spec()
        spec["items"][0]["text"] = "# not a heading *not bold*"
        md = render.render_markdown(spec, date=DAY)
        self.assertIn("\\# not a heading \\*not bold\\*", md)

    def test_templates_ship_with_placeholders(self):
        for name, marks in (("html/sheet.html", ["$lang", "$title", "$body"]),
                            ("typ/sheet.typ", ["$title_str", "$lang", "$body"]),
                            ("md/sheet.md", ["$title", "$date_line", "$meta", "$rules", "$body"])):
            text = (TEMPLATES_DIR / name).read_text(encoding="utf-8")
            for m in marks:
                self.assertIn(m, text, name)


class BackendTests(Base):
    def test_detect_backends_quick_lists_the_chain(self):
        rows = render.detect_backends(quick=True)
        self.assertEqual([r["name"] for r in rows], ["typst", "tectonic", "xelatex", "lualatex", "chrome", "html", "md"])
        by = dict((r["name"], r) for r in rows)
        self.assertTrue(by["html"]["ok"] and by["md"]["ok"])
        self.assertFalse(by["xelatex"]["ok"], "LaTeX sheets arrive in v0.2")
        for r in rows:
            self.assertEqual(set(r), {"name", "found", "ok", "detail", "path"})
        self.assertEqual(render.working_backends(quick=True)[-2:], ["html", "md"])

    def test_backend_order(self):
        self.assertEqual(render.backend_order("md"), ["md"])
        self.assertEqual(render.backend_order("html", preferred="typst"), ["html"])
        self.assertEqual(render.backend_order("pdf", preferred="html"), ["typst", "chrome", "html", "md"])
        self.assertEqual(render.backend_order(None, preferred="html"), ["html", "typst", "chrome", "md"])
        self.assertEqual(render.backend_order(None, preferred="chrome"), ["chrome", "typst", "html", "md"])
        self.assertEqual(render.backend_order(None, preferred="bogus"), ["typst", "chrome", "html", "md"])

    def test_pdf_request_falls_back_to_html_when_no_pdf_backend_works(self):
        with mock.patch.object(render, "find_typst", return_value=None), \
                mock.patch.object(render, "find_chrome", return_value=None):
            res = render.render_sheet(drills_spec(), self.tmp, "ielts-drills-01", fmt="pdf", date=DAY)
            self.assertEqual(res["backend"], "html")
            self.assertEqual(res["files"], [self.tmp / "ielts-drills-01.html"])
            self.assertIn("typst not found", res["notes"])
            rows = render.detect_backends()
            self.assertFalse(dict((r["name"], r) for r in rows)["chrome"]["ok"])

    def test_a_failed_pdf_moves_to_the_next_backend(self):
        with mock.patch.object(render, "find_typst", return_value="/nonexistent/typst"), \
                mock.patch.object(render, "find_chrome", return_value=None):
            res = render.render_sheet(drills_spec(), self.tmp, "x", fmt=None, date=DAY)
        self.assertEqual(res["backend"], "html")
        self.assertFalse((self.tmp / "x.typ").exists(), "a failed typst source is not left behind")
        self.assertTrue(any("typst" in n for n in res["notes"]))

    def test_unknown_format_is_a_usage_error(self):
        from lib import UsageError
        with self.assertRaises(UsageError):
            render.render_sheet(drills_spec(), self.tmp, "x", fmt="docx")


# ==========================================================================
# Through the CLI
# ==========================================================================

class BuildCliTests(Base):
    def setUp(self):
        Base.setUp(self)
        self.ws = make_ws(self.tmp, "A")

    def linted(self, spec):
        self.assertEqual(new_sheet(self.ws, spec).returncode, 0)
        r = run(["sheet", "lint", SUBJECT, spec["id"]], ws=self.ws, now=NOW)
        self.assertEqual(r.returncode, 0, r.stdout)

    def build(self, sheet_id, *extra):
        return run(["sheet", "build", SUBJECT, sheet_id] + list(extra), ws=self.ws, now=NOW)

    def test_md_and_html_builds_always_work(self):
        spec = drills_spec()
        self.linted(spec)
        for fmt in ("md", "html"):
            r = self.build(spec["id"], "--format", fmt)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            out = Path(r.stdout.splitlines()[0])
            self.assertEqual(out, (subject_dir(self.ws) / "sheets" / "2026-10" / ("ielts-drills-01." + fmt)).resolve())
            self.assertTrue(out.is_file())
            self.assertIn("Other words, same idea", out.read_text(encoding="utf-8"))
            # built ahead, with no block and no session open: a blank date to fill in, not the build day
            self.assertIn("Date: ____________", out.read_text(encoding="utf-8"))
            self.assertNotIn("Monday 12 October 2026", out.read_text(encoding="utf-8"))
            self.assertNotIn("note:", r.stdout)
            row = sheet_row(self.ws, spec["id"])
            self.assertEqual(row["status"], "rendered")
            self.assertEqual(row["files"], ["sheets/2026-10/ielts-drills-01." + fmt])

    def test_recorded_backend_is_used_first(self):
        cfg_path = Path(self.ws) / "indelible.json"
        cfg = fio.read_json(cfg_path)
        cfg["render"] = {"backend": "html", "verified_at": NOW}
        fio.write_json(cfg_path, cfg)
        spec = drills_spec()
        self.linted(spec)
        r = self.build(spec["id"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(r.stdout.splitlines()[0].endswith("ielts-drills-01.html"))
        self.assertEqual(sheet_row(self.ws, spec["id"])["files"], ["sheets/2026-10/ielts-drills-01.html"])

    def test_date_flag_sets_the_header_and_the_month_folder(self):
        spec = drills_spec()
        self.linted(spec)
        r = self.build(spec["id"], "--format", "md", "--date", "2026-11-02")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = subject_dir(self.ws) / "sheets" / "2026-11" / "ielts-drills-01.md"
        self.assertIn("Monday 2 November 2026", out.read_text(encoding="utf-8"))
        self.assertEqual(self.build(spec["id"], "--format", "md", "--date", "2 Nov").returncode, 2)

    def test_theory_sheet_builds(self):
        spec = theory_spec()
        self.linted(spec)
        r = self.build(spec["id"], "--format", "html")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        page = Path(r.stdout.splitlines()[0]).read_text(encoding="utf-8")
        self.assertTrue(visible_text(page).endswith(CLOSE))

    def test_doctor_uses_render_detect_backends(self):
        r = run(["doctor", "--quick", "--json"], ws=self.ws, now=NOW)
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data["renderer_source"], "render")
        self.assertIn("md", [x["name"] for x in data["renderers"]])

    @unittest.skipUnless(shutil.which("typst"), "typst is not on PATH")
    def test_typst_pdf_build(self):
        spec = drills_spec()
        self.linted(spec)
        r = self.build(spec["id"], "--format", "pdf")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        row = sheet_row(self.ws, spec["id"])
        self.assertEqual(row["files"], ["sheets/2026-10/ielts-drills-01.pdf", "sheets/2026-10/ielts-drills-01.typ"])
        pdf = subject_dir(self.ws) / row["files"][0]
        self.assertTrue(render.pdf_complete(pdf))
        theory = theory_spec()
        self.linted(theory)
        self.assertEqual(self.build(theory["id"], "--format", "pdf").returncode, 0)
        self.assertTrue(sheet_row(self.ws, theory["id"])["files"][0].endswith(".pdf"))

    @unittest.skipUnless(render.find_chrome(), "no Chrome, Chromium or Edge found")
    def test_browser_pdf_build(self):
        spec = drills_spec()
        self.linted(spec)
        with_typst = bool(shutil.which("typst"))
        r = self.build(spec["id"], "--format", "pdf")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        if "note: no PDF" in r.stdout:
            self.skipTest("a browser is installed but could not print here")
        row = sheet_row(self.ws, spec["id"])
        self.assertTrue(row["files"][0].endswith(".pdf"))
        self.assertTrue(row["files"][1].endswith(".typ" if with_typst else ".html"))
        self.assertTrue(render.pdf_complete(subject_dir(self.ws) / row["files"][0]))


if __name__ == "__main__":
    unittest.main()
