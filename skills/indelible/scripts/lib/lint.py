"""The sheet checker: rules L1-L9 and warnings W1-W2 (CONTRACT section 7.4).

``check(spec, ctx)`` is pure: it takes the visible spec and a context dict and
returns one result per rule, in order. ``gather(ws, subject, spec, row)``
builds that context from the workspace (topics, sense words, the glossary,
budget, exposures, errors, the sealed key, and the time the sheet will be
sat). ``run(...)`` does both.

When the sheet is linked to a block (``sheet new/lint --block``, or the
sheet row's block), L5 uses that block's minutes and L7 judges the recheck at
the block's start: a recheck built at the previous close is judged at the time
it will be sat, not at build time. ``sheet issue`` checks both again.

L4 terms: code (inline `spans` and fenced blocks) is never scanned; theory
section bodies are. Resolutions: ``defined_here`` (the word is in
``theory.words`` on this sheet), ``defined_on:<sheet-id>``, ``glossary`` (the
word is in data/glossary.jsonl: ``glossary add``), ``everyday`` (used in its
plain everyday sense; never for a word in the subject lexicon, and never on a
theory sheet for a word it defines), and ``measured_here`` (a measuring sheet
that deliberately tests the word).

The key is read in-process for L8 only. Nothing from it is ever returned or
printed: an L8 FAIL names the question (ask) ids, never the text.

Result rows: ``{"rule": "L4", "status": "PASS"|"FAIL"|"WARN", "title": "terms", "detail": "..."}``.
"""

import re
import unicodedata

from lib import LISTS_DIR, dates, learning
from lib import io as fio
from lib import render

RULES = ["L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9", "W1", "W2"]
TITLES = {
    "L1": "structure", "L2": "check lines", "L3": "unlabelled", "L4": "terms", "L5": "budget",
    "L6": "drill blocks", "L7": "cold validity", "L8": "key leak", "L9": "least-sure",
    "W1": "formula in block title", "W2": "sentences first",
}

# L2: every ask has a check line on these types. The contract lists "repair"
# in neither list; sheets.md and builder.md make check lines optional on
# repair pencils (done with the fix in view), so repair is not required here.
CHECK_REQUIRED = ("drills", "cold", "mixed", "diagnostic", "mock", "checkpoint", "review")
UNLABELLED_TYPES = ("cold", "diagnostic", "mock", "checkpoint", "probe", "mixed")
BUDGET_EXEMPT = ("diagnostic", "mock", "checkpoint")
MEASURING = ("cold", "diagnostic", "mock", "checkpoint", "probe", "words")
RESOLUTIONS = ("defined_here", "defined_on:<sheet-id>", "glossary", "everyday", "measured_here")
LEAST_SURE_EXEMPT = ("theory", "external", "example", "triage")
VERBAL_LAYERS = ("verbal", "reading")
MIN_LEAK_LEN = 3
BUDGET_FRACTION = 0.8
MAX_LISTED = 6

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
    """Text with fenced code blocks and inline code spans blanked out (code is never term-checked)."""
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
    missing = [a.get("id") for it in _items(spec) for a in _asks(it) if a.get("check") is not True]
    if missing:
        return "FAIL", "no check line on question%s %s" % ("s" if len(missing) > 1 else "", _listed(missing))
    return "PASS", "every question has a check line"


def _l3(spec, ctx):
    """CONTRACT 7.4 L3, with one exemption the contract text lacks: the
    adjacency test applies only when the sheet has 2 or more topics. A
    single-topic recheck cannot interleave, and one that also re-serves a
    mistake on that topic needs two items (a cold:<T> item and an error:<E>
    item), so under the literal rule it could never pass."""
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
    """The texts L4 scans: titles, item text, labels, theory section titles and bodies; code removed."""
    texts = [spec.get("title")]
    texts += [b.get("title") for b in spec.get("blocks") or [] if isinstance(b, dict)]
    for it in _items(spec):
        texts.append(it.get("text"))
        texts += [a.get("label") for a in _asks(it)]
    th = spec.get("theory")
    if isinstance(th, dict):
        for sec in th.get("sections") or []:
            if isinstance(sec, dict):
                texts += [sec.get("title"), sec.get("body")]
    return [strip_code(x) for x in texts if _s(x).strip()]


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
    resolved = {}
    for term in spec.get("terms") or []:
        if isinstance(term, dict) and _s(term.get("term")).strip():
            resolved[" ".join(_s(term["term"]).lower().split())] = _s(term.get("resolution")).strip()
    th = spec.get("theory") if isinstance(spec.get("theory"), dict) else {}
    defined = set(" ".join(_s(w.get("term")).lower().split())
                  for w in th.get("words") or [] if isinstance(w, dict))
    glossary = ctx.get("glossary")
    lexicon = set(ctx.get("lexicon") or [])
    missing = [w for w in used if not resolved.get(w)]
    unknown, wrong, bad_everyday, bad_measured, not_owned = [], [], [], [], []
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
            if w in lexicon or w in defined:
                bad_everyday.append(w)
        elif res == "measured_here":
            if t not in MEASURING:
                bad_measured.append(w)
        elif t == "theory":
            wrong.append(w)
        elif res == "glossary" and glossary is not None and w not in glossary:
            not_owned.append(w)
    probs = []
    if missing:
        probs.append("used without a resolution: %s" % _listed(["'%s'" % w for w in missing]))
    if unknown:
        probs.append("unknown resolution for %s (use %s)" % (_listed(["'%s'" % w for w in unknown]),
                                                            ", ".join(RESOLUTIONS)))
    if wrong:
        if t == "theory":
            probs.append("must be defined_here and listed in theory.words (or everyday, in its plain sense): %s"
                         % _listed(["'%s'" % w for w in wrong]))
        else:
            probs.append("marked defined_here but not in theory.words: %s" % _listed(["'%s'" % w for w in wrong]))
    if bad_everyday:
        probs.append("everyday is not allowed for a word in the subject lexicon or one this sheet defines: %s"
                     % _listed(["'%s'" % w for w in bad_everyday]))
    if bad_measured:
        probs.append("measured_here is only for measuring sheets (%s): %s"
                     % (", ".join(MEASURING), _listed(["'%s'" % w for w in bad_measured])))
    if not_owned:
        probs.append("marked glossary but not in the learner's glossary (glossary add <subject> <term>): %s"
                     % _listed(["'%s'" % w for w in not_owned]))
    if probs:
        return "FAIL", "; ".join(probs)
    if not used:
        return "PASS", "no listed words used"
    return "PASS", "%d listed word%s resolved" % (len(used), "" if len(used) == 1 else "s")


def _l5(spec, ctx):
    t = spec.get("type")
    if t in BUDGET_EXEMPT:
        return "PASS", "measurement: sized by the exam clock"
    budget, basis = ctx.get("budget") or (None, None)
    est = spec.get("est_min")
    if budget is None:
        return "PASS", "no budget known (pass --budget-min)"
    try:
        est_f = float(est)
    except (TypeError, ValueError):
        return "FAIL", "est_min is not a number"
    if est_f <= budget + 1e-9:
        return "PASS", "~%s min within %s min (%s)" % (_num(est_f), _num(round(budget, 1)), basis)
    return "FAIL", "~%s min is over the budget of %s min (%s)" % (_num(est_f), _num(round(budget, 1)), basis)


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
    cold:<topic>: the first serve after teaching needs teaching on record and
    the window, plus no exposure in the 24 h before and no untreated mistake
    on the topic. error:<E>: not untreated, due (next_due <= that day), no
    exposure in the 24 h before, no untreated mistake on the topic.
    sentinel:<E> (a retired mistake, possibly archived): the same without the
    due date.
    """
    if spec.get("type") != "cold":
        return "PASS", "not a cold sheet"
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
            state = topics_state.get(topic)
            first = learning.is_first_serve(state)
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
    if probs:
        return "FAIL", "; ".join(probs[:MAX_LISTED]) + ("" if when == "now" else " (judged %s)" % when)
    if not checked:
        return "PASS", "no recheck items"
    return "PASS", "%d recheck item%s eligible %s" % (checked, "" if checked == 1 else "s", when)


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
    return "FAIL", "least_sure must be true on %s sheets (one closing line: Least sure of)" % t


def _w1(spec, ctx):
    hits = [str(i) for i, b in enumerate(spec.get("blocks") or [], start=1)
            if isinstance(b, dict) and "=" in _s(b.get("title"))]
    if hits:
        return "WARN", "'=' in block title %s: keep formulas out of headings" % _listed(hits)
    return "PASS", "no formula in block titles"


def _w2(spec, ctx):
    if spec.get("type") != "drills":
        return "PASS", "not a drills sheet"
    items = _items(spec)
    if not items or not any(is_verbal(it) for it in items):
        return "PASS", "no sentence or verbal items"
    if is_verbal(items[0]):
        return "PASS", "a sentence or verbal item comes first"
    return "WARN", "the first item is not a sentence or verbal item; put one first"


CHECKS = {"L1": _l1, "L2": _l2, "L3": _l3, "L4": _l4, "L5": _l5, "L6": _l6, "L7": _l7,
          "L8": _l8, "L9": _l9, "W1": _w1, "W2": _w2}


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

def budget_for(ws, subject, spec, row=None, budget_min=None, block=None):
    """(minutes or None, basis) for L5."""
    if budget_min is not None:
        return float(budget_min), "--budget-min %s" % _num(budget_min)
    block_id = block or (row or {}).get("block") or spec.get("block")
    if block_id:
        b = ws.get_block(block_id)
        if b and b.get("start") and b.get("end"):
            try:
                minutes = dates.minutes_between(b["start"], b["end"])
                return BUDGET_FRACTION * minutes, "0.8 × block %s of %s min" % (block_id, _num(round(minutes)))
            except ValueError:
                pass
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
    return {
        "topics": dict((t["id"], _s(t.get("name")).strip()) for t in subject.topics()),
        "sense": sense_words(cfg),
        "lexicon": set(" ".join(_s(w).lower().split()) for w in _lexicon_terms(cfg.get("lexicon"))),
        "glossary": _glossary_terms(subject),
        "block_size": block_size,
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
