"""The sheet checker: rules L1-L14 and warnings W1-W6 (CONTRACT section 7.4).

``check(spec, ctx)`` is pure: it takes the visible spec and a context dict and
returns one result per rule, in order. ``gather(ws, subject, spec, row)``
builds that context from the workspace (topics, sense words, the glossary,
budget, pace, exposures, errors, the words and operations the subject's other
sheets show, the sealed key, and the time the sheet will be sat). ``run(...)``
does both.

When the sheet is linked to a block (``sheet new/lint --block``, or the
sheet row's block), L5 uses that block's minutes (the open session's work
minutes, when it runs on that block), less the sheets already issued on it, and L7 judges cold and mixed items at the block's start while
the block is still ahead: the time the sheet will be sat, not build time
(``--at`` names another time). The builder links every sheet to its block, so
a mixed sheet built at the close is judged at the next block. ``sheet issue``
checks both again, since the learner may meet a topic in between. L5 also
recomputes the builder's own estimate from the subject's ``pace_s``
(``pace_floor``) and fails a lower ``est_min``, since the estimate is written
by the party whose sizing it checks. Official questions (``official:``) are
left out of it: the exam's clock times them. W5 adds the reading
a theory, example or repair sheet asks for (``reading_words``, at a fast 150
words a minute), which the pace floor leaves out. A measurement
(diagnostic, mock, checkpoint) is exempt from the session's question budget,
not from its own minutes: its block's minutes less the 10 kept for recording
(``budget_for``).

L4 terms: code (inline `spans` and fenced blocks) is scanned only for the
subject's own ``lexicon`` and ``sense_list`` entries (``len``, ``.append``,
``λ``), never for the seed list, whose words are often identifiers; check hints
and theory section bodies are scanned for all of them. Resolutions:
``defined_here`` (the word is in ``theory.words`` on this sheet),
``defined_on:<sheet-id>`` (a sheet of this subject, not void, that defines the
word; ``sheet issue`` waits until that sheet is issued), ``glossary`` (the
word is in data/glossary.jsonl: ``glossary add``), ``everyday`` (used in its
plain everyday sense; never for a word in the subject lexicon or one the sheet
defines, and on a theory, example or repair sheet never for one it teaches: in
the title, a section title, the topic's name or a question, or used 3 times or
more), and ``measured_here`` (a measuring sheet that deliberately tests the
word).

L10 and W3 read check hints only. A hint is how the learner checks an answer,
so it must name a check that runs: never a search for their own mistake, a
re-solve or a confidence rating (L10, any sheet), and on a topic the learner
doesn't own yet (below mastery 3p) never "another way" or "the weakest step",
which need a second method or a sense of their own weak spots (W3). W4 asks
that a theory or repair sheet's worked case ends with a step labelled
"Check:", so the check a drill asks for has been seen worked. L10 and W3 match
English wording only; the rules themselves hold in any language.

L11 asks a theory or repair sheet for a worked section, before any rule
section; a locked override of R12 order (``overrides[]`` in subject.json)
lifts the order, never the worked section. A ``prequestion`` section (a guess
before reading) goes only on a theory sheet, before its first worked section. L12 asks that every new item on a drills sheet uses an operation a
theory, external, example or repair sheet of its topic has shown: a pencil
question with that ``op``, or a worked section listing it in ``ops``. The theory
and its drills come from two builder runs, so this is what ties them.

L13 asks a theory sheet on a procedural, conceptual or code topic for a
``meaning`` section ("What it is and why"): what the object is, and why the
rule follows from it. A procedure taught without it fades before its 2-day
recheck. W6 asks the same, as a warning, on other topics (a language or
reading convention may say in one line that it is learned as given), and
keeps the box short and before the rule.

L14 keeps scaffolds (an item's printed working lines or empty table) on
practice sheets: a measuring or mixed sheet is question, box and check line
only. On drills, a block's last two items print only the box, so the block
shows whether the working now happens unprompted.

The key is read in-process for L8 only. Nothing from it is ever returned or
printed: an L8 FAIL names the question (ask) ids, never the text.

Result rows: ``{"rule": "L4", "status": "PASS"|"FAIL"|"WARN", "title": "terms", "detail": "..."}``.
"""

import math
import re
import unicodedata

from lib import LISTS_DIR, dates, learning
from lib import io as fio
from lib import render

RULES = ["L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9", "L10", "L11", "L12", "L13", "L14",
         "W1", "W2", "W3", "W4", "W5", "W6"]
TITLES = {
    "L1": "structure", "L2": "check lines", "L3": "unlabelled", "L4": "terms", "L5": "budget",
    "L6": "drill blocks", "L7": "cold validity", "L8": "key leak", "L9": "least-sure",
    "L10": "check hints", "L11": "worked case first", "L12": "taught operations", "L13": "meaning box",
    "L14": "scaffolds",
    "W1": "formula in block title", "W2": "sentences after their numbers",
    "W3": "checks on new topics", "W4": "worked check", "W5": "reading time", "W6": "meaning box",
}

# L2: every ask has a check line on these types. Repair is exempt (CONTRACT
# 7.4): sheets.md and builder.md make check lines optional on repair pencils,
# which are done with the fix in view.
CHECK_REQUIRED = ("drills", "cold", "mixed", "diagnostic", "mock", "checkpoint", "review")
# ... except where the sheet copies the exam, which has no check column: a whole mock,
# and an official question (origin official:) on a diagnostic or checkpoint. A check
# written per answer would take the exam's own clock and measure another task.
EXAM_CONDITIONS = ("mock",)
OFFICIAL_EXEMPT_TYPES = ("diagnostic", "checkpoint")
UNLABELLED_TYPES = ("cold", "diagnostic", "mock", "checkpoint", "probe", "mixed")
BUDGET_EXEMPT = ("diagnostic", "mock", "checkpoint")
FLOOR_EXEMPT = ("triage",)
MEASURING = ("cold", "diagnostic", "mock", "checkpoint", "probe", "words")
RESOLUTIONS = ("defined_here", "defined_on:<sheet-id>", "glossary", "everyday", "measured_here")
# L4: on these sheets a word the sheet teaches is never "everyday" (see _taught).
TEACHING_TYPES = ("theory", "example", "repair")
TAUGHT_USES = 3
LEAST_SURE_EXEMPT = ("theory", "external", "example", "triage")
# L7: the types whose timing is checked: a 2-day recheck in its window, a words recheck
# (profiles.md: its cold:<topic> items close the booking), and the mixed sheets whose
# re-served mistakes move the ladder at grading. A late-recheck probe (plan.md
# section 7) is sat outside its window on purpose, so it is not checked here.
RECHECK_TYPES = ("cold", "mixed", "words")
VERBAL_LAYERS = ("verbal", "reading")
MIN_LEAK_LEN = 3
BUDGET_FRACTION = 0.8
RECORD_MIN = 10     # a measurement block holds the exam clock plus 10–15 minutes to record (measure.md §4)
HANDED_OVER = ("issued", "sat", "graded")   # the sheets on a block that take its minutes
# W5: the sheets read in full before their pencils, and the reading pace it allows. builder.md budgets
# 120 words a minute (90 in a second language); 150 is a fast reader, so W5 warns only when even
# that reader could not finish.
READING_TYPES = ("theory", "example", "repair")
READING_WPM = 150
MAX_LISTED = 6

# L10: a hint that sends the learner to search for their own mistake, re-solve
# the question or rate their confidence, instead of naming a check that runs.
# "Error" is often a subject word (the standard error, an error term, error bars,
# an error message), so it counts as a search only when the phrase ends there or
# points at the learner's own work. English wording only; the rule holds in any
# language, and the builder re-reads other languages itself.
_SEARCH = r"(?:find|spot|look\s+for|search\s+for|hunt\s+for|locate)"
_WHOSE = r"(?:(?:the|a|an|any|your|my)\s+)?(?:own\s+)?"
_OWN = (r"(?:(?:your|my|the|this|each|every)\s+)?(?:own\s+)?"
        r"(?:work|working|solutions?|answers?|steps?|calculations?|method|proof|code|lines?)")
_ERR_END = r"(?:\s+(?:in|on)\s+" + _OWN + r"\b|(?=\s*(?:[.?!;]|$)))"
_SCAN = r"(?:check|look\s+(?:over|through|at)|go\s+(?:over|through)|read\s+through|scan|search)"
_SEARCH_HINT = re.compile(
    r"\b" + _SEARCH + r"\s+" + _WHOSE + r"(?:mistakes?|slips?)\b"
    r"|\b" + _SEARCH + r"\s+(?:your|my)\s+(?:own\s+)?errors?\b"
    r"|\b" + _SEARCH + r"\s+" + _WHOSE + r"errors?" + _ERR_END +
    r"|\b" + _SCAN + r"\s+(?:it\s+|" + _OWN + r"\s+)?for\s+(?:any\s+)?(?:mistakes?|slips?)\b"
    r"|\b" + _SCAN + r"\s+(?:it\s+|" + _OWN + r"\s+)?for\s+(?:any\s+)?errors?" + _ERR_END +
    r"|\b(?:find|spot|see)\s+what(?:'s|\u2019s|\s+is|\s+went)\s+wrong\b"
    r"|\bwhere\s+(?:did\s+|does\s+)?(?:you|it|i)\s+(?:went|go|goes)\s+wrong\b"
    r"|\b(?:which|what)\s+(?:step|line|part)\s+is\s+wrong\b"
    r"|\bis\s+there\s+(?:a|an|any)\s+(?:mistakes?|slips?)\b"
    r"|\bis\s+there\s+(?:a|an|any)\s+errors?" + _ERR_END +
    r"|\b(?:did|have)\s+you\s+(?:make|made)\s+(?:a|an|any)\s+(?:mistakes?|errors?|slips?)\b"
    r"|\b(?:didn't|didn\u2019t|did\s+not)\s+make\s+(?:a|an|any)\s+(?:mistakes?|errors?|slips?)\b"
    r"|\bmake\s+sure\s+(?:it|it's|it\u2019s|it\s+is|your\s+answer\s+is|you're|you\s+are)\s+(?:right|correct)\b"
    r"|\bdouble[\s-]*check"
    r"|\bre-?do\b|\bre-solve\b|\brework\b"
    r"|\b(?:solve|do|work|try)\s+(?:(?:it|this|that|them|the\s+(?:question|problem|sum))\s+)?"
    r"(?:out\s+|through\s+)?again\b"
    r"|\bare\s+you\s+sure\b|\bhow\s+(?:sure|confident)\s+are\s+you\b"
    r"|\b(?:rate|mark)\s+your\s+(?:confidence|certainty)\b",
    re.IGNORECASE)
# L10: a hint that is only "check your answer", with nothing that says how.
_BARE_HINT = re.compile(
    r"^(?:please\s+)?(?:check|re-?check|verify|review|look\s+over|go\s+over)"
    r"(?:\s+(?:your|the|it|this|each|every))?"
    r"(?:\s+(?:final\s+)?(?:answers?|work|working|solutions?|calculations?|steps?|results?|everything))?"
    r"(?:\s+(?:again|carefully|once\s+more))?$",
    re.IGNORECASE)
# W3: a hint that needs a second method or a sense of one's own weak spots.
# Narrow: "the weakest acid" or "a cart pushed on a track" are subject words.
_SECOND_WAY_HINT = re.compile(
    r"\b(?:another|a\s+different|a\s+second)\s+(?:way|method|route|approach)\b"
    r"|\bweakest\s+(?:step|point|part|spot|line)\b"
    r"|\b(?:step|part|point|line)\s+(?:is|was)\s+(?:the\s+)?weakest\b"
    r"|\bbe\s+pushed\s+on\b|\bleast\s+sure\b",
    re.IGNORECASE)
_CHECK_STEP = re.compile(r"\bcheck\s*:", re.IGNORECASE)
CHECKABLE_TYPES = CHECK_REQUIRED + ("repair",)
WORKED_CHECK_TYPES = ("theory", "repair")
# L11: a locked override of these rules (method.md: R12 order, concrete first; R12 before it was
# split) lets the rule come before the worked case. The worked case itself is never waived.
ORDER_RULES = ("r12 order", "r12")
# L12: the sheets that show an operation before the drills ask for it (pencil questions' op,
# and a worked section's ops).
SHOWING_TYPES = ("theory", "external", "example", "repair")
# L13: the layers whose theory must say what the object is and why the rule follows (a procedure
# learned without its meaning fades); W6 asks for it on the others. The box is about 5 lines.
MEANING_LAYERS = ("procedural", "conceptual", "code")
MEANING_MAX_WORDS = 80
# L14: a scaffold is worked structure, which a measuring or mixed sheet never carries (builder rule 6);
# on drills it fades before the block ends.
SCAFFOLD_REFUSED = MEASURING + ("mixed",)
SCAFFOLD_FADED = 2

_CODE_SPAN = re.compile(r"(`+)(?!`)(.+?)(?<!`)\1(?!`)")
_FENCE_OPEN = re.compile(r"^[ \t]*(`{3,}|~{3,})")
_ROMAN = re.compile(r"^(?=[ivxlcdm])m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$")
_CHOICE_LINE = re.compile(r"^\s*(?:\(\s*([A-Za-z]{1,7})\s*\)|([A-Za-z]{1,7})\s*[.)])\s+\S")


# ==========================================================================
# Helpers
# ==========================================================================

def _s(v):
    return "" if v is None else str(v)


def _items(spec):
    return [it for it in (spec.get("items") or []) if isinstance(it, dict)]


def _asks(item):
    return [a for a in (item.get("asks") or []) if isinstance(a, dict)]


def _listed(values, n=MAX_LISTED):
    values = [_s(v) for v in values]
    if len(values) <= n:
        return ", ".join(values)
    return ", ".join(values[:n]) + " (+%d more)" % (len(values) - n)


def _num(x):
    return render._num(x)


def phrase_pattern(phrase):
    """Whole-word, case-insensitive pattern for a word or phrase (any run of spaces between words)."""
    words = _s(phrase).strip().split()
    if not words:
        return None
    body = r"\s+".join(re.escape(w) for w in words)
    pre = r"(?<!\w)" if re.match(r"\w", words[0][0]) else ""
    post = r"(?!\w)" if re.match(r"\w", words[-1][-1]) else ""
    return re.compile(pre + body + post, re.IGNORECASE)


def contains_phrase(text, phrase):
    pat = phrase_pattern(phrase)
    return bool(pat and pat.search(_s(text)))


def _norm(text):
    text = unicodedata.normalize("NFC", _s(text)).casefold()
    return re.sub(r"\s+", " ", text).strip()


def strip_code(text):
    """Text with fenced code blocks and inline code spans blanked out. Code is checked
    separately, for the subject's own words only (``code_parts``)."""
    out, fence = [], None
    for line in _s(text).split("\n"):
        m = _FENCE_OPEN.match(line)
        if fence is None:
            if m:
                fence = m.group(1)[0] * len(m.group(1))
                out.append("")
                continue
            out.append(_CODE_SPAN.sub(" ", line))
        else:
            if m and m.group(1).startswith(fence) and not line.strip()[len(m.group(1)):].strip():
                fence = None
            out.append("")
    return "\n".join(out)


def code_parts(text):
    """Only the code in a text: the lines of fenced blocks and the insides of inline spans
    (what ``strip_code`` blanks out)."""
    out, fence = [], None
    for line in _s(text).split("\n"):
        m = _FENCE_OPEN.match(line)
        if fence is None:
            if m:
                fence = m.group(1)[0] * len(m.group(1))
                continue
            out += [s.group(2) for s in _CODE_SPAN.finditer(line)]
        else:
            if m and m.group(1).startswith(fence) and not line.strip()[len(m.group(1)):].strip():
                fence = None
                continue
            out.append(line)
    return "\n".join(out)


def choice_labels(texts):
    """Option labels printed at the start of a line: 'iii. ...', '(iv) ...', 'B) ...' (lowercase)."""
    found = set()
    for text in texts:
        for line in _s(text).split("\n"):
            m = _CHOICE_LINE.match(line)
            if not m:
                continue
            label = (m.group(1) or m.group(2) or "").lower()
            if len(label) == 1 or _ROMAN.match(label):
                found.add(label)
    return found


def _bare(value):
    return _norm(value).strip(" .()[]:")


def is_verbal(item):
    op = _s(item.get("op")).lower()
    return (item.get("layer") in VERBAL_LAYERS or _s(item.get("form")).lower() == "sentence"
            or "sentence" in op or "verbal" in op)


# ==========================================================================
# Sense words (L4)
# ==========================================================================

_SEED = []


def load_sense_seed():
    """Entries of assets/lists/sense_seed.txt (lowercase; comments skipped)."""
    if not _SEED:
        text = fio.read_text(LISTS_DIR / "sense_seed.txt") or ""
        for line in text.split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                _SEED.append(" ".join(line.lower().split()))
    return list(_SEED)


def _lexicon_terms(values):
    out = []
    for v in values or []:
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            for k in ("term", "word", "name"):
                if isinstance(v.get(k), str):
                    out.append(v[k])
                    break
    return out


def sense_words(subject_cfg=None):
    """The seed list plus the subject's sense_list and lexicon, lowercase and de-duplicated."""
    cfg = subject_cfg or {}
    words = load_sense_seed() + _lexicon_terms(cfg.get("sense_list")) + _lexicon_terms(cfg.get("lexicon"))
    out, seen = [], set()
    for w in words:
        w = " ".join(_s(w).lower().split())
        if w and w not in seen:
            seen.add(w)
            out.append(w)
    return out


# ==========================================================================
# The rules
# ==========================================================================

def _l1(spec, ctx):
    items = spec.get("items")
    if not isinstance(items, list) or not items:
        return "FAIL", "the sheet has no items"
    probs, ns, ask_ids = [], set(), set()
    n_asks = 0
    for idx, it in enumerate(items, start=1):
        if not isinstance(it, dict):
            probs.append("item %d is not an object" % idx)
            continue
        n = it.get("n")
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            probs.append("item %d has no item number n" % idx)
        elif n in ns:
            probs.append("item number %d is used twice" % n)
        else:
            ns.add(n)
        asks = it.get("asks")
        if not isinstance(asks, list) or not asks:
            probs.append("item %s has no question" % _s(n or idx))
            continue
        for a in asks:
            if not isinstance(a, dict):
                probs.append("item %s has a question that is not an object" % _s(n or idx))
                continue
            n_asks += 1
            aid = a.get("id")
            if not isinstance(aid, str) or not aid.strip():
                probs.append("item %s has a question with no id" % _s(n or idx))
            elif aid in ask_ids:
                probs.append("question id %s is used twice" % aid)
            else:
                ask_ids.add(aid)
            if not _s(a.get("label")).strip():
                probs.append("question %s has no label" % _s(aid or "?"))
    if probs:
        return "FAIL", "; ".join(probs[:MAX_LISTED]) + (" (+%d more)" % (len(probs) - MAX_LISTED)
                                                         if len(probs) > MAX_LISTED else "")
    return "PASS", "%d items, %d questions" % (len(ns), n_asks)


def _l2(spec, ctx):
    t = spec.get("type")
    if t not in CHECK_REQUIRED:
        return "PASS", "not required on %s sheets" % t
    if t in EXAM_CONDITIONS:
        return "PASS", "not required on %s sheets (exam conditions)" % t
    missing, exam = [], 0
    for it in _items(spec):
        as_exam = t in OFFICIAL_EXEMPT_TYPES and _s(it.get("origin")).startswith("official:")
        for a in _asks(it):
            if as_exam:
                exam += 1
            elif a.get("check") is not True:
                missing.append(a.get("id"))
    if missing:
        return "FAIL", "no check line on question%s %s" % ("s" if len(missing) > 1 else "", _listed(missing))
    if exam:
        return "PASS", "every question Claude wrote has a check line; official questions need none (exam conditions)"
    return "PASS", "every question has a check line"


def _l3(spec, ctx):
    """CONTRACT 7.4 L3. The adjacency test applies only when the sheet has 2
    or more topics: a single-topic recheck cannot interleave, and one that
    also re-serves a mistake on that topic needs two items (a cold:<T> item
    and an error:<E> item), so without the exemption it could never pass."""
    t = spec.get("type")
    if t not in UNLABELLED_TYPES:
        return "PASS", "not a measuring sheet"
    topics = ctx.get("topics") or {}
    places = [("the title", spec.get("title"))]
    for i, b in enumerate(spec.get("blocks") or [], start=1):
        if isinstance(b, dict):
            places.append(("block title %d" % i, b.get("title")))
    for it in _items(spec):
        for a in _asks(it):
            places.append(("the label of %s" % _s(a.get("id")), a.get("label")))
    probs = []
    for where, text in places:
        if not _s(text).strip():
            continue
        for tid, name in topics.items():
            if contains_phrase(text, tid):
                probs.append("topic id %s in %s" % (tid, where))
            if name and contains_phrase(text, name):
                probs.append("topic name '%s' in %s" % (name, where))
    items = _items(spec)
    distinct = set(it.get("topic") for it in items if it.get("topic"))
    if len(distinct) >= 2:
        for a, b in zip(items, items[1:]):
            if a.get("topic") and a.get("topic") == b.get("topic"):
                probs.append("items %s and %s are next to each other on the same topic"
                             % (_s(a.get("n")), _s(b.get("n"))))
    if probs:
        return "FAIL", _listed(probs, 5)
    return "PASS", "no topic named; no two same-topic items together"


def _term_texts(spec):
    """The texts L4 scans: titles, item text, labels, check hints, theory section titles and
    bodies; code removed. A hint is printed under its question, so a word in it is read too."""
    return [strip_code(x) for x in _raw_term_texts(spec)]


def _code_texts(spec):
    """The code in the same texts, scanned only for the subject's own words."""
    return [c for c in (code_parts(x) for x in _raw_term_texts(spec)) if c.strip()]


def _raw_term_texts(spec):
    texts = [spec.get("title")]
    texts += [b.get("title") for b in spec.get("blocks") or [] if isinstance(b, dict)]
    for it in _items(spec):
        texts.append(it.get("text"))
        texts += render.scaffold_texts(it.get("scaffold"))
        texts += [a.get("label") for a in _asks(it)]
        texts += [a.get("check_hint") for a in _asks(it)]
    th = spec.get("theory")
    if isinstance(th, dict):
        for sec in th.get("sections") or []:
            if isinstance(sec, dict):
                texts += [sec.get("title"), sec.get("body")]
    return [_s(x) for x in texts if _s(x).strip()]


def _taught(w, spec, ctx, texts):
    """On a teaching sheet (theory, example, repair): is ``w`` a word the sheet teaches,
    so never ``everyday``? It is when it is in the title, a theory section title or
    the name of a topic on the sheet, in a pencil question's text or label, or used
    TAUGHT_USES times or more. One plain use in a box ("the difference is small") is not."""
    pat = phrase_pattern(w)
    if pat is None:
        return False
    th = spec.get("theory") if isinstance(spec.get("theory"), dict) else {}
    names = ctx.get("topics") or {}
    heads = [spec.get("title")] + [sec.get("title") for sec in th.get("sections") or [] if isinstance(sec, dict)]
    heads += [names.get(it.get("topic")) for it in _items(spec)]
    for it in _items(spec):
        heads.append(it.get("text"))
        heads += [a.get("label") for a in _asks(it)]
    if any(pat.search(strip_code(h)) for h in heads if _s(h).strip()):
        return True
    return sum(len(pat.findall(x)) for x in texts) >= TAUGHT_USES


def _res_ok(res):
    if res in ("defined_here", "glossary", "everyday", "measured_here"):
        return True
    return res.startswith("defined_on:") and bool(re.match(r"^[a-z0-9][a-z0-9-]{1,60}$", res[len("defined_on:"):]))


def _l4(spec, ctx):
    t = spec.get("type")
    texts = _term_texts(spec)
    used = []
    for w in ctx.get("sense") or []:
        pat = phrase_pattern(w)
        if pat and any(pat.search(x) for x in texts):
            used.append(w)
    # Code is scanned only for the subject's own words and symbols (its lexicon and
    # sense list, e.g. `len`, `.append`): a seed word there is usually an identifier.
    code = _code_texts(spec)
    own = sorted(set(ctx.get("lexicon") or []) | set(ctx.get("sense_list") or []))
    for w in own if code else []:
        pat = phrase_pattern(w)
        if w not in used and pat and any(pat.search(x) for x in code):
            used.append(w)
    resolved = {}
    for term in spec.get("terms") or []:
        if isinstance(term, dict) and _s(term.get("term")).strip():
            resolved[" ".join(_s(term["term"]).lower().split())] = _s(term.get("resolution")).strip()
    th = spec.get("theory") if isinstance(spec.get("theory"), dict) else {}
    defined = set(" ".join(_s(w.get("term")).lower().split())
                  for w in th.get("words") or [] if isinstance(w, dict))
    glossary = ctx.get("glossary")
    sheet_words = ctx.get("sheet_words")
    lexicon = set(ctx.get("lexicon") or [])
    missing = [w for w in used if not resolved.get(w)]
    unknown, wrong, bad_everyday, bad_measured, not_owned, not_there = [], [], [], [], [], []
    for w in used:
        res = resolved.get(w)
        if not res:
            continue
        if not _res_ok(res):
            unknown.append(w)
        elif res == "defined_here":
            if w not in defined:
                wrong.append(w)
        elif res == "everyday":
            if w in lexicon or w in defined or (t in TEACHING_TYPES and _taught(w, spec, ctx, texts)):
                bad_everyday.append(w)
        elif res == "measured_here":
            if t not in MEASURING:
                bad_measured.append(w)
        elif t == "theory":
            wrong.append(w)
        elif res == "glossary" and glossary is not None and w not in glossary:
            not_owned.append(w)
        elif res.startswith("defined_on:") and sheet_words is not None:
            target = res[len("defined_on:"):]
            if w not in (sheet_words.get(target) or ()):
                not_there.append("'%s' (%s)" % (w, target))
    probs = []
    if missing:
        probs.append("used without a resolution (use %s, or plain words): %s"
                     % (", ".join(RESOLUTIONS), _listed(["'%s'" % w for w in missing])))
    if unknown:
        probs.append("unknown resolution for %s (use %s)" % (_listed(["'%s'" % w for w in unknown]),
                                                            ", ".join(RESOLUTIONS)))
    if wrong:
        if t == "theory":
            probs.append("must be defined_here and listed in theory.words: %s" % _listed(["'%s'" % w for w in wrong]))
        else:
            probs.append("marked defined_here but not in theory.words: %s" % _listed(["'%s'" % w for w in wrong]))
    if bad_everyday and t in TEACHING_TYPES:
        probs.append("everyday is not allowed for a word in the subject lexicon, one this sheet defines, or one "
                     "it teaches (in the title, a section title, the topic's name or a question, or used %d times "
                     "or more): define it in theory.words: %s"
                     % (TAUGHT_USES, _listed(["'%s'" % w for w in bad_everyday])))
    elif bad_everyday:
        # No theory block here (drills, cold ...), so point at the resolutions this sheet can use.
        opts = (["defined_here"] if defined else []) + ["defined_on:<sheet>", "glossary"]
        opts += ["measured_here"] if t in MEASURING else []
        probs.append("everyday is not allowed for a word in the subject lexicon or one this sheet defines: "
                     "resolve it %s or %s, or use plain words: %s"
                     % (", ".join(opts[:-1]), opts[-1], _listed(["'%s'" % w for w in bad_everyday])))
    if bad_measured:
        probs.append("measured_here is only for measuring sheets (%s): %s"
                     % (", ".join(MEASURING), _listed(["'%s'" % w for w in bad_measured])))
    if not_owned:
        probs.append("marked glossary but not in the learner's glossary (glossary add <subject> <term>): %s"
                     % _listed(["'%s'" % w for w in not_owned]))
    if not_there:
        probs.append("defined_on names no sheet of this subject that defines the word (in its theory.words, "
                     "or a term resolved defined_here); build that sheet first, or resolve it another way: %s"
                     % _listed(not_there))
    if probs:
        return "FAIL", "; ".join(probs)
    if not used:
        return "PASS", "no listed words used"
    return "PASS", "%d listed word%s resolved" % (len(used), "" if len(used) == 1 else "s")


def pace_floor(spec, pace_s=None):
    """The builder's honest estimate (builder.md): pace_s[layer] for each question, over 60, plus 1 minute.
    An official question (origin ``official:``) is left out: the exam's clock times it, not the pace."""
    secs = 0.0
    for it in _items(spec):
        if _s(it.get("origin")).startswith("official:"):
            continue
        secs += learning.pace_for(it.get("layer"), pace_s) * len(_asks(it))
    return secs / 60.0 + 1


def reading_words(spec):
    """The words a reading sheet asks the learner to read: the floor box, the words box and the sections."""
    th = spec.get("theory") if isinstance(spec.get("theory"), dict) else {}
    texts = [_s(f) for f in (th.get("floor") or [])]
    for w in th.get("words") or []:
        if isinstance(w, dict):
            texts += [_s(w.get("term")), _s(w.get("gloss")), _s(w.get("def"))]
    for sec in th.get("sections") or []:
        if isinstance(sec, dict):
            texts += [_s(sec.get("title")), _s(sec.get("body"))]
    return sum(len(t.split()) for t in texts)


def over_budget_fix(stype):
    """What to do about a sheet over its budget: a measurement is split or given a longer block, never cut."""
    if stype in BUDGET_EXEMPT:
        return ("a measurement is not cut to fit: split a part Claude wrote into sittings (measure.md §3), "
                "or book an official paper a block of its length plus 10–15 min")
    return "cut questions"


def _l5(spec, ctx):
    t = spec.get("type")
    budget, basis = ctx.get("budget") or (None, None)
    try:
        est_f = float(spec.get("est_min"))
    except (TypeError, ValueError):
        return "FAIL", "est_min is not a number"
    # The estimate is the builder's own number, so it is checked against the pace it
    # must come from. A triage sheet is a mark per word, not a question at pace.
    floor = pace_floor(spec, ctx.get("pace_s"))
    if t not in FLOOR_EXEMPT and est_f + 1e-9 < floor:
        fix = ("recount it; a measurement is never cut: split a part Claude wrote into sittings (measure.md §3), "
               "or book it a longer block" if t in BUDGET_EXEMPT else "recount it, or cut questions")
        return "FAIL", ("est_min %s is under the pace floor of %s min (pace_s of each question's layer, "
                        "over 60, plus 1; official questions left out): %s"
                        % (_num(est_f), _num(math.ceil(floor - 1e-9)), fix))
    if budget is None:
        return "PASS", "no budget known (pass --budget-min)"
    if est_f <= budget + 1e-9:
        return "PASS", "~%s min within %s min (%s)" % (_num(est_f), _num(round(budget, 1)), basis)
    return "FAIL", "~%s min is over the budget of %s min (%s): %s" % (_num(est_f), _num(round(budget, 1)), basis,
                                                                     over_budget_fix(t))


def _l6(spec, ctx):
    if spec.get("type") != "drills":
        return "PASS", "not a drills sheet"
    lo, hi = ctx.get("block_size") or (3, 8)
    items = _items(spec)
    by_n = dict((it.get("n"), it) for it in items)
    blocks = [b for b in (spec.get("blocks") or []) if isinstance(b, dict)]
    if not blocks:
        return "FAIL", "a drills sheet needs blocks"
    probs, seen = [], {}
    for i, b in enumerate(blocks, start=1):
        name = "block %d" % i
        if not _s(b.get("title")).strip():
            probs.append("%s has no title" % name)
        its = b.get("items") if isinstance(b.get("items"), list) else []
        if not (lo <= len(its) <= hi):
            probs.append("%s has %d items (allowed %d–%d)" % (name, len(its), lo, hi))
        unknown = [n for n in its if n not in by_n]
        if unknown:
            probs.append("%s lists item %s, which is not on the sheet" % (name, _listed(unknown)))
        for n in its:
            seen[n] = seen.get(n, 0) + 1
        known = [by_n[n] for n in its if n in by_n]
        no_op = [it.get("n") for it in known if not _s(it.get("op")).strip()]
        if no_op:
            probs.append("item %s has no op" % _listed(no_op))
        ops = []
        for it in known:
            op = _s(it.get("op")).strip()
            if op and op not in ops:
                ops.append(op)
        if len(ops) > 1:
            probs.append("%s mixes operations (%s)" % (name, _listed(ops)))
        # The failure gate covers the 3 items that end at gate_after, and stops something only
        # when at least 2 items come after it.
        if b.get("gate_after") is not None:
            ga = b.get("gate_after")
            pos = its.index(ga) + 1 if ga in its and not isinstance(ga, bool) else 0
            if pos < 3 or len(its) - pos < 2:
                probs.append("%s: gate_after must be one of its items, with at least 3 items up to it and 2 after "
                             "it (got %s)" % (name, _s(ga)))
    twice = [n for n, c in seen.items() if c > 1 and n in by_n]
    if twice:
        probs.append("item %s is in more than one block" % _listed(twice))
    outside = [it.get("n") for it in items if it.get("n") not in seen]
    if outside:
        probs.append("item %s is in no block" % _listed(outside))
    if probs:
        return "FAIL", "; ".join(probs[:MAX_LISTED])
    return "PASS", "%d block%s, one operation each" % (len(blocks), "" if len(blocks) == 1 else "s")


def _l7(spec, ctx):
    """Cold validity (CONTRACT 6.4), judged at the time the sheet will be sat.

    ``ctx["at"]`` is that time (the linked block's start); without it, now.
    cold:<topic>: the first serve after teaching (or one again after a recheck
    that left the topic below 3: learning.needs_window) needs teaching on record
    and the window, plus no exposure in the 24 h before and no untreated mistake
    on the topic; any later serve needs only the last two. error:<E>: not untreated, due (next_due <= that day), no
    exposure in the 24 h before, no untreated mistake on the topic.
    sentinel:<E> (a retired mistake, possibly archived): the same without the
    due date. A mixed sheet is practice, but grading moves the ladder for its
    error: and sentinel: items, so they get the same checks; a cold:<topic>
    item there fails, since a recheck in its window is a cold sheet. A words
    recheck is judged as a cold sheet, but only its first serve by the window:
    words sheets don't feed levels, and their later rungs are placed by hand.
    Other types are not timed here, though the late-recheck probe of plan.md
    section 7 carries cold:<topic> items too. On a cold sheet, every
    cold:<topic> topic needs MIN_COLD_ASKS questions.
    """
    stype = spec.get("type")
    if stype not in RECHECK_TYPES:
        return "PASS", "timing not checked on a %s sheet" % (stype or "untyped")
    at = ctx.get("at") or ctx.get("now") or dates.now()
    when = ctx.get("at_label") or "now"
    exposures = ctx.get("exposures") or []
    errors = ctx.get("errors") or []
    topics_state = ctx.get("topics_state") or {}
    window = ctx.get("window")
    by_id = dict((e.get("id"), e) for e in errors if e.get("id"))
    probs, checked = [], 0
    for it in _items(spec):
        origin = _s(it.get("origin"))
        n = _s(it.get("n"))
        if origin.startswith("cold:"):
            checked += 1
            topic = origin[len("cold:"):]
            if stype == "mixed":
                probs.append("item %s (%s): a 2-day recheck item belongs on a cold sheet, not on %s practice; "
                             "build the recheck as type cold" % (n, topic, stype))
                continue
            state = topics_state.get(topic)
            if stype == "words":
                first = learning.is_first_serve(state)
            else:
                first = learning.needs_window(topic, state, exposures)
            if first and not learning.has_first_serve_basis(topic, exposures, state):
                probs.append("item %s (%s): not taught yet (no teaching on record), so it is not recheck "
                             "material" % (n, topic))
                continue
            res = learning.cold_eligibility(topic, at, exposures, errors, window=window, first_serve=first)
            if not res.get("eligible"):
                probs.append("item %s (%s): %s" % (n, topic, res.get("reason")))
        elif origin.startswith("error:") or origin.startswith("sentinel:"):
            checked += 1
            kind, eid = origin.split(":", 1)
            e = by_id.get(eid)
            if e is None:
                probs.append("item %s: %s is not on file" % (n, eid))
            elif e.get("status") == "untreated":
                probs.append("item %s: %s is untreated (repair it before it is served cold)" % (n, eid))
            elif kind == "error":
                res = learning.error_reserve_eligibility(e, at, exposures, errors)
                if not res.get("eligible"):
                    probs.append("item %s (%s, %s): %s" % (n, eid, e.get("topic"), res.get("reason")))
            else:
                res = learning.cold_eligibility(e.get("topic"), at, exposures, errors, first_serve=False)
                if not res.get("eligible"):
                    probs.append("item %s (%s, %s): %s" % (n, eid, e.get("topic"), res.get("reason")))
    if stype == "cold":
        probs += _thin_rechecks(spec)
    if probs:
        return "FAIL", "; ".join(probs[:MAX_LISTED]) + ("" if when == "now" else " (judged %s)" % when)
    if not checked:
        return "PASS", "no recheck items"
    return "PASS", "%d recheck item%s eligible %s" % (checked, "" if checked == 1 else "s", when)


def _thin_rechecks(spec):
    """A cold pass counts toward a level only with MIN_COLD_ASKS counted questions on the
    topic in one sitting (learning.py), so a recheck topic served once is used up for
    nothing. Every question on the topic counts, its error: and sentinel: items too."""
    counts, order = {}, []
    for it in _items(spec):
        origin = _s(it.get("origin"))
        if origin.startswith("cold:") and origin[len("cold:"):] not in order:
            order.append(origin[len("cold:"):])
        for a in _asks(it):
            t = _s(a.get("topic") or it.get("topic"))
            counts[t] = counts.get(t, 0) + 1
    return ["topic %s has %d question%s: a 2-day recheck counts only with at least %d questions on the topic; "
            "add one or drop the topic" % (t, counts.get(t, 0), "" if counts.get(t, 0) == 1 else "s",
                                           learning.MIN_COLD_ASKS)
            for t in order if counts.get(t, 0) < learning.MIN_COLD_ASKS]


def _passage_asks(spec):
    """Ask ids whose answer is copied from the passage (``answer_in_passage`` on the item or the ask)."""
    out = set()
    for it in _items(spec):
        for a in _asks(it):
            if it.get("answer_in_passage") is True or a.get("answer_in_passage") is True:
                out.add(a.get("id"))
    return out


def _l8(spec, ctx):
    """No accepted answer (3+ characters) appears in the visible text: a case-folded,
    whitespace-normalised substring test (CONTRACT 7.4), so an answer inside a
    longer word counts too.

    Two exemptions, both still checked everywhere else:
    - an accepted string that is a printed option label (a roman numeral or a
      letter at the start of an option line, e.g. 'iii.' or '(B)'): a
      choice question always prints its labels;
    - a question marked ``answer_in_passage`` (copy ONE word from the
      passage): matches inside item texts (the passage) are allowed, but not
      in titles, labels, check hints or theory.
    """
    key = ctx.get("key")
    if not isinstance(key, dict):
        return "FAIL", "no sealed key on file for this sheet"
    visible = [_norm(x) for x in render.visible_texts(spec)]
    stems = set(_norm(it.get("text")) for it in _items(spec) if _s(it.get("text")).strip())
    others = [v for v in visible if v not in stems]
    labels = choice_labels([it.get("text") for it in _items(spec)])
    passage = _passage_asks(spec)
    leaks = []
    for aid, entry in key.items():
        accepts = entry.get("accept") if isinstance(entry, dict) else None
        if not isinstance(accepts, list):
            continue
        pool = others if aid in passage else visible
        for a in accepts:
            if isinstance(a, bool) or not isinstance(a, (str, int, float)):
                continue
            s = _norm(a)
            if len(s) < MIN_LEAK_LEN or _bare(a) in labels:
                continue
            if any(s in v for v in pool):
                leaks.append(aid)
                break
    if leaks:
        return "FAIL", "an accepted answer is visible on the sheet for question%s %s" % (
            "s" if len(leaks) > 1 else "", _listed(leaks))
    return "PASS", "no accepted answer is visible"


def _l9(spec, ctx):
    t = spec.get("type")
    if t in LEAST_SURE_EXEMPT:
        return "PASS", "not required on %s sheets" % t
    if spec.get("least_sure") is True:
        return "PASS", "the sheet ends with the Least-sure line"
    return "FAIL", "least_sure must be true on %s sheets (one closing line: the Least-sure line)" % t


def _hint_words(hint):
    return re.sub(r"[^\w\s'-]", " ", _s(hint)).strip()


def _l10(spec, ctx):
    bad = []
    for it in _items(spec):
        for a in _asks(it):
            if a.get("check") is not True:
                continue
            hint = _s(a.get("check_hint")).strip()
            if hint and (_SEARCH_HINT.search(hint) or _BARE_HINT.match(" ".join(_hint_words(hint).split()))):
                bad.append(a.get("id"))
    if bad:
        return "FAIL", ("the check hint on question%s %s asks for a search, a re-solve or a confidence "
                        "rating: name the check to run (put the answer back in, rebuild the total, test the "
                        "definition used against the question's words)" % ("s" if len(bad) > 1 else "",
                                                                             _listed(bad)))
    return "PASS", "every check hint names a check"


def _owned(level):
    try:
        return level is not None and learning.level_rank(level) >= learning.level_rank("3p")
    except Exception:  # an unreadable level counts as not owned
        return False


def _w3(spec, ctx):
    if spec.get("type") not in CHECKABLE_TYPES:
        return "PASS", "no check lines on %s sheets" % spec.get("type")
    state = ctx.get("topics_state") or {}
    missing, second = [], []
    for it in _items(spec):
        for a in _asks(it):
            if a.get("check") is not True:
                continue
            topic_state = state.get(_s(a.get("topic") or it.get("topic")))
            if isinstance(topic_state, dict) and _owned(topic_state.get("level")):
                continue
            hint = _s(a.get("check_hint")).strip()
            if not hint:
                missing.append(a.get("id"))
            elif _SECOND_WAY_HINT.search(hint):
                second.append(a.get("id"))
    probs = []
    if missing:
        probs.append("no hint on %s" % _listed(missing))
    if second:
        probs.append("a second method or 'weakest step' on %s" % _listed(second))
    if probs:
        return "WARN", ("%s: on a topic the learner doesn't own yet (below mastery 3), name the check the "
                        "theory sheet worked, or one that uses only what they own" % "; ".join(probs))
    return "PASS", "checks on new topics name a check the learner can run"


def order_overridden(overrides):
    """True when the subject holds a locked override of R12 order (concrete case first), or of
    R12 as it stood before the split: the learner chose to see the rule first."""
    for o in overrides or []:
        if (isinstance(o, dict) and o.get("locked") is True
                and " ".join(_s(o.get("rule")).lower().split()) in ORDER_RULES):
            return True
    return False


def _l11(spec, ctx):
    """A theory or repair sheet shows a worked case, and shows it before the rule: a
    concept introduced only by its definition is a don't (sheets.md §5). The order is a
    default (R12 order): a locked override lets the rule come first, never the worked
    case go. A guess before reading (a ``prequestion`` section) goes only on a theory
    sheet, before the worked case that answers it."""
    theory = spec.get("theory") if isinstance(spec.get("theory"), dict) else {}
    kinds = [_s(sec.get("kind")) for sec in (theory.get("sections") or []) if isinstance(sec, dict)]
    if "prequestion" in kinds and spec.get("type") != "theory":
        return "FAIL", "a guess before reading (prequestion) goes on a new topic's theory sheet only"
    if spec.get("type") not in WORKED_CHECK_TYPES:
        return "PASS", "not a theory or repair sheet"
    if "prequestion" in kinds and "worked" in kinds and kinds.index("prequestion") > kinds.index("worked"):
        return "FAIL", "the guess comes after the worked case that answers it: put the prequestion first"
    if "worked" not in kinds:
        return "FAIL", "no worked section: show a concrete worked case, then the rule"
    if "rule" in kinds and kinds.index("rule") < kinds.index("worked"):
        if order_overridden(ctx.get("overrides")):
            return "PASS", ("the rule comes first, as the learner's locked override of R12 order asks; "
                            "a worked case follows")
        return "FAIL", "the rule comes before the first worked case: put the worked case first"
    return "PASS", "a worked case comes before the rule"


def _op_key(op):
    return _s(op).strip().lower()


def shown_ops(specs):
    """{topic: the operations its theory, external, example and repair sheets show}: their
    pencil questions' ``op`` and their worked sections' ``ops``. None when unknown."""
    if specs is None:
        return None
    out = {}
    for _row, spec in specs:
        if spec.get("type") not in SHOWING_TYPES:
            continue
        topics = []
        for it in _items(spec):
            t = _s(it.get("topic")).strip()
            if not t:
                continue
            if t not in topics:
                topics.append(t)
            out.setdefault(t, set())
            if _op_key(it.get("op")):
                out[t].add(_op_key(it.get("op")))
        th = spec.get("theory") if isinstance(spec.get("theory"), dict) else {}
        for sec in th.get("sections") or []:
            if not isinstance(sec, dict) or _s(sec.get("kind")) != "worked" or not isinstance(sec.get("ops"), list):
                continue
            for t in topics:
                out[t].update(_op_key(o) for o in sec["ops"] if _op_key(o))
    return out


def _l12(spec, ctx):
    """Drills ask only for operations a sheet on the topic has shown: each new item's op is
    a pencil question's op or a worked section's op on a theory, external, example or
    repair sheet of that topic (any not void, so a theory built ahead with its drills
    counts). A topic with no such sheet (taught by a tutor, from a migration) is skipped."""
    if spec.get("type") != "drills":
        return "PASS", "not a drills sheet"
    shown = ctx.get("shown_ops")
    if shown is None:
        return "PASS", "not checked (no sheets read)"
    missing, checked = [], 0
    for it in _items(spec):
        if _s(it.get("origin") or "new") != "new":
            continue
        topic = _s(it.get("topic")).strip()
        op = _op_key(it.get("op"))
        if topic not in shown or not op:
            continue
        checked += 1
        if op not in shown[topic]:
            missing.append("item %s (%s): '%s'" % (_s(it.get("n")), topic, op))
    if missing:
        return "FAIL", ("an operation no theory, external, example or repair sheet of the topic has shown: %s. "
                        "Show it worked there (a worked section's ops, or a pencil question's op) and rebuild "
                        "that sheet, or drop the item; never rename an op to pass" % _listed(missing, 4))
    if not checked:
        return "PASS", "no topic here has a teaching sheet on file"
    return "PASS", "every new item's operation was shown on a sheet of its topic"


def _sections(spec):
    theory = spec.get("theory") if isinstance(spec.get("theory"), dict) else {}
    return [sec for sec in (theory.get("sections") or []) if isinstance(sec, dict)]


def _meaning_layers(spec):
    """The layers on a theory sheet that need its meaning box (L13)."""
    return sorted(set(_s(it.get("layer")) for it in _items(spec)) & set(MEANING_LAYERS))


def _l13(spec, ctx):
    """A theory sheet on a procedural, conceptual or code topic says what the object is and why
    the rule follows from it, in a ``meaning`` section after the worked case."""
    if spec.get("type") != "theory":
        return "PASS", "not a theory sheet"
    if any(_s(sec.get("kind")) == "meaning" for sec in _sections(spec)):
        return "PASS", "the sheet says what it is and why"
    need = _meaning_layers(spec)
    if need:
        return "FAIL", ("no meaning section on a %s topic: after the worked case, say in at most 5 lines what "
                        "the object is (one everyday anchor or a picture in words) and why the rule follows "
                        "from it" % "/".join(need))
    layers = "/".join(sorted(set(_s(it.get("layer")) for it in _items(spec)) - {""})) or "no"
    return "PASS", "not required on a %s topic (W6 asks for it)" % layers


def _w6(spec, ctx):
    if spec.get("type") != "theory":
        return "PASS", "not a theory sheet"
    secs = _sections(spec)
    kinds = [_s(sec.get("kind")) for sec in secs]
    meaning = [sec for sec in secs if _s(sec.get("kind")) == "meaning"]
    if not meaning:
        if _meaning_layers(spec):
            return "PASS", "L13 asks for it"
        return "WARN", ("no meaning section: say in at most 5 lines what it is and why the rule follows, or, "
                        "for a convention, that it is one to learn as given")
    probs = []
    words = sum(len(_s(sec.get("body")).split()) for sec in meaning)
    if words > MEANING_MAX_WORDS:
        probs.append("it runs to %d words: keep it to about 5 lines (%d words)" % (words, MEANING_MAX_WORDS))
    if "rule" in kinds and kinds.index("rule") < kinds.index("meaning"):
        probs.append("it comes after the rule: put it between the worked case and the rule")
    if probs:
        return "WARN", "the meaning box: " + "; ".join(probs)
    return "PASS", "a short meaning box before the rule"


def _l14(spec, ctx):
    """Scaffolds (printed working) go on practice sheets only, and fade before a drills block ends."""
    items = _items(spec)
    with_sc = [it.get("n") for it in items if it.get("scaffold") not in (None, [], {})]
    if not with_sc:
        return "PASS", "no scaffolds"
    t = spec.get("type")
    if t in SCAFFOLD_REFUSED:
        return "FAIL", ("printed working (scaffold) on item %s of a %s sheet: a measuring or mixed sheet is "
                        "question, box and check line only" % (_listed(with_sc), t))
    if t == "drills":
        late = []
        for b in spec.get("blocks") or []:
            its = b.get("items") if isinstance(b, dict) and isinstance(b.get("items"), list) else []
            late += [n for n in its[-SCAFFOLD_FADED:] if n in with_sc]
        if late:
            return "FAIL", ("a scaffold on item %s, one of the last two of its block: they print only the box, so "
                            "the block shows whether the working now happens unprompted" % _listed(late))
    return "PASS", "working printed on item %s, faded before each block ends" % _listed(with_sc)


def _w4(spec, ctx):
    if spec.get("type") not in WORKED_CHECK_TYPES:
        return "PASS", "not a theory or repair sheet"
    theory = spec.get("theory") if isinstance(spec.get("theory"), dict) else {}
    worked = [sec for sec in (theory.get("sections") or [])
              if isinstance(sec, dict) and _s(sec.get("kind")) == "worked"]
    if any(_CHECK_STEP.search(_s(sec.get("body"))) for sec in worked):
        return "PASS", "the worked case shows its check"
    return "WARN", ("no worked case shows its check: end it with a step labelled 'Check:', the same check "
                    "the drills will ask for")


def _w5(spec, ctx):
    if spec.get("type") not in READING_TYPES:
        return "PASS", "not a theory, example or repair sheet"
    try:
        est_f = float(spec.get("est_min"))
    except (TypeError, ValueError):
        return "PASS", "est_min is checked by L5"
    words = reading_words(spec)
    need = pace_floor(spec, ctx.get("pace_s")) + words / float(READING_WPM)
    if est_f + 1e-9 < need:
        return "WARN", ("est_min %s leaves no time to read the sheet's %d words: at least %s min with the pencil "
                        "questions. Add the reading time, the words over 120 a minute (90 in a second language)"
                        % (_num(est_f), words, _num(math.ceil(need - 1e-9))))
    return "PASS", "%d words to read within ~%s min" % (words, _num(est_f))


def _w1(spec, ctx):
    hits = [str(i) for i, b in enumerate(spec.get("blocks") or [], start=1)
            if isinstance(b, dict) and "=" in _s(b.get("title"))]
    if hits:
        return "WARN", "'=' in block title %s: keep formulas out of headings" % _listed(hits)
    return "PASS", "no formula in block titles"


def _w2(spec, ctx):
    """A sentence is answered off numbers the learner has just computed: on drills that mix
    computed and sentence items, a sentence item with no computed item before it on its topic
    stands cut off from them. Put it as the last question of the item it is about."""
    if spec.get("type") != "drills":
        return "PASS", "not a drills sheet"
    items = _items(spec)
    verbal = [it for it in items if is_verbal(it)]
    if not verbal:
        return "PASS", "no sentence or verbal items"
    if len(verbal) == len(items):
        return "PASS", "every item is a sentence or verbal item"
    cut_off, computed = [], set()
    for it in items:
        topic = _s(it.get("topic"))
        if not is_verbal(it):
            computed.add(topic)
        elif topic not in computed:
            cut_off.append(_s(it.get("n")))
    if cut_off:
        return "WARN", ("sentence item %s has no computed item before it on its topic: make it the last "
                        "question of the computed item it is about ('Using your answers to 3a–3b, …')"
                        % _listed(cut_off))
    return "PASS", "each sentence item follows the numbers it is about"


CHECKS = {"L1": _l1, "L2": _l2, "L3": _l3, "L4": _l4, "L5": _l5, "L6": _l6, "L7": _l7,
          "L8": _l8, "L9": _l9, "L10": _l10, "L11": _l11, "L12": _l12, "L13": _l13, "L14": _l14,
          "W1": _w1, "W2": _w2, "W3": _w3, "W4": _w4, "W5": _w5, "W6": _w6}


def check(spec, ctx=None):
    """Run every rule. Returns a list of result dicts, in rule order."""
    ctx = ctx or {}
    out = []
    for rule in RULES:
        try:
            status, detail = CHECKS[rule](spec, ctx)
        except Exception as exc:  # a malformed spec must fail the rule, not crash lint
            status, detail = ("WARN" if rule.startswith("W") else "FAIL"), "could not check (%s)" % type(exc).__name__
        out.append({"rule": rule, "status": status, "title": TITLES[rule], "detail": detail})
    return out


def passed(results):
    return not any(r["status"] == "FAIL" for r in results)


def format_line(r):
    return "%s %s %s%s" % (r["rule"], r["status"], r["title"], (": " + r["detail"]) if r["detail"] else "")


# ==========================================================================
# Context from the workspace
# ==========================================================================

def _block_siblings(subject, block_id, sheet_id):
    """(minutes, ids) of the other sheets already handed over on a block (issued, sat
    or graded: a sheet already marked in the block used its minutes). A sheet built
    for the block and not issued yet is left out: it may still be cut, and the sheet
    issued last is the one refused, never the recheck that opens the session."""
    try:
        rows = subject.load_sheets()
    except Exception:
        return 0.0, []
    total, ids = 0.0, []
    for r in rows:
        if r.get("block") != block_id or r.get("id") == sheet_id or r.get("status") not in HANDED_OVER:
            continue
        est = r.get("est_min")
        if isinstance(est, bool) or not isinstance(est, (int, float)):
            continue
        total += float(est)
        ids.append(r.get("id"))
    return total, ids


def _session_minutes(subject, block_id):
    """The open session's planned minutes plus its extension, when it runs on this block."""
    try:
        lock = subject.read_session_lock()
    except Exception:
        return None
    if not isinstance(lock, dict) or not block_id or lock.get("block") != block_id:
        return None
    try:
        return float(lock.get("planned_min") or 0) + float(lock.get("extension_min") or 0)
    except (TypeError, ValueError):
        return None


def _session_work(ws, subject, planned):
    """The work minutes ``session open`` prints for a session of ``planned`` minutes
    (learning.session_budget, at the subject's dominant layer and the root's breaks)."""
    try:
        cfg = subject.load() or {}
    except Exception:
        cfg = {}
    try:
        sess = (ws.load_config() or {}).get("session") or {}
    except Exception:
        sess = {}
    bmin = sess.get("break_min")
    return learning.session_budget(planned, learning.dominant_layer(cfg), cfg.get("pace_s"),
                                   sess.get("break_every_min") or 75, 10 if bmin is None else bmin)["work_min"]


def budget_for(ws, subject, spec, row=None, budget_min=None, block=None):
    """(minutes or None, basis) for L5 and the issue check.

    ``--budget-min`` wins. Else the linked block: 0.8 × its minutes, or, for a
    measurement (diagnostic, mock, checkpoint), its minutes less the RECORD_MIN
    it keeps for recording (measure.md §4: the exam clock plus 10–15 minutes).
    A practice sheet on the block of the open session uses the work minutes
    ``session open`` printed for its planned minutes (with its extension)
    instead, longer or shorter than the block: a slot split into a recheck block
    and a session block is one session, and a session opened short has less
    time. Every other sheet already issued on the block (sat and graded too) is
    taken off, so sheets are sized together, not one by one.
    Else 0.8 × the default session; a measurement never uses that, and a mock or
    checkpoint falls back to the exam's own minutes (``format.minutes``).
    """
    if budget_min is not None:
        return float(budget_min), "--budget-min %s" % _num(budget_min)
    measuring = spec.get("type") in BUDGET_EXEMPT
    block_id = block or (row or {}).get("block") or spec.get("block")
    if block_id:
        b = ws.get_block(block_id)
        if b and b.get("start") and b.get("end"):
            try:
                minutes = dates.minutes_between(b["start"], b["end"])
            except ValueError:
                minutes = None
            if minutes is not None:
                session = None if measuring else _session_minutes(subject, block_id)
                if measuring:
                    total, basis = max(minutes - RECORD_MIN, 0.0), "block %s of %s min, less %d to record" % (
                        block_id, _num(round(minutes)), RECORD_MIN)
                elif session is not None and session > 0:
                    work = _session_work(ws, subject, session)
                    total, basis = work, "the session's %s work minutes on block %s" % (_num(work), block_id)
                else:
                    total, basis = BUDGET_FRACTION * minutes, "0.8 × block %s of %s min" % (
                        block_id, _num(round(minutes)))
                others, ids = _block_siblings(subject, block_id, spec.get("id") or (row or {}).get("id"))
                if ids:
                    basis += ", less %s min on %s" % (_num(round(others, 1)), _listed(ids, 3))
                return max(total - others, 0.0), basis
    if measuring:
        if spec.get("type") in ("mock", "checkpoint"):
            try:
                exam = (subject.load().get("format") or {}).get("minutes")
            except Exception:
                exam = None
            if isinstance(exam, (int, float)) and not isinstance(exam, bool) and exam > 0:
                return float(exam), "the exam's %s min (format.minutes)" % _num(exam)
        return None, None
    try:
        length = (ws.load_config().get("session") or {}).get("length_min")
    except Exception:
        length = None
    if isinstance(length, (int, float)) and not isinstance(length, bool) and length > 0:
        return BUDGET_FRACTION * length, "0.8 × the default session of %s min" % _num(length)
    return None, None


def read_key(subject, sheet_id):
    """The sealed key, read in-process (never printed). None if absent or unreadable."""
    try:
        data = fio.read_json(subject.key_path(sheet_id))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def sitting_time(ws, block_id, now, at=None):
    """(time the sheet will be sat, label) for L7: ``at``, else the block's start, else now.

    For an unplaced recheck obligation, the later of now and its window's start.
    """
    if at is not None:
        return at, "at %s" % dates.fmt_iso(at)
    if block_id:
        b = ws.get_block(block_id)
        if b is not None:
            s = dates.try_parse_iso(b.get("start"))
            if s is not None and s > now:
                return s, "at the start of block %s (%s)" % (block_id, dates.fmt_iso(s))
            if s is not None:
                return now, "now"  # the block has started: the sheet is sat from now on
            w = b.get("window") if isinstance(b.get("window"), dict) else {}
            f = dates.try_parse_iso(w.get("from"))
            if f is not None and f > now:
                return f, "at the opening of the window of %s (%s)" % (block_id, dates.fmt_iso(f))
    return now, "now"


def _term_key(value):
    return " ".join(_s(value).lower().split())


def _sealed_specs(subject):
    """[(row, spec)] for this subject's sheets that are not void, read from their sealed specs.

    None when the sheet rows can't be read; a spec that can't be read is left out.
    """
    try:
        rows = subject.load_sheets()
    except Exception:
        return None
    out = []
    for r in rows:
        if not isinstance(r, dict) or r.get("status") == "void" or not r.get("id"):
            continue
        try:
            spec = fio.read_json(subject.spec_path(r["id"]))
        except Exception:
            continue
        if isinstance(spec, dict):
            out.append((r, spec))
    return out


def defined_words(spec):
    """The words a sheet defines: its ``theory.words`` plus its terms resolved ``defined_here``."""
    th = spec.get("theory") if isinstance(spec.get("theory"), dict) else {}
    out = set(_term_key(w.get("term")) for w in th.get("words") or [] if isinstance(w, dict))
    for t in spec.get("terms") or []:
        if isinstance(t, dict) and _s(t.get("resolution")).strip() == "defined_here":
            out.add(_term_key(t.get("term")))
    out.discard("")
    return out


def _sheet_words(specs):
    """{sheet id: the words it defines} for L4's ``defined_on:<id>``; None when unknown."""
    if specs is None:
        return None
    return dict((r["id"], defined_words(spec)) for r, spec in specs)


def _glossary_terms(subject):
    try:
        rows = subject.load_glossary()
    except Exception:
        return set()
    return set(" ".join(_s(r.get("term")).lower().split()) for r in rows if _s(r.get("term")).strip())


def gather(ws, subject, spec, row=None, budget_min=None, now=None, block=None, at=None):
    cfg = subject.load()
    bs = cfg.get("block_size") or {}
    try:
        block_size = (int(bs.get("min", 3)), int(bs.get("max", 8)))
    except (TypeError, ValueError):
        block_size = (3, 8)
    now = now or ws.now()
    block_id = block or (row or {}).get("block") or spec.get("block")
    sit_at, sit_label = sitting_time(ws, block_id, now, at)
    specs = _sealed_specs(subject)
    return {
        "topics": dict((t["id"], _s(t.get("name")).strip()) for t in subject.topics()),
        "sense": sense_words(cfg),
        "lexicon": set(" ".join(_s(w).lower().split()) for w in _lexicon_terms(cfg.get("lexicon"))),
        "sense_list": set(" ".join(_s(w).lower().split()) for w in _lexicon_terms(cfg.get("sense_list"))),
        "glossary": _glossary_terms(subject),
        "sheet_words": _sheet_words(specs),
        "shown_ops": shown_ops([(r, s) for r, s in specs if r.get("id") != spec.get("id")]
                               if specs is not None else None),
        "block_size": block_size,
        "overrides": cfg.get("overrides") if isinstance(cfg.get("overrides"), list) else [],
        "pace_s": cfg.get("pace_s") if isinstance(cfg.get("pace_s"), dict) else {},
        "budget": budget_for(ws, subject, spec, row, budget_min, block=block_id),
        "now": now,
        "at": sit_at,
        "at_label": sit_label,
        "exposures": subject.load_exposures(),
        "errors": subject.load_errors(include_archive=True),
        "topics_state": subject.load_topics_state(),
        "window": subject.cold_window(),
        "key": read_key(subject, spec.get("id") or (row or {}).get("id")),
    }


def run(ws, subject, spec, row=None, budget_min=None, now=None, block=None, at=None):
    return check(spec, gather(ws, subject, spec, row, budget_min=budget_min, now=now, block=block, at=at))
