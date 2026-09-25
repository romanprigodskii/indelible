"""Sheet rendering: one visible sheet spec -> HTML, typst or Markdown, and the PDF backends.

The renderer chain (CONTRACT section 7.4) is::

    typst  ->  Chrome/Chromium/Edge headless printing the HTML to PDF  ->  HTML  ->  Markdown

``sheet build`` uses the backend recorded by ``doctor`` first, then tries the
chain in order. A backend that fails moves on to the next one automatically.

Everything here reads only the *visible* spec. The answer key is never passed
to this module, so nothing it writes can contain an answer.

Public API::

    detect_backends(quick=False) -> [{"name","found","ok","detail","path"}, ...]
        one row per backend checked, in chain order (typst, the LaTeX engines,
        chrome, html, md). ``ok`` is the result of a real test compile of the
        shipped template (``quick`` only checks that the program exists).
    working_backends(quick=False) -> ["typst", "chrome", "html", "md"] (the ok ones)
    render_html(spec, **ctx) / render_typst(spec, **ctx) / render_markdown(spec, **ctx) -> str
    render_sheet(spec, out_dir, base, fmt=None, preferred=None, **ctx)
        -> {"backend", "files": [primary, source?], "notes": [...]}
    visible_texts(spec) -> [str]   every learner-visible string the spec produces (lint L8)
    provenance(spec) -> "Practice — written by Claude" | "Measurement — ..."

``ctx`` keywords: ``date`` (the sitting date; default today; ``False`` prints
a blank date line to fill in, for a sheet built ahead with no block), ``tools``
(default ``spec.tools`` or "none"), ``lang`` (an ISO 639 code for
hyphenation), ``profile`` (the subject profile: ``code`` sheets get the code
wording in the rules box).

Code: item text and theory bodies may hold fenced code blocks (lines between
```` ``` ```` fences) and inline `code spans`. They are printed verbatim in a
monospace font with their indentation: ``<pre><code>`` in HTML, fenced
blocks and spans in Markdown, raw blocks in typst.

Answer boxes are sized from the question's ``answer_form`` (``letter``,
``number``, ``word`` and ``test-line`` get a one-line box; ``none`` gets no
box, e.g. a code task answered in the editor), or its label ("letter",
"number", "one word", "TRUE / FALSE / NOT GIVEN"), else from the layer.

Python 3.9+, standard library only. Unicode maths only (no LaTeX) in v0.1.
"""

import html as _html
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from string import Template

from lib import TEMPLATES_DIR, dates, schema
from lib import io as fio

BACKENDS = ("typst", "chrome", "html", "md")
PDF_BACKENDS = ("typst", "chrome")
LATEX_ENGINES = ("tectonic", "xelatex", "lualatex")
FORMATS = ("pdf", "html", "md")
RENDER_TIMEOUT_S = 60

READ_THEN_CLOSE = ("theory", "external", "example")
THEORY_BEARING = ("theory", "external", "example", "repair")
BLANK_DATE = "Date: ____________"
NO_LEAST_SURE = ("theory", "external", "example", "triage")

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]

V_RULE = "A word used and not defined on this sheet is my error: mark it V."
CLOSE_LINE_THEORY = "Close this sheet now. The drills come separately."
CLOSE_LINE_EXAMPLE = "Close this sheet now, then go back to your question."
START_LABEL = "Start time:"
STOP_LABEL = "Stop time:"
LEAST_SURE_LABEL = "Least sure of (item numbers):"
CHECK_LABEL = "Check:"

# Answer-box heights (mm) by layer; generous, for handwriting.
BOX_MM = {"procedural": 32, "conceptual": 30, "verbal": 18, "reading": 16, "production": 80, "code": 50}
BOX_MM_DEFAULT = 24
# ... but the answer's form wins: a letter or a number needs one line, not half a page.
FORM_MM = {"letter": 12, "choice": 12, "number": 14, "numeral": 12, "word": 14, "one-word": 14,
           "test-line": 14, "short": 18, "sentence": 24, "long": 80, "essay": 80, "extended": 80,
           "code": 50, "none": 0}
SMALL_BOX_MM = 14
SMALL_LABEL_RE = re.compile(r"\b(letter|number|numeral|one word|roman numeral|true|false|not given)\b", re.I)
FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})[ \t]*([A-Za-z0-9_+.#-]*)[ \t]*$")
CODE_SPAN_RE = re.compile(r"(`+)(?!`)(.+?)(?<!`)\1(?!`)")
KEEP_MAX_CHARS = 700  # items with a stem up to this long stay on one page with their questions


# ==========================================================================
# Small helpers
# ==========================================================================

def _s(value):
    """Any value -> a clean one-line-or-more string ('' for None)."""
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\r", "\n")


def _num(x):
    """12.0 -> '12'; 7.5 -> '7.5'."""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return _s(x)
    if f == int(f):
        return str(int(f))
    return ("%.1f" % f).rstrip("0").rstrip(".")


def _minutes_int(x):
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    i = int(f)
    return i if f == i else i + 1


def paragraphs(text):
    """Text -> paragraphs (split on blank lines), each a list of lines."""
    text = _s(text).strip("\n")
    if not text.strip():
        return []
    out = []
    for block in re.split(r"\n[ \t]*\n", text):
        lines = [ln.rstrip() for ln in block.split("\n")]
        lines = [ln for ln in lines if ln.strip()]
        if lines:
            out.append(lines)
    return out


def date_line(d):
    """date -> 'Thursday 15 October 2026' (locale-independent)."""
    d = dates.to_date(d)
    return "%s %d %s %d" % (dates.WEEKDAY_NAMES[d.weekday()], d.day, MONTHS[d.month - 1], d.year)


def segments(text):
    """Text -> blocks: ``{"kind": "p", "lines": [...]}`` paragraphs (split on blank
    lines) and ``{"kind": "code", "lang": str, "text": str}`` fenced code blocks,
    whose lines keep their indentation and blank lines."""
    out, para, code, fence, lang = [], [], [], None, ""

    def flush():
        if para:
            out.append({"kind": "p", "lines": list(para)})
            del para[:]

    for raw in _s(text).split("\n"):
        if fence is None:
            m = FENCE_RE.match(raw)
            if m:
                flush()
                fence, lang, code = m.group(1), m.group(2), []
                continue
            if not raw.strip():
                flush()
                continue
            para.append(raw.rstrip())
        else:
            stripped = raw.strip()
            if stripped.startswith(fence) and not stripped.strip(fence[0]):
                out.append({"kind": "code", "lang": lang, "text": "\n".join(code)})
                fence = None
                continue
            code.append(raw.rstrip().expandtabs(4))
    if fence is not None:
        out.append({"kind": "code", "lang": lang, "text": "\n".join(code)})
    flush()
    return out


def split_code_spans(line):
    """A line -> [(is_code, text)] around inline `code spans` (the backticks dropped)."""
    parts, pos = [], 0
    for m in CODE_SPAN_RE.finditer(line):
        if m.start() > pos:
            parts.append((False, line[pos:m.start()]))
        body = m.group(2)
        if len(m.group(1)) > 1 and body.startswith(" ") and body.endswith(" ") and body.strip():
            body = body[1:-1]
        parts.append((True, body))
        pos = m.end()
    if pos < len(line):
        parts.append((False, line[pos:]))
    return parts or [(False, "")]


def _items(spec):
    return [it for it in (spec.get("items") or []) if isinstance(it, dict)]


def _asks(item):
    return [a for a in (item.get("asks") or []) if isinstance(a, dict)]


def ask_count(spec):
    return sum(len(_asks(it)) for it in _items(spec))


def provenance(spec):
    """The header's provenance line."""
    t = spec.get("type")
    if t in schema.MEASURING_TYPES:
        items = _items(spec)
        if items and all(_s(it.get("origin")).startswith("official:") for it in items):
            return "Measurement — official"
        return "Measurement — written by Claude"
    return "Practice — written by Claude"


def _range_text(nums):
    """[1, 2, 3] -> '1–3'; [1, 3, 5] -> '1, 3 and 5'."""
    nums = [n for n in nums]
    try:
        ints = [int(n) for n in nums]
        if ints == list(range(ints[0], ints[0] + len(ints))):
            return "%d–%d" % (ints[0], ints[-1])
    except (TypeError, ValueError):
        pass
    parts = [_s(n) for n in nums]
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def gate_text(first_three):
    r = _range_text(first_three)
    return ("If your check failed on 2 of items %s, or you left 2 blank: "
            "stop and send a photo of %s." % (r, r))


def _box_mm(spec, item, ask):
    """Answer-box height in mm (0: no box): the ask's box_mm, its answer_form (or the
    item's), a label asking for a letter, number or one word, the sheet's form, the layer."""
    v = ask.get("box_mm")
    if isinstance(v, (int, float)) and not isinstance(v, bool) and (v == 0 or 8 <= v <= 250):
        return int(v)
    form = _s(ask.get("answer_form") or item.get("answer_form")).strip().lower()
    if form in FORM_MM:
        return FORM_MM[form]
    if SMALL_LABEL_RE.search(_s(ask.get("label"))):
        return SMALL_BOX_MM
    form = _s(spec.get("answer_form")).lower()
    if form in ("long", "essay", "extended"):
        return 80
    if form == "code":
        return 50
    return BOX_MM.get(item.get("layer"), BOX_MM_DEFAULT)


def is_code_sheet(spec, profile=None):
    if profile == "code" or _s(spec.get("answer_form")).lower() == "code":
        return True
    items = _items(spec)
    return bool(items) and all(it.get("layer") == "code" for it in items)


# ==========================================================================
# The document model (shared by every format)
# ==========================================================================

def rules(spec, tools, fmt="html", profile=None):
    """The rules box lines, in order (the wording depends on the sheet type and profile)."""
    t = spec.get("type")
    items = _items(spec)
    code = is_code_sheet(spec, profile)
    any_check = any(a.get("check") for it in items for a in _asks(it))
    minutes = _minutes_int(spec.get("est_min"))
    out = []
    if t in ("theory", "example"):
        out.append("Read this sheet once, doing the pencil items as you meet them. Then close it: "
                   "the questions that follow are closed book.")
    elif t == "external":
        out.append("Read the pages listed below, then close the book. The pencil items are closed book: "
                   "no notes, no book, no search.")
    elif t == "repair":
        out.append("Read the fix once, with the page open, doing its pencil items as you meet them. "
                   "Then close it: anything after it is closed book.")
    else:
        out.append("Closed book: no notes, no book, no search, no AI.")
    if code:
        out.append("Write your code in your editor, one file or answer for each question; send the files "
                   "(or paste them) when you stop.")
    elif fmt == "md":
        out.append("Answer on paper (or in a typed file), one answer for each box.")
    else:
        out.append("Answer on paper, one answer in each box.")
    if code:
        check_how = ("Work backwards from it: work out the output for one input by hand, then run it and "
                     "compare, or trace one case through line by line.")
    else:
        check_how = ("Work backwards from it: put it back in, rebuild the total, or test the "
                     "definition you used against the question's words.")
    if any_check or not items:
        out.append("Write the check beside each answer. " + check_how)
    else:
        out.append("Write the check beside each answer where a Check line is printed. " + check_how)
    out.append("“I don't know” is always an accepted answer.")
    if minutes:
        out.append("Stop after %d minute%s." % (minutes, "" if minutes == 1 else "s"))
    else:
        out.append("Stop when the time set for this sheet is up.")
    out.append("Tools allowed: %s." % (_s(tools).strip().rstrip(".") or "none"))
    out.append(V_RULE)
    return out


def build_model(spec, date=None, tools=None, fmt="html", profile=None):
    """Everything a template shows, as plain strings. No key content ever enters here.

    ``date`` None means today; ``False`` prints a blank date line to fill in.
    """
    t = spec.get("type")
    blank = date is False
    d = None if blank else (dates.to_date(date) if date else dates.today())
    tools = tools if tools not in (None, "") else (spec.get("tools") or "none")
    n_asks = ask_count(spec)
    est = spec.get("est_min")
    meta = "About %s min · %d question%s · %s" % (_num(est), n_asks, "" if n_asks == 1 else "s", provenance(spec))

    items = _items(spec)
    by_n = {}
    for it in items:
        by_n.setdefault(it.get("n"), it)
    groups, used = [], set()
    for b in spec.get("blocks") or []:
        if not isinstance(b, dict):
            continue
        its = []
        for n in b.get("items") or []:
            key = n
            if key in by_n and key not in used:
                its.append(by_n[key])
                used.add(key)
        if not its:
            continue
        gate = None
        if t == "drills" and len(its) >= 3:
            gate = gate_text([it.get("n") for it in its[:3]])
        groups.append({"title": _s(b.get("title")).strip() or None, "items": its, "gate": gate})
    rest = [it for it in items if it.get("n") not in used]
    if rest:
        groups.append({"title": None, "items": rest, "gate": None})

    model_groups = []
    for g in groups:
        mitems = []
        for it in g["items"]:
            masks = []
            for a in _asks(it):
                hint = _s(a.get("check_hint")).strip() or None
                masks.append({"id": _s(a.get("id")), "label": _s(a.get("label")).strip(),
                              "check": bool(a.get("check")), "hint": hint if a.get("check") else None,
                              "box_mm": _box_mm(spec, it, a)})
            keep = len(_s(it.get("text"))) <= KEEP_MAX_CHARS and len(masks) <= 2
            mitems.append({"n": _s(it.get("n")), "paras": segments(it.get("text")), "asks": masks, "keep": keep})
        model_groups.append({"title": g["title"], "items": mitems, "gate": g["gate"]})

    theory = None
    th = spec.get("theory")
    if isinstance(th, dict) and t in THEORY_BEARING:
        words = []
        for w in th.get("words") or []:
            if isinstance(w, dict) and _s(w.get("term")).strip():
                words.append({"term": _s(w.get("term")).strip(), "gloss": _s(w.get("gloss")).strip(),
                              "def": _s(w.get("def")).strip()})
        sections = []
        for sec in th.get("sections") or []:
            if isinstance(sec, dict):
                sections.append({"kind": _s(sec.get("kind")) or "text", "title": _s(sec.get("title")).strip(),
                                 "paras": segments(sec.get("body"))})
        theory = {
            "floor": [_s(f).strip() for f in (th.get("floor") or []) if _s(f).strip()],
            "words": words,
            "sections": sections,
            "pages": _s(th.get("pages")).strip() or None,
        }

    close_line = None
    if t in ("theory", "external"):
        close_line = CLOSE_LINE_THEORY
    elif t == "example":
        close_line = CLOSE_LINE_EXAMPLE

    return {
        "type": t,
        "title": _s(spec.get("title")).strip() or "Sheet",
        "date_line": BLANK_DATE if d is None else date_line(d),
        "date": "" if d is None else d.isoformat(),
        "meta": meta,
        "provenance": provenance(spec),
        "rules": rules(spec, tools, fmt=fmt, profile=profile),
        "theory": theory,
        "groups": model_groups,
        "least_sure": bool(spec.get("least_sure")),
        "close_line": close_line,
    }


def visible_texts(spec):
    """Every learner-visible string that comes from the spec (for the key-leak check).

    The fixed template wording (rules box, labels) is left out: it is the same
    on every sheet and is not the question.
    """
    out = [_s(spec.get("title"))]
    for b in spec.get("blocks") or []:
        if isinstance(b, dict):
            out.append(_s(b.get("title")))
    for it in _items(spec):
        out.append(_s(it.get("text")))
        for a in _asks(it):
            out.append(_s(a.get("label")))
            out.append(_s(a.get("check_hint")))
    th = spec.get("theory")
    if isinstance(th, dict):
        out.extend(_s(f) for f in (th.get("floor") or []))
        for w in th.get("words") or []:
            if isinstance(w, dict):
                out.extend([_s(w.get("term")), _s(w.get("gloss")), _s(w.get("def"))])
        for sec in th.get("sections") or []:
            if isinstance(sec, dict):
                out.extend([_s(sec.get("title")), _s(sec.get("body"))])
        out.append(_s(th.get("pages")))
    return [x for x in out if x.strip()]


# ==========================================================================
# Templates
# ==========================================================================

def template_text(fmt):
    name = {"html": "html/sheet.html", "typst": "typ/sheet.typ", "md": "md/sheet.md"}[fmt]
    text = fio.read_text(TEMPLATES_DIR / name)
    if text is None:
        from lib import DataError
        raise DataError("Missing skill asset: assets/templates/%s" % name)
    return text


def _lang(lang):
    lang = _s(lang).strip().lower()
    return lang if re.match(r"^[a-z]{2,3}$", lang) else "en"


# ---- HTML -------------------------------------------------------------------

def _e(text):
    return _html.escape(_s(text), quote=True)


def _html_line(line):
    return "".join("<code>%s</code>" % _e(t) if is_code else _e(t) for is_code, t in split_code_spans(line))


def _html_paras(paras, cls=None):
    attr = ' class="%s"' % cls if cls else ""
    out = []
    for blk in paras:
        if isinstance(blk, dict) and blk.get("kind") == "code":
            lang = ' data-lang="%s"' % _e(blk["lang"]) if blk.get("lang") else ""
            out.append('<pre class="code"%s><code>%s</code></pre>\n' % (lang, _e(blk["text"])))
            continue
        lines = blk["lines"] if isinstance(blk, dict) else blk
        out.append("<p%s>%s</p>\n" % (attr, "<br>".join(_html_line(ln) for ln in lines)))
    return "".join(out)


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", _s(text).lower()).strip("-") or "x"


def render_html(spec, date=None, tools=None, lang="en", profile=None):
    m = build_model(spec, date=date, tools=tools, fmt="html", profile=profile)
    o = []
    o.append('<main aria-labelledby="sheet-title">\n')
    o.append('<header class="sheet-head">\n')
    if m["date"]:
        when = '<time datetime="%s">%s</time>' % (_e(m["date"]), _e(m["date_line"]))
    else:
        when = _e(m["date_line"])
    o.append('<div class="head-row"><h1 id="sheet-title">%s</h1>'
             '<p class="when">%s</p></div>\n' % (_e(m["title"]), when))
    o.append('<p class="meta">%s</p>\n' % _e(m["meta"]))
    o.append('</header>\n')

    o.append('<section class="rules" aria-labelledby="rules-h">\n<h2 id="rules-h">Rules</h2>\n<ul>\n')
    for r in m["rules"]:
        cls = ' class="v-rule"' if r == V_RULE else ""
        o.append("<li%s>%s</li>\n" % (cls, _e(r)))
    o.append("</ul>\n</section>\n")

    o.append('<p class="line start"><span class="num">0.</span> <span>%s</span> '
             '<span class="fill short" aria-hidden="true"></span></p>\n' % _e(START_LABEL))

    th = m["theory"]
    if th:
        if th["floor"]:
            o.append('<section class="floor" aria-labelledby="floor-h">\n<h2 id="floor-h">Before this sheet</h2>\n<ul>\n')
            o.extend("<li>%s</li>\n" % _e(f) for f in th["floor"])
            o.append("</ul>\n</section>\n")
        if th["pages"]:
            o.append('<section class="pages" aria-labelledby="pages-h">\n<h2 id="pages-h">Read</h2>\n'
                     '<p>%s</p>\n</section>\n' % _e(th["pages"]))
        if th["words"]:
            o.append('<section class="words" aria-labelledby="words-h">\n<h2 id="words-h">Words on this sheet</h2>\n<dl>\n')
            for w in th["words"]:
                gloss = ' <span class="gloss">(%s)</span>' % _e(w["gloss"]) if w["gloss"] else ""
                o.append("<dt>%s%s</dt><dd>%s</dd>\n" % (_e(w["term"]), gloss, _e(w["def"])))
            o.append("</dl>\n</section>\n")
        for i, sec in enumerate(th["sections"], start=1):
            hid = "sec-%d" % i
            o.append('<section class="sec sec-%s" aria-labelledby="%s">\n' % (_e(_slug(sec["kind"])), hid))
            title = sec["title"] or {"rule": "The rule", "warning": "Warning", "worked": "Worked case",
                                     "contrast": "Contrast", "both_hold": "When both hold",
                                     "where": "Where this lives"}.get(sec["kind"], "Notes")
            o.append('<h2 id="%s">%s</h2>\n' % (hid, _e(title)))
            o.append(_html_paras(sec["paras"]))
            o.append("</section>\n")

    for gi, g in enumerate(m["groups"], start=1):
        if g["title"]:
            o.append('<section class="block" aria-labelledby="blk-%d">\n<h2 id="blk-%d">%s</h2>\n'
                     % (gi, gi, _e(g["title"])))
        else:
            o.append('<section class="block" aria-label="Questions">\n')
        for idx, it in enumerate(g["items"], start=1):
            qid = "q-%s" % _slug(it["n"])
            o.append('<article class="item%s" aria-labelledby="%s">\n' % (" keep" if it["keep"] else "", qid))
            o.append('<h3 id="%s" class="qnum"><span class="sr-only">Question </span>%s.</h3>\n'
                     % (qid, _e(it["n"])))
            o.append('<div class="qbody">\n')
            if it["paras"]:
                o.append('<div class="stem">\n%s</div>\n' % _html_paras(it["paras"]))
            for a in it["asks"]:
                aid = "a-%s" % _slug(a["id"])
                o.append('<div class="ask" role="group" aria-labelledby="%s">\n' % aid)
                o.append('<p class="ask-label" id="%s"><span class="ask-id">%s</span> %s</p>\n'
                         % (aid, _e(a["id"]), _html_line(a["label"])))
                if a["box_mm"]:
                    o.append('<div class="box" style="min-height:%dmm" aria-hidden="true"></div>\n' % a["box_mm"])
                if a["check"]:
                    o.append('<p class="check"><span>%s</span> <span class="fill" aria-hidden="true"></span></p>\n'
                             % _e(CHECK_LABEL))
                    if a["hint"]:
                        o.append('<p class="hint">%s</p>\n' % _e(a["hint"]))
                o.append("</div>\n")
            o.append("</div>\n</article>\n")
            if g["gate"] and idx == 3:
                o.append('<p class="gate" role="note">%s</p>\n' % _e(g["gate"]))
        o.append("</section>\n")

    o.append('<section class="end" aria-label="End of sheet">\n')
    o.append('<p class="line"><span>%s</span> <span class="fill short" aria-hidden="true"></span></p>\n' % _e(STOP_LABEL))
    if m["least_sure"]:
        o.append('<p class="line"><span>%s</span> <span class="fill" aria-hidden="true"></span></p>\n'
                 % _e(LEAST_SURE_LABEL))
    if m["close_line"]:
        o.append('<p class="close-line"><strong>%s</strong></p>\n' % _e(m["close_line"]))
    o.append("</section>\n</main>")

    title = m["title"] + (" · " + m["date_line"] if m["date"] else "")
    return Template(template_text("html")).substitute(lang=_e(_lang(lang)), title=_e(title), body="".join(o))


# ---- typst ------------------------------------------------------------------

def ts(text):
    """A typst string literal: nothing inside it is read as markup."""
    s = _s(text).replace("\t", " ")
    s = "".join(ch for ch in s if ch == "\n" or ord(ch) >= 32)
    s = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return '"' + s + '"'


def _tl(text):
    """Markup for one plain line: an embedded string literal followed by a space."""
    return "#" + ts(text) + " "


def _typ_line(line):
    parts = []
    for is_code, t in split_code_spans(line):
        parts.append(("#raw(%s)" % ts(t)) if is_code else ("#" + ts(t)))
    return "".join(parts)


def _typ_paras(paras):
    out = []
    for blk in paras:
        if isinstance(blk, dict) and blk.get("kind") == "code":
            lang = (", lang: %s" % ts(blk["lang"])) if blk.get("lang") else ""
            out.append("#raw(block: true%s, %s)\n\n" % (lang, ts(blk["text"])))
            continue
        lines = blk["lines"] if isinstance(blk, dict) else blk
        out.append(" #linebreak() ".join(_typ_line(ln) for ln in lines) + "\n\n")
    return "".join(out)


def render_typst(spec, date=None, tools=None, lang="en", profile=None):
    m = build_model(spec, date=date, tools=tools, fmt="pdf", profile=profile)
    o = []
    o.append("#grid(columns: (1fr, auto), column-gutter: 12pt, align: (left + bottom, right + bottom),\n")
    o.append("  [#heading(level: 1)[%s]],\n" % _tl(m["title"]).strip())
    o.append("  [#text(size: 11pt)[%s]],\n)\n" % _tl(m["date_line"]).strip())
    o.append("#text(size: 10.5pt)[%s]\n\n" % _tl(m["meta"]).strip())

    o.append("#boxed[\n  #strong[Rules]\n  #list(\n")
    for r in m["rules"]:
        o.append("    [%s],\n" % _tl(r).strip())
    o.append("  )\n]\n\n")

    o.append("#v(4pt)\n#strong[#\"0.\"] %s #fillin(40mm)\n\n" % _tl(START_LABEL).strip())

    th = m["theory"]
    if th:
        if th["floor"]:
            o.append("#boxed[\n  #strong[Before this sheet]\n  #list(\n")
            o.extend("    [%s],\n" % _tl(f).strip() for f in th["floor"])
            o.append("  )\n]\n\n")
        if th["pages"]:
            o.append("#boxed[#strong[Read:] %s]\n\n" % _tl(th["pages"]).strip())
        if th["words"]:
            o.append("#heading(level: 2)[Words on this sheet]\n\n")
            for w in th["words"]:
                gloss = " #emph[(%s)]" % _tl(w["gloss"]).strip() if w["gloss"] else ""
                o.append("#strong[%s]%s: %s\n\n" % (_tl(w["term"]).strip(), gloss, _tl(w["def"]).strip()))
        for sec in th["sections"]:
            title = sec["title"] or {"rule": "The rule", "warning": "Warning", "worked": "Worked case",
                                     "contrast": "Contrast", "both_hold": "When both hold",
                                     "where": "Where this lives"}.get(sec["kind"], "Notes")
            body = _typ_paras(sec["paras"])
            if sec["kind"] in ("rule", "warning"):
                o.append("#boxed[\n#strong[%s]\n\n%s]\n\n" % (_tl(title).strip(), body))
            else:
                o.append("#heading(level: 2)[%s]\n\n%s" % (_tl(title).strip(), body))

    for g in m["groups"]:
        if g["title"]:
            o.append("#heading(level: 2)[%s]\n\n" % _tl(g["title"]).strip())
        for idx, it in enumerate(g["items"], start=1):
            if it["keep"]:
                o.append("#block(width: 100%, breakable: false)[\n")
            o.append("#block(width: 100%, above: 14pt, below: 4pt)[\n")
            o.append("#strong[%s] " % _tl(it["n"] + ".").strip())
            o.append(_typ_paras(it["paras"]) or "\n")
            o.append("]\n")
            for a in it["asks"]:
                o.append("#block(width: 100%, breakable: false, above: 6pt, below: 10pt)[\n")
                o.append("#strong[%s] %s\n\n" % (_tl(a["id"]).strip(), _typ_line(a["label"])))
                if a["box_mm"]:
                    o.append("#answer(%dmm)\n\n" % a["box_mm"])
                if a["check"]:
                    o.append("#checkline()\n\n")
                    if a["hint"]:
                        o.append("#hint[%s]\n" % _tl(a["hint"]).strip())
                o.append("]\n")
            if it["keep"]:
                o.append("]\n")
            if g["gate"] and idx == 3:
                o.append("#shaded[#strong[%s]]\n\n" % _tl(g["gate"]).strip())

    o.append("#v(10pt)\n#line(length: 100%, stroke: 0.5pt + luma(150))\n\n")
    o.append("%s #fillin(40mm)\n\n" % _tl(STOP_LABEL).strip())
    if m["least_sure"]:
        o.append("%s #fillin(1fr)\n\n" % _tl(LEAST_SURE_LABEL).strip())
    if m["close_line"]:
        o.append("#v(8pt)\n#align(center)[#strong[%s]]\n" % _tl(m["close_line"]).strip())

    return Template(template_text("typst")).substitute(
        title_str=ts(m["title"]), lang=_lang(lang), body="".join(o))


# ---- Markdown ---------------------------------------------------------------

def _md_escape(text):
    """Keep learner text literal in Markdown (no emphasis, headings or links)."""
    s = _s(text)
    s = re.sub(r"([\\`*_{}\[\]<>#|$~])", r"\\\1", s)
    s = re.sub(r"^(\s*)([-+])(\s)", r"\1\\\2\3", s)
    s = re.sub(r"^(\s*\d+)\.(\s)", r"\1\\.\2", s)
    return s


def _md_line(line):
    out = []
    for is_code, t in split_code_spans(line):
        if is_code:
            ticks = "`" * (max([len(r) for r in re.findall(r"`+", t)] or [0]) + 1)
            pad = " " if t.startswith("`") or t.endswith("`") else ""
            out.append("%s%s%s%s%s" % (ticks, pad, t, pad, ticks))
        else:
            out.append(_md_escape(t))
    return "".join(out)


def _md_paras(paras):
    out = []
    for blk in paras:
        if isinstance(blk, dict) and blk.get("kind") == "code":
            fence = "`" * max(3, max([len(r) for r in re.findall(r"`+", blk["text"])] or [0]) + 1)
            out.append("%s%s\n%s\n%s\n\n" % (fence, blk.get("lang") or "", blk["text"], fence))
            continue
        lines = blk["lines"] if isinstance(blk, dict) else blk
        out.append("  \n".join(_md_line(ln) for ln in lines) + "\n\n")
    return "".join(out)


def render_markdown(spec, date=None, tools=None, lang="en", profile=None):
    m = build_model(spec, date=date, tools=tools, fmt="md", profile=profile)
    o = []
    o.append("**0.** %s ____\n\n" % START_LABEL)
    th = m["theory"]
    if th:
        if th["floor"]:
            o.append("## Before this sheet\n\n")
            o.extend("- %s\n" % _md_escape(f) for f in th["floor"])
            o.append("\n")
        if th["pages"]:
            o.append("**Read:** %s\n\n" % _md_escape(th["pages"]))
        if th["words"]:
            o.append("## Words on this sheet\n\n")
            for w in th["words"]:
                gloss = " *(%s)*" % _md_escape(w["gloss"]) if w["gloss"] else ""
                o.append("- **%s**%s: %s\n" % (_md_escape(w["term"]), gloss, _md_escape(w["def"])))
            o.append("\n")
        for sec in th["sections"]:
            title = sec["title"] or sec["kind"].replace("_", " ").capitalize()
            if sec["kind"] in ("rule", "warning"):
                o.append("> **%s**\n>\n" % _md_escape(title))
                for blk in sec["paras"]:
                    if blk.get("kind") == "code":
                        body = _md_paras([blk]).rstrip("\n")
                        o.append("".join("> " + ln + "\n" for ln in body.split("\n")) + ">\n")
                        continue
                    o.append(">" + "  \n>".join(" " + _md_line(ln) for ln in blk["lines"]) + "\n>\n")
                o.append("\n")
            else:
                o.append("## %s\n\n%s" % (_md_escape(title), _md_paras(sec["paras"])))

    for g in m["groups"]:
        if g["title"]:
            o.append("## %s\n\n" % _md_escape(g["title"]))
        for idx, it in enumerate(g["items"], start=1):
            o.append("**%s.** " % _md_escape(it["n"]))
            body = _md_paras(it["paras"])
            o.append(body if body else "\n\n")
            for a in it["asks"]:
                if a["box_mm"]:
                    o.append("- **%s** %s  \n  Answer: ______________________  \n"
                             % (_md_escape(a["id"]), _md_line(a["label"])))
                else:
                    o.append("- **%s** %s  \n" % (_md_escape(a["id"]), _md_line(a["label"])))
                if a["check"]:
                    hint = " *(%s)*" % _md_escape(a["hint"]) if a["hint"] else ""
                    o.append("  %s ______________________%s\n" % (CHECK_LABEL, hint))
            o.append("\n")
            if g["gate"] and idx == 3:
                o.append("> **%s**\n\n" % _md_escape(g["gate"]))
    o.append("---\n\n%s ____\n\n" % STOP_LABEL)
    if m["least_sure"]:
        o.append("%s ____\n\n" % LEAST_SURE_LABEL)
    if m["close_line"]:
        o.append("**%s**\n" % m["close_line"])

    rules_md = "".join("> - %s\n" % _md_escape(r) for r in m["rules"])
    return Template(template_text("md")).substitute(
        title=_md_escape(m["title"]), date_line=m["date_line"], meta=_md_escape(m["meta"]),
        rules=rules_md.rstrip("\n"), body="".join(o).rstrip("\n"))


# ==========================================================================
# PDF backends
# ==========================================================================

def find_typst():
    return shutil.which("typst")


def find_browsers():
    """Chrome, Chromium or Edge executables, most likely first."""
    if os.environ.get("INDELIBLE_NO_BROWSER"):
        return []
    names = []
    home = Path(os.path.expanduser("~"))
    if sys.platform == "darwin":
        for app, exe in (("Google Chrome", "Google Chrome"), ("Chromium", "Chromium"),
                         ("Microsoft Edge", "Microsoft Edge"), ("Google Chrome Canary", "Google Chrome Canary")):
            for base in (Path("/Applications"), home / "Applications"):
                names.append(str(base / (app + ".app") / "Contents" / "MacOS" / exe))
    if os.name == "nt":
        for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base:
                names.append(str(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"))
                names.append(str(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"))
                names.append(str(Path(base) / "Chromium" / "Application" / "chrome.exe"))
    for exe in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                "microsoft-edge", "microsoft-edge-stable", "msedge", "chrome"):
        found = shutil.which(exe)
        if found:
            names.append(found)
    out = []
    for n in names:
        if n not in out and Path(n).is_file():
            out.append(n)
    return out


def find_chrome():
    found = find_browsers()
    return found[0] if found else None


def pdf_complete(pdf):
    try:
        with open(str(pdf), "rb") as fh:
            head = fh.read(5)
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 2048))
            tail = fh.read()
        return head.startswith(b"%PDF") and b"%%EOF" in tail
    except OSError:
        return False


def _stop(proc):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                pass


def _run_until_pdf(cmd, pdf, timeout):
    """Run a headless browser until the PDF is complete, then stop it.

    Some Chrome builds write the PDF and then keep running, so waiting for the
    process to exit is not enough.
    """
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                stdin=subprocess.DEVNULL)
    except OSError:
        return False
    deadline = time.time() + timeout
    ok = False
    last_size = -1
    try:
        while time.time() < deadline:
            if pdf.exists() and pdf_complete(pdf):
                size = pdf.stat().st_size
                if size == last_size:  # stable across two polls: fully written
                    ok = True
                    break
                last_size = size
            elif proc.poll() is not None:
                ok = pdf.exists() and pdf_complete(pdf)
                break
            time.sleep(0.2)
    finally:
        _stop(proc)
    return ok


def compile_typst(src, pdf, exe=None, timeout=RENDER_TIMEOUT_S):
    """``typst compile src pdf`` into a temp file, then moved into place. Returns (ok, detail)."""
    exe = exe or find_typst()
    if not exe:
        return False, "typst not found"
    src, pdf = Path(src), Path(pdf)
    tmp = pdf.with_name("." + pdf.stem + ".tmp.pdf")
    try:
        r = subprocess.run([exe, "compile", str(src), str(tmp)], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        _unlink(tmp)
        return False, "typst compile timed out"
    except (OSError, subprocess.SubprocessError) as exc:
        _unlink(tmp)
        return False, "typst compile failed (%s)" % type(exc).__name__
    if r.returncode != 0 or not pdf_complete(tmp):
        _unlink(tmp)
        msg = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        return False, "typst compile failed" + (": " + msg[0][:160] if msg else "")
    os.replace(str(tmp), str(pdf))
    return True, "compiled with typst"


def print_html_to_pdf(html_path, pdf, exe=None, timeout=RENDER_TIMEOUT_S):
    """Chrome/Chromium/Edge headless ``--print-to-pdf``. Returns (ok, detail)."""
    exe = exe or find_chrome()
    if not exe:
        return False, "no Chrome, Chromium or Edge found"
    html_path, pdf = Path(html_path), Path(pdf)
    profile = tempfile.mkdtemp(prefix="indelible-chrome-")
    tmp = pdf.with_name("." + pdf.stem + ".tmp.pdf")
    _unlink(tmp)
    try:
        # --use-mock-keychain / --password-store=basic: never touch the OS keychain
        # (on macOS a headless print otherwise can raise keychain dialogs).
        cmd = [exe, "--headless", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
               "--use-mock-keychain", "--password-store=basic",
               "--disable-extensions", "--user-data-dir=" + profile,
               "--no-pdf-header-footer", "--print-to-pdf-no-header",
               "--print-to-pdf=" + str(tmp), html_path.resolve().as_uri()]
        if sys.platform.startswith("linux") and hasattr(os, "geteuid") and os.geteuid() == 0:
            cmd.insert(1, "--no-sandbox")  # Chromium refuses to run as root without it (containers, CI)
        ok = _run_until_pdf(cmd, tmp, timeout)
        if not ok:
            _unlink(tmp)
            return False, "browser print to PDF failed"
        os.replace(str(tmp), str(pdf))
        return True, "printed with %s" % Path(exe).name
    except (OSError, subprocess.SubprocessError) as exc:
        _unlink(tmp)
        return False, "browser print failed (%s)" % type(exc).__name__
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def _unlink(path):
    try:
        Path(path).unlink()
    except OSError:
        pass


# ==========================================================================
# Backend detection (doctor) and the build chain
# ==========================================================================

SAMPLE_SPEC = {
    "v": 1, "id": "doctor-test", "type": "drills", "subject": "test", "title": "Test sheet",
    "est_min": 1, "tools": "none",
    "items": [{"n": 1, "topic": "T01", "layer": "verbal", "op": "test",
               "text": "Ação · Ñandú · Γειά σου · x² ≤ 3 → √9 = 3",
               "asks": [{"id": "1a", "label": "Answer:", "check": True, "check_hint": "Put it back in."}]}],
    "blocks": [{"title": "Block A", "items": [1]}],
    "terms": [], "theory": None, "least_sure": True,
}


def _test_backend(name, exe):
    tmp = Path(tempfile.mkdtemp(prefix="indelible-render-test-"))
    try:
        if name == "typst":
            src = tmp / "test.typ"
            fio.write_text(src, render_typst(SAMPLE_SPEC), backup=False)
            ok, detail = compile_typst(src, tmp / "test.pdf", exe=exe)
            return ok, "test compile passed" if ok else detail
        src = tmp / "test.html"
        fio.write_text(src, render_html(SAMPLE_SPEC), backup=False)
        ok, detail = print_html_to_pdf(src, tmp / "test.pdf", exe=exe)
        return ok, "test print passed" if ok else detail
    except Exception as exc:  # a broken renderer must never break doctor
        return False, "test failed (%s)" % type(exc).__name__
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)


def detect_backends(quick=False):
    """One row per renderer, in chain order, each ``{"name","found","ok","detail","path"}``.

    ``ok`` comes from a real test compile of the shipped template (typst) or a
    real test print of the shipped HTML template (Chrome/Chromium/Edge). With
    ``quick`` the programs are only looked up. LaTeX engines are reported but
    never ``ok`` in v0.1. ``html`` and ``md`` always work.
    """
    rows = []
    typst = find_typst()
    if typst:
        ok, detail = (True, "found (not test-compiled)") if quick else _test_backend("typst", typst)
        rows.append({"name": "typst", "found": True, "ok": ok, "detail": detail, "path": typst})
    else:
        rows.append({"name": "typst", "found": False, "ok": False, "detail": "not found", "path": None})
    for eng in LATEX_ENGINES:
        path = shutil.which(eng)
        rows.append({"name": eng, "found": bool(path), "ok": False,
                     "detail": "found; LaTeX sheets arrive in v0.2" if path else "not found", "path": path})
    chrome = find_chrome()
    if chrome:
        ok, detail = (True, "found (not test-printed)") if quick else _test_backend("chrome", chrome)
        rows.append({"name": "chrome", "found": True, "ok": ok, "detail": detail, "path": chrome})
    else:
        rows.append({"name": "chrome", "found": False, "ok": False,
                     "detail": "no Chrome, Chromium or Edge found", "path": None})
    rows.append({"name": "html", "found": True, "ok": True,
                 "detail": "always available (open it in a browser and print)", "path": None})
    rows.append({"name": "md", "found": True, "ok": True, "detail": "always available (on screen)", "path": None})
    return rows


def working_backends(quick=False):
    """Names of the backends that work here, in chain order."""
    return [r["name"] for r in detect_backends(quick=quick) if r.get("ok") and r["name"] in BACKENDS]


def backend_order(fmt=None, preferred=None):
    """The backends to try, in order, for a requested format."""
    if fmt == "md":
        return ["md"]
    if fmt == "html":
        return ["html"]
    chain = list(BACKENDS)
    if fmt == "pdf":
        return chain
    if preferred in BACKENDS:
        chain.remove(preferred)
        chain.insert(0, preferred)
    return chain


def render_sheet(spec, out_dir, base, fmt=None, preferred=None, date=None, tools=None, lang="en", profile=None):
    """Render through the chain. Returns ``{"backend", "files", "notes"}``.

    ``files`` lists the printable output first, then its kept source
    (``.typ`` or ``.html``) when the output is a PDF.
    """
    if fmt not in (None,) + FORMATS:
        from lib import UsageError
        raise UsageError("--format must be pdf, html or md")
    out_dir = Path(out_dir)
    fio.ensure_dir(out_dir)
    notes = []
    kw = {"date": date, "tools": tools, "lang": lang, "profile": profile}
    for b in backend_order(fmt, preferred):
        if b == "typst":
            exe = find_typst()
            if not exe:
                notes.append("typst not found")
                continue
            src, pdf = out_dir / (base + ".typ"), out_dir / (base + ".pdf")
            fio.write_text(src, render_typst(spec, **kw), backup=False)
            ok, detail = compile_typst(src, pdf, exe=exe)
            if ok:
                return {"backend": "typst", "files": [pdf, src], "notes": notes}
            _unlink(src)
            notes.append(detail)
        elif b == "chrome":
            exe = find_chrome()
            if not exe:
                notes.append("no Chrome, Chromium or Edge found")
                continue
            src, pdf = out_dir / (base + ".html"), out_dir / (base + ".pdf")
            fio.write_text(src, render_html(spec, **kw), backup=False)
            ok, detail = print_html_to_pdf(src, pdf, exe=exe)
            if ok:
                return {"backend": "chrome", "files": [pdf, src], "notes": notes}
            notes.append(detail)
        elif b == "html":
            out = out_dir / (base + ".html")
            fio.write_text(out, render_html(spec, **kw), backup=False)
            return {"backend": "html", "files": [out], "notes": notes}
        elif b == "md":
            out = out_dir / (base + ".md")
            fio.write_text(out, render_markdown(spec, **kw), backup=False)
            return {"backend": "md", "files": [out], "notes": notes}
    from lib import CheckFailed
    raise CheckFailed("No renderer worked: " + "; ".join(notes))
