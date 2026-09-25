"""Brief, due and the generated views.

    brief [subject] [--json]
    due [subject] [--list] [--json]
    render [subject|all] [--force]

``brief`` is the only thing read at session open. It is at most 4,500
characters: long lists are cut with ``+N more (run: ...)``. Everything above
the line ``-- for Claude, do not read aloud --`` may be read to the learner,
so with ``learner.vocab = plain`` it uses plain words and never shows an
``E-``, ``B-``, ``S-`` or ``L-`` id; ids and mistake details go below the line.

Opening a brief increments ``opens_unsat`` on every issued sheet that is not
yet taken. One open is counted per subject in any 3-hour span, and never
while that subject's session is running, so the skill's setup brief and the
session-open brief count once. A sheet issued ahead for a block that has not
started yet is not counted until that block starts.

``render`` regenerates ``<subject>/views/{brief,progress,errors,log}.md``,
``views/week.md`` and the generated section of each CLAUDE.md. A file edited
by hand since the last render is refused (its sha is kept in
``.indelible/render.json``) unless ``--force``, which keeps a ``.bak``.
A file render has never written is never refused.

Other modules may call:
    render_week(ws, start=None, force=False, write=True) -> str   (views/week.md)
    render_subjects(ws, subjects, force=False, skip_edited=False) -> dict
    hand_edits(ws, subjects, include_root=True) -> [rel path]
    session_lock_state(subject, now) -> dict or None
    due_state(subject, now) -> dict
"""

import difflib
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta

from lib import CheckFailed, DataError, LockBusy
from lib import dates, learning, schema
from lib import io as fio
from lib import ws as wsmod

BRIEF_MAX = 4500
CLAUDE_SEP = "-- for Claude, do not read aloud --"
NOTES_MAX_LINES = 25
TODO_DAYS = 3
LAST_SESSIONS = 3
LOG_MAX = 30
LOG_LINE_MAX = 200
ITEM_MAX = 220
OPEN_DEDUPE_H = 3.0
UNCLOSED_AFTER_H = 2.0
REENTRY_GAP_DAYS = 5
OPENS_FORCE = 2

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

ID_RE = re.compile(r"\b(?:E-[a-z0-9-]+-\d{3,}|S-[a-z0-9-]+-\d{3,}|B-\d{8}-[a-z0-9-]+-\d+|L-\d{3,})\b")
COLD_TOKEN_RE = re.compile(r"\bcold:([A-Za-z0-9_-]+(?:,[A-Za-z0-9_-]+)*)")
# Other content tokens (the plan convention: teach:T03, repair:T01,T04 ...).
CONTENT_TOKEN_RE = re.compile(r"\b(?:teach|repair|review|drill|chat):([A-Za-z0-9_-]+(?:,[A-Za-z0-9_-]+)*)")

KIND_PLAIN = {
    "teach": "new skill", "cold": "2-day recheck", "repair": "fixing mistakes", "review": "review",
    "mixed": "mixed practice", "mock": "mock test", "diagnostic": "diagnostic test",
    "checkpoint": "checkpoint test", "words": "words", "oral": "speaking", "project": "project work",
    "long": "long session", "tutor_lesson": "tutor lesson", "buffer": "spare time", "admin": "admin",
}
STATUS_PLAIN = {
    "planned": "planned", "synced": "in calendar", "done": "done", "missed?": "no record yet",
    "missed": "missed", "moved": "moved", "cancelled": "cancelled",
}
INSTRUMENT_PLAIN = {
    "cold": "2-day recheck", "practice": "practice", "diagnostic": "diagnostic test", "mock": "mock test",
    "checkpoint": "checkpoint", "probe": "quick probe", "words": "words check",
}
ERROR_KIND_PLAIN = {"belief": "wrong idea", "slip": "slip", "shaky": "unsure"}
ERROR_STATUS_PLAIN = {"untreated": "needs fixing", "spacing": "coming back", "retired": "done",
                      "reopened": "back again"}
OPEN_BLOCK_STATUSES = ("planned", "synced")


# ==========================================================================
# Registration
# ==========================================================================

def register(subparsers):
    p = subparsers.add_parser("brief", help="the session-open summary (the only thing read at open)")
    p.add_argument("subject", nargs="?", default=None, help="subject id (default: the current or only subject)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(func=cmd_brief)

    p = subparsers.add_parser("due", help="what is due: 2-day rechecks and mistakes, by tier")
    p.add_argument("subject", nargs="?", default=None)
    p.add_argument("--list", action="store_true", help="list items by tier instead of counts")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_due)

    p = subparsers.add_parser("render", help="regenerate the views and the generated part of each CLAUDE.md")
    p.add_argument("target", nargs="?", default=None, help="a subject id, or all (default: all)")
    p.add_argument("--force", action="store_true", help="overwrite views edited by hand (keeps a .bak)")
    p.set_defaults(func=cmd_render)


def _out(text=""):
    sys.stdout.write(text + "\n")


# ==========================================================================
# Small shared helpers
# ==========================================================================

def tz_of(ws):
    return ws.tzinfo()


def now_in(ws):
    """The current time in the workspace time zone (the one clock every command uses)."""
    return ws.now()


def vocab_of(ws):
    try:
        v = (ws.load_config().get("learner") or {}).get("vocab")
    except (DataError, OSError):
        v = None
    return v if v in schema.VOCABS else "plain"


def is_plain(ws):
    return vocab_of(ws) == "plain"


def scrub_ids(text):
    """Remove E-/S-/B-/L- ids from a line meant for a plain-vocabulary learner."""
    if not text:
        return text
    out = ID_RE.sub("", text)
    out = re.sub(r"\(\s*\)", "", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\s+([,.;:)])", r"\1", out)
    return out.strip()


def clip(text, n=ITEM_MAX):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def to_local(value, tz):
    dt = dates.try_parse_iso(value)
    return dt.astimezone(tz) if dt is not None else None


def fmt_day(d):
    d = dates.to_date(d)
    return "%s %d %s" % (dates.WEEKDAYS[d.weekday()], d.day, MONTHS[d.month - 1])


def fmt_when(dt, now=None):
    """``today 07:00`` or ``Thu 15 Oct 07:00`` (dt already local)."""
    if dt is None:
        return "?"
    if now is not None and dt.date() == now.date():
        return "today %s" % dt.strftime("%H:%M")
    return "%s %s" % (fmt_day(dt), dt.strftime("%H:%M"))


def fmt_span(start, end, now=None):
    if start is None:
        return "?"
    if end is None:
        return fmt_when(start, now)
    return "%s–%s" % (fmt_when(start, now), end.strftime("%H:%M"))


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def subject_titles(ws):
    out = {}
    for s in ws.subject_entries():
        sid = s["id"]
        try:
            out[sid] = wsmod.Subject(ws, sid, s.get("dir") or sid).title()
        except (DataError, OSError):
            out[sid] = sid
    return out


def subject_state(ws, sid):
    entry = ws.subject_entry(sid) or {}
    return entry.get("state", "live")


def block_topics(block):
    """Topic ids named by ``cold:<T>`` tokens in a block's content."""
    content = block.get("content")
    if not isinstance(content, str):
        return []
    out = []
    for m in COLD_TOKEN_RE.finditer(content):
        for t in m.group(1).split(","):
            t = t.strip()
            if t and t not in out:
                out.append(t)
    return out


def block_times(block, tz):
    """(start, end) local datetimes; for an obligation, the window (from, to)."""
    s = to_local(block.get("start"), tz)
    e = to_local(block.get("end"), tz)
    if s is None:
        w = block.get("window") or {}
        if isinstance(w, dict):
            return to_local(w.get("from"), tz), to_local(w.get("to"), tz)
    return s, e


def block_minutes(block):
    s, e = dates.try_parse_iso(block.get("start")), dates.try_parse_iso(block.get("end"))
    if s is None or e is None:
        return None
    return int(round((e - s).total_seconds() / 60.0))


def topic_names(subj):
    """{topic id: name} for a subject ({} when the topics cannot be read)."""
    try:
        return dict((t["id"], t.get("name") or t["id"]) for t in subj.topics() if t.get("id"))
    except Exception:
        return {}


def _plain_content(content, names):
    """Content tokens such as ``teach:T03`` become topic names (or nothing): no raw ids for the learner."""
    def sub(m):
        found = [names.get(i) for i in m.group(1).split(",") if i and (names or {}).get(i)]
        return ", ".join(found)
    c = CONTENT_TOKEN_RE.sub(sub, content)
    c = re.sub(r"\s+([,.;:])", r"\1", c)
    c = re.sub(r"([,;:])(?:\s*[,;:])+", r"\1", c)
    return c.strip(" ,;:")


def block_what(block, plain=True, names=None):
    """What a block is, in plain words. A 2-day recheck never names its topics.

    ``names`` ({topic id: name}) turns plan tokens such as ``teach:T03`` into
    topic names in plain vocabulary; without it the tokens are dropped.
    """
    kind = block.get("kind") or "?"
    if kind == "cold":
        return "2-day recheck (mixed)" if plain else "cold (2-day recheck)"
    words = KIND_PLAIN.get(kind, kind) if plain else kind
    content = block.get("content")
    if isinstance(content, str) and content.strip():
        c = COLD_TOKEN_RE.sub("2-day recheck", content)
        if plain:
            c = scrub_ids(_plain_content(c, names or {}))
            if c.lower().startswith(words.lower()):
                c = c[len(words):].strip(" ,;:")
        c = clip(c, 80)
        if c:
            return "%s: %s" % (words, c)
    return words


def is_obligation(block):
    return not block.get("start") and isinstance(block.get("window"), dict)


def session_span(row, tz):
    act = row.get("actual") or {}
    s = to_local(act.get("start"), tz)
    e = to_local(act.get("end"), tz)
    return s, e


def session_lock_state(subj, now):
    """The subject's session lock with parsed times, or None.

    Adds ``_start``, ``_planned_end``, ``_close_start``, ``_planned_min``,
    ``_parked`` and ``_unclosed`` (lock older than planned end + 2 h, or the
    ``.indelible/unclosed`` flag).
    """
    lock = subj.read_session_lock()
    if lock is None:
        return None
    tz = now.tzinfo
    info = dict(lock)
    start = to_local(lock.get("start"), tz)
    if start is None:
        try:
            start = datetime.fromtimestamp(subj.session_lock_path.stat().st_mtime).astimezone(tz)
        except OSError:
            start = now
    try:
        pmin = float(lock.get("planned_min") or 0)
    except (TypeError, ValueError):
        pmin = 0.0
    pend = to_local(lock.get("planned_end"), tz) or (start + timedelta(minutes=pmin))
    cstart = to_local(lock.get("close_start"), tz)
    if cstart is None and pmin:
        cstart = learning.close_start(start, pmin).astimezone(tz)
    parked = subj.unclosed_path.exists()
    info.update({
        "_start": start, "_planned_end": pend, "_close_start": cstart, "_planned_min": pmin,
        "_parked": parked,
        "_unclosed": parked or now > pend + timedelta(hours=UNCLOSED_AFTER_H),
    })
    return info


def _overlaps(a0, a1, b0, b1):
    if None in (a0, a1, b0, b1):
        return False
    return a0 < b1 and b0 < a1


def missed_blocks(ws, subj, blocks, sessions, now, lock=None):
    """Blocks past their end, planned or synced, not soft, with no overlapping session.

    Computed read-only: nothing is written. Empty in on-demand mode.
    """
    if ws.schedule_mode() == "on_demand":
        return []
    tz = now.tzinfo
    spans, sess_blocks = [], set()
    for r in sessions:
        if r.get("block"):
            sess_blocks.add(r["block"])
        spans.append(session_span(r, tz))
    if lock is not None:
        spans.append((lock["_start"], lock["_planned_end"] if lock["_unclosed"] else now))
        if lock.get("block"):
            sess_blocks.add(lock["block"])
    out = []
    for b in blocks:
        if b.get("subject") != subj.id or b.get("status") not in OPEN_BLOCK_STATUSES:
            continue
        if b.get("soft") or not b.get("start") or b.get("kind") == "buffer":
            continue
        s, e = to_local(b.get("start"), tz), to_local(b.get("end"), tz)
        if s is None:
            continue
        if e is None:
            e = s
        if e > now or b.get("id") in sess_blocks:
            continue
        if any(_overlaps(s, e, a, z) for a, z in spans):
            continue
        out.append(b)
    out.sort(key=lambda b: b.get("start") or "")
    return out


# ==========================================================================
# Due
# ==========================================================================

def _err_order(e):
    return (1 if e.get("named_least_sure") else 0, e.get("next_due") or "", e.get("opened") or "", e.get("id") or "")


def due_state(subj, now):
    """What is due now, by tier (a dict; no writes).

    tier 1 ``cold``: topics whose first 2-day recheck is eligible now (only
    topics with teaching on record: ``taught_at``, a ``teach`` exposure, or the
    ``review`` set that confirms a 3p topic; a topic that was only measured or
    only repaired is never recheck material);
    tier 2 ``beliefs``: repaired beliefs due; tier 3 ``shaky``; tier 4
    ``oldest``: every other due error, oldest first; tier 5 ``untreated``:
    beliefs that need repair (never cold material). Within a tier, errors the
    learner had not named on the Least-sure line come first.
    """
    exposures = subj.load_exposures()
    errors = subj.load_errors()
    ts_all = subj.load_topics_state()
    window = subj.cold_window()
    names = {}
    cold = []
    for t in subj.topics():
        names[t["id"]] = t.get("name") or t["id"]
        if t.get("scope") == "out":
            continue
        if not learning.is_first_serve(ts_all.get(t["id"])):
            continue
        if not learning.has_first_serve_basis(t["id"], exposures, ts_all.get(t["id"])):
            continue
        res = learning.cold_eligibility(t["id"], now, exposures, errors, window, first_serve=True)
        if res["eligible"]:
            cold.append({"topic": t["id"], "name": names[t["id"]], "hours": res["hours"]})
    cold.sort(key=lambda c: -(c["hours"] or 0.0))
    today = now.date()
    live = [dict(e) for e in errors if e.get("status") in ("untreated", "spacing", "reopened")]
    due = [e for e in live if learning.is_due(e, today)]
    for e in due:
        res = learning.error_reserve_eligibility(e, now, exposures, errors)
        e["_eligible"] = res["eligible"]
        e["_reason"] = res["reason"]
    beliefs = sorted([e for e in due if e.get("kind") == "belief"], key=_err_order)
    shaky = sorted([e for e in due if e.get("kind") == "shaky"], key=_err_order)
    oldest = sorted([e for e in due if e.get("kind") not in ("belief", "shaky")], key=_err_order)
    untreated = sorted([e for e in live if e.get("status") == "untreated"],
                       key=lambda e: (e.get("opened") or "", e.get("id") or ""))
    slips = [e for e in oldest if e.get("kind") == "slip"]
    return {
        "cold": cold, "beliefs": beliefs, "shaky": shaky, "oldest": oldest, "untreated": untreated,
        "names": names,
        "counts": {"cold": len(cold), "beliefs": len(beliefs), "slips": len(slips), "shaky": len(shaky),
                   "other": len(oldest) - len(slips), "untreated": len(untreated),
                   "errors_due": len(beliefs) + len(shaky) + len(oldest)},
    }


def due_counts_items(st, plain):
    c = st["counts"]
    items = []
    if plain:
        if c["cold"]:
            items.append("2-day rechecks ready now: %d" % c["cold"])
        parts = []
        if c["beliefs"]:
            parts.append("%d fixed" % c["beliefs"])
        if c["slips"]:
            parts.append("%d slip%s" % (c["slips"], "" if c["slips"] == 1 else "s"))
        if c["shaky"]:
            parts.append("%d shaky" % c["shaky"])
        if c["other"]:
            parts.append("%d other" % c["other"])
        if parts:
            items.append("mistakes due: " + ", ".join(parts))
        if c["untreated"]:
            items.append("mistakes to fix before they come back: %d" % c["untreated"])
    else:
        if c["cold"]:
            shown = ["%s (%.0f h)" % (x["topic"], x["hours"] or 0) for x in st["cold"][:6]]
            if len(st["cold"]) > 6:
                shown.append("+%d" % (len(st["cold"]) - 6))
            items.append("cold serves eligible now: " + ", ".join(shown))
        parts = []
        if c["beliefs"]:
            parts.append("%d beliefs repaired" % c["beliefs"])
        if c["slips"]:
            parts.append("%d slip%s" % (c["slips"], "" if c["slips"] == 1 else "s"))
        if c["shaky"]:
            parts.append("%d shaky" % c["shaky"])
        if c["other"]:
            parts.append("%d other" % c["other"])
        if parts:
            items.append("errors due: " + ", ".join(parts))
        if c["untreated"]:
            items.append("untreated beliefs needing repair: %d" % c["untreated"])
    return items


def _err_line(e, names, with_reason=False):
    belief = e.get("belief") or e.get("account") or ""
    line = '%s %s %s' % (e.get("id") or "?", e.get("topic") or "?", names.get(e.get("topic"), ""))
    if e.get("kind") != "belief":
        line += " [%s]" % (e.get("kind") or "?")
    if belief:
        line += ' "%s"' % clip(belief, 90)
    line += " (rung %s" % e.get("rung", 0)
    if e.get("next_due"):
        line += ", due %s" % e["next_due"]
    line += ")"
    if with_reason and e.get("_eligible") is False:
        line += " not now: %s" % e.get("_reason")
    return " ".join(line.split())


# ==========================================================================
# The brief
# ==========================================================================

class Section(object):
    """One brief line (or a head plus indented lines) with a cuttable item list."""

    def __init__(self, head, items=None, sep=" · ", more=None, multiline=False, text=None, claude=False):
        self.head = head
        self.items = [clip(i) for i in (items or [])]
        self.sep = sep
        self.more = more
        self.multiline = multiline
        self.text = text
        self.claude = claude
        self.k = len(self.items)

    def cuttable(self):
        return self.text is None and self.k > 0

    def render(self):
        if self.text is not None:
            return self.text
        parts = list(self.items[: self.k])
        rest = len(self.items) - self.k
        if rest > 0:
            parts.append("+%d more (run: %s)" % (rest, self.more or "due --list"))
        if self.multiline:
            return "\n".join([self.head] + ["  " + p for p in parts])
        return self.head + " " + self.sep.join(parts)


def fit_sections(sections, limit=BRIEF_MAX):
    """Join the sections, cutting the longest lists first until the text fits."""
    rendered = [s.render() for s in sections]

    def total():
        return sum(len(r) for r in rendered) + max(0, len(rendered) - 1)

    while total() > limit:
        cands = [i for i, s in enumerate(sections) if s.cuttable()]
        if not cands:
            break
        i = max(cands, key=lambda j: len(rendered[j]))
        s = sections[i]
        over = total() - limit
        step = 1
        if s.k > 20 and over > 400:
            step = max(1, s.k // 5)
        s.k = max(0, s.k - step)
        rendered[i] = s.render()
    text = "\n".join(rendered)
    if len(text) > limit:
        tail = "\n+more (run: due --list)"
        text = text[: limit - len(tail)].rstrip() + tail
    return text


def claude_md_notes(subj):
    """Learner lines from the subject CLAUDE.md: Learner notes, Do not calibrate on, Overrides (<= 25)."""
    text = fio.read_text(subj.claude_md) or ""
    heads = (("learner notes", "notes"), ("do not calibrate on", "do not calibrate on"), ("overrides", "override"))
    cur = None
    items = []
    in_marked = False
    for raw in text.split("\n"):
        line = raw.strip()
        if line.startswith(wsmod.MARK_BEGIN):
            in_marked = True
            continue
        if line.startswith(wsmod.MARK_END):
            in_marked = False
            continue
        if in_marked:
            continue
        m = re.match(r"^#{1,4}\s+(.*)$", line)
        if m:
            name = m.group(1).strip().lower()
            cur = None
            for key, label in heads:
                if name.startswith(key):
                    cur = label
            continue
        if cur is None or not line or line.startswith("<!--"):
            continue
        if line.startswith("(") and line.endswith(")"):
            continue  # the template's placeholder text
        items.append("[%s] %s" % (cur, line.lstrip("-*• ").strip()))
        if len(items) >= NOTES_MAX_LINES:
            break
    return items


MIXED_LAYER = "mixed sheet"


def measured_pace(subj, sheets=None, attempts=None, last_n=5, labels=None, plans=None):
    """{layer: (mean seconds per question, sheets used)} from timed, graded sheets.

    A sheet's time is known only as a whole, so a sheet whose questions span
    more than one layer is reported under ``"mixed sheet"`` rather than under
    one of its layers. When a dict is passed as ``labels``, it receives
    {layer: "[measured]" or "[practice]"}: "[measured]" only when every sheet
    used was a measuring one. ``plans`` (a dict) receives the planned seconds
    per question for the mixed sheets (weighted by their layers).
    """
    sheets = subj.load_sheets() if sheets is None else sheets
    attempts = subj.load_attempts() if attempts is None else attempts
    layers = {}
    for a in attempts:
        if a.get("sheet") and a.get("layer"):
            d = layers.setdefault(a["sheet"], {})
            d[a["layer"]] = d.get(a["layer"], 0) + 1
    per = {}
    for s in sheets:
        if s.get("status") != "graded":
            continue
        timing = s.get("sat") or {}
        asks = s.get("asks")
        if not isinstance(asks, int) or asks <= 0:
            continue
        try:
            t0, t1 = dates.parse_hhmm(timing.get("start")), dates.parse_hhmm(timing.get("stop"))
        except (ValueError, TypeError):
            continue
        minutes = (t1.hour * 60 + t1.minute) - (t0.hour * 60 + t0.minute)
        if minutes < 0:
            minutes += 24 * 60
        if minutes <= 0:
            continue
        d = layers.get(s.get("id")) or {}
        if not d:
            continue
        if len(d) > 1:
            layer = MIXED_LAYER
            pace_plan = subj.load().get("pace_s") or {}
            total = float(sum(d.values()))
            planned = sum(n * float(pace_plan.get(k) or learning.DEFAULT_PACE_S.get(k) or 90)
                          for k, n in d.items()) / total
        else:
            layer = list(d)[0]
            planned = None
        per.setdefault(layer, []).append((minutes * 60.0 / asks, schema.measures(s.get("type")), planned))
    out = {}
    for layer, vals in per.items():
        vals = vals[-last_n:]
        out[layer] = (int(round(sum(v[0] for v in vals) / len(vals))), len(vals))
        if labels is not None:
            labels[layer] = "[measured]" if all(v[1] for v in vals) else "[practice]"
        if plans is not None and layer == MIXED_LAYER:
            plans[layer] = int(round(sum(v[2] for v in vals) / len(vals)))
    return out


def _session_line(r, tz, plain, now):
    s, _ = session_span(r, tz)
    act = r.get("actual") or {}
    planned = (r.get("planned") or {}).get("min")
    asks = r.get("asks") or {}
    when = fmt_when(s, None) if s else "?"
    parts = []
    if not plain:
        parts.append(r.get("id") or "?")
    parts.append(when)
    if act.get("elapsed_min") is not None:
        parts.append("%s of %s min" % (act.get("elapsed_min"), planned if planned is not None else "?"))
    if asks.get("n"):
        parts.append("%d question%s, %d right" % (asks["n"], "" if asks["n"] == 1 else "s", asks.get("right", 0)))
    st = (r.get("closed") or {}).get("status")
    if st:
        parts.append({"same-day": "closed same day", "late": "closed late",
                      "with-todos": "closed with to-dos"}.get(st, st) if plain else st)
    if r.get("note"):
        parts.append(r["note"])
    line = " · ".join(str(p) for p in parts)
    return scrub_ids(line) if plain else line


def _lock_line(lk, now, plain, sid):
    s = fmt_when(lk["_start"], now)
    if plain:
        return "unclosed session (started %s)" % s
    return "unclosed session %s (started %s)" % (lk.get("session_id") or "?", s)


def brief_sections(ws, subj, now, sheets=None):
    """Build the brief's sections for one subject (no writes)."""
    tz = now.tzinfo
    plain = is_plain(ws)
    cfg = subj.load()
    sid = subj.id
    state = subject_state(ws, sid)
    learner, claude = [], []

    def guard(fn):
        try:
            fn()
        except (DataError, ValueError, TypeError, KeyError, OSError) as exc:
            learner.append(Section("NOTE:", text="NOTE: part of the brief could not be built (%s)" % clip(exc, 120)))

    # ---- header -----------------------------------------------------------
    tgt = cfg.get("target") or {}
    d = subj.target_date()
    if d is None:
        when = "no date"
    else:
        left = (d - now.date()).days
        if left > 1:
            when = "%s (%d days left)" % (d.isoformat(), left)
        elif left == 1:
            when = "%s (1 day left)" % d.isoformat()
        elif left == 0:
            when = "%s (today)" % d.isoformat()
        else:
            when = "%s (date passed)" % d.isoformat()
    header = "%s · %s · %s" % (subj.title(), cfg.get("profile") or "?", when)
    if state == "shadow":
        header = "SHADOW (read-only) · " + header
    elif state == "paused":
        header += " · PAUSED"
    learner.append(Section("", text=header))

    blocks = ws.load_blocks()
    sessions = subj.load_sessions()
    sheets = subj.load_sheets() if sheets is None else sheets
    lock = session_lock_state(subj, now)
    ledger = ws.load_ledger()
    titles = subject_titles(ws)
    names = topic_names(subj)
    for loader in (subj.load_errors, subj.load_exposures, subj.load_attempts):
        try:
            loader()  # read once up front, so any unreadable line is quarantined before FLAGS counts them
        except (DataError, OSError):
            pass

    # ---- FLAGS --------------------------------------------------------------
    flags, cflags = [], []

    def build_flags():
        if lock is not None and lock["_unclosed"]:
            flags.append(_lock_line(lock, now, plain, sid))
            cflags.append(Section("", text=clip(
                "UNCLOSED: %s started %s, planned end %s: close it first: session close %s (it is logged as late)"
                % (lock.get("session_id") or "?", dates.fmt_iso(lock["_start"]),
                   dates.fmt_iso(lock["_planned_end"]), sid), 400)))
        for other in ws.subjects():
            if other.id == sid or subject_state(ws, other.id) in ("legacy", "shadow"):
                continue
            ol = session_lock_state(other, now)
            if ol is None:
                continue
            what = "parked session" if ol["_parked"] else ("unclosed session" if ol["_unclosed"] else "session open")
            flags.append("%s: %s (started %s)" % (titles.get(other.id, other.id), what, fmt_when(ol["_start"], now)))
            cflags.append(Section("", text=clip(
                "OTHER LOCK: %s %s %s: ask whether to close it (session close %s) or park it "
                "(session open %s ... --park-other)" % (other.id, ol.get("session_id") or "?", what, other.id, sid),
                400)))
        missed = missed_blocks(ws, subj, blocks, sessions, now, lock)
        if missed:
            shown = []
            for b in missed:
                s, e = block_times(b, tz)
                shown.append("%s %s" % (fmt_span(s, e, now), block_what(b, plain, names)))
            flags.append("missed? " + "; ".join(shown[:4]) + (" +%d more" % (len(shown) - 4) if len(shown) > 4 else ""))
            cflags.append(Section("MISSED?:", [b.get("id") or "?" for b in missed],
                                  more="plan list --subject %s" % sid))
        unsat = [s for s in sheets if s.get("status") == "issued" and int(s.get("opens_unsat") or 0) >= OPENS_FORCE]
        for s in unsat:
            issued = to_local(s.get("issued_at"), tz)
            ago = (" issued %s" % fmt_day(issued)) if issued else ""
            if s.get("type") == "cold":
                name = "a 2-day recheck"
            else:
                name = "sheet %s (%s)" % (s.get("id"), s.get("type") or "?")
            flags.append("%s%s, not taken after %d opens" % (name, ago, int(s.get("opens_unsat") or 0)))
        if unsat:
            cflags.append(Section("NOT TAKEN (sit now, or sheet void):", [s.get("id") or "?" for s in unsat],
                                  more="sheet show %s --status issued" % sid))
        q = ws.quarantine_count()
        if q:
            flags.append("%d line%s in the record could not be read; kept aside" % (q, "" if q == 1 else "s")
                         if plain else "quarantine: %d unreadable line%s" % (q, "" if q == 1 else "s"))
        for r in ws.open_ledger_items(kind="decision", subject=sid, rows=ledger):
            sg = r.get("safeguard") or {}
            co = sg.get("check_on")
            try:
                if not co or dates.to_date(co) > now.date():
                    continue
            except ValueError:
                continue
            summary = clip(r.get("summary") or "", 80)
            if plain:
                flags.append("a check on an earlier decision is due (%s): %s" % (co, scrub_ids(summary)))
            else:
                flags.append("armed safeguard due %s: %s %s" % (co, r.get("id"), summary))
            cflags.append(Section("", text=clip("SAFEGUARD DUE: %s check_on %s: %s -> %s"
                                                % (r.get("id"), co, sg.get("rule"), sg.get("action")), 300)))

    guard(build_flags)
    if flags:
        learner.append(Section("FLAGS:", [scrub_ids(f) if plain else f for f in flags], sep=" | ",
                               more="brief %s" % sid))
    claude.extend(cflags)

    # ---- NOW/NEXT ------------------------------------------------------------
    nn = []

    def build_now():
        if lock is not None and not lock["_unclosed"]:
            el = int((now - lock["_start"]).total_seconds() // 60)
            nn.append("session open since %s (%d of %d min)" % (lock["_start"].strftime("%H:%M"), el,
                                                                 int(lock["_planned_min"])))
        mine = [b for b in blocks if b.get("subject") == sid and b.get("start")
                and b.get("status") not in ("cancelled", "moved")]
        missed_ids = set(b.get("id") for b in missed_blocks(ws, subj, blocks, sessions, now, lock))
        today = [b for b in mine if to_local(b.get("start"), tz) and to_local(b.get("start"), tz).date() == now.date()]
        today.sort(key=lambda b: to_local(b.get("start"), tz))
        for b in today:
            s, e = block_times(b, tz)
            st = "missed?" if b.get("id") in missed_ids else b.get("status")
            mins = block_minutes(b)
            extra = []
            if mins:
                extra.append("%d min" % mins)
            if st in ("done", "missed?", "missed"):
                extra.append(STATUS_PLAIN.get(st, st) if plain else st)
            item = "today %s–%s %s" % (s.strftime("%H:%M"), e.strftime("%H:%M") if e else "?", block_what(b, plain, names))
            if extra:
                item += " (%s)" % ", ".join(extra)
            if not plain:
                item = "%s %s" % (b.get("id"), item)
            nn.append(item)
        end_today = now.replace(hour=23, minute=59, second=59, microsecond=0)
        future = [b for b in mine if b.get("status") in OPEN_BLOCK_STATUSES
                  and to_local(b.get("start"), tz) and to_local(b.get("start"), tz) > end_today]
        future.sort(key=lambda b: to_local(b.get("start"), tz))
        if future:
            b = future[0]
            s, e = block_times(b, tz)
            mins = block_minutes(b)
            item = "next %s %s%s" % (fmt_span(s, e, now), block_what(b, plain, names), " (%d min)" % mins if mins else "")
            if not plain:
                item = "%s %s" % (b.get("id"), item)
            nn.append(item)
        for b in blocks:
            if b.get("subject") != sid or not is_obligation(b) or b.get("status") not in OPEN_BLOCK_STATUSES:
                continue
            f, t = block_times(b, tz)
            if t is None or t < now:
                continue
            if ws.schedule_mode() == "on_demand":
                item = "2-day recheck open between %s and %s (start a session in that window)" % (
                    fmt_when(f, now), fmt_when(t, now))
            else:
                item = "2-day recheck to book: between %s and %s" % (fmt_when(f, now), fmt_when(t, now))
            if not plain:
                item = "%s %s (%s)" % (b.get("id"), item, ",".join(block_topics(b)))
            nn.append(item)

    guard(build_now)
    if nn:
        learner.append(Section("NOW/NEXT:", nn, more="plan list --subject %s" % sid))

    # ---- DUE -------------------------------------------------------------------
    st_holder = {}

    def build_due():
        st_holder["st"] = due_state(subj, now)

    guard(build_due)
    st = st_holder.get("st")
    if st:
        items = due_counts_items(st, plain)
        if items:
            learner.append(Section("DUE:", items, more="due %s --list" % sid))

    # ---- TO-DO -----------------------------------------------------------------
    todo, todo_ids = [], []

    def build_todo():
        rows = []
        for r in ws.open_ledger_items(kind="owed", subject=sid, rows=ledger):
            due = to_local(r.get("due"), tz)
            if due is None or due > now + timedelta(days=TODO_DAYS):
                continue
            rows.append((due, r))
        rows.sort(key=lambda x: x[0])
        for due, r in rows:
            what = clip(r.get("what") or "", 120)
            if due < now:
                when = "overdue: was due %s" % fmt_when(due, now)
            else:
                when = "due %s" % fmt_when(due, now)
            mine = " (mine)" if r.get("by") == "claude" else ""
            if plain:
                todo.append("%s%s (%s)" % (scrub_ids(what), mine, when))
            else:
                todo.append("%s %s%s (%s)" % (r.get("id"), what, mine, when))
            refs = r.get("refs") or []
            todo_ids.append("%s%s" % (r.get("id"), (" [" + ", ".join(str(x) for x in refs) + "]") if refs else ""))

    guard(build_todo)
    if todo:
        learner.append(Section("TO-DO (next %d days):" % TODO_DAYS if plain else "TO-DO (≤%d days):" % TODO_DAYS,
                               todo, more="ledger list --open --subject %s" % sid))
    if todo_ids and plain:
        claude.append(Section("TO-DO IDS:", todo_ids, more="ledger list --open --subject %s" % sid))

    # ---- LEVELS ----------------------------------------------------------------
    lv = []

    def build_levels():
        ts_all = subj.load_topics_state()
        for t in subj.topics():
            if t.get("scope") == "out":
                continue
            level = (ts_all.get(t["id"]) or {}).get("level", 0)
            if plain:
                shown = "3 (to confirm)" if str(level) in ("3p", "3P") else str(level)
                lv.append("%s %s" % (t.get("name") or t["id"], shown))
            else:
                lv.append("%s %s %s" % (t["id"], t.get("name") or "", level))

    guard(build_levels)
    if lv:
        learner.append(Section("MASTERY (0–5):" if plain else "LEVELS:", lv, more="topic show %s" % sid))

    # ---- LAST SESSIONS ---------------------------------------------------------
    last = sessions[-LAST_SESSIONS:]
    if last:
        head = "LAST SESSIONS:"
        _, e = session_span(last[-1], tz)
        if e is not None:
            gap = (now.date() - e.date()).days
            if gap >= REENTRY_GAP_DAYS:
                head = "LAST SESSIONS (%d days since the last one):" % gap
        learner.append(Section(head, [_session_line(r, tz, plain, now) for r in reversed(last)],
                               multiline=True, more="log: %s/views/log.md" % subj.dirname))

    # ---- PACE ------------------------------------------------------------------
    pace = []

    def build_pace():
        plan = cfg.get("pace_s") or {}
        labels, mixed_plans = {}, {}
        for layer, (secs, n) in sorted(measured_pace(subj, sheets=sheets, labels=labels, plans=mixed_plans).items()):
            p = plan.get(layer) or learning.DEFAULT_PACE_S.get(layer) or mixed_plans.get(layer)
            label = labels.get(layer, "[practice]")
            if plain:
                pace.append("%s about %d s per question (%d sheet%s; plan %s s) %s"
                            % (layer, secs, n, "" if n == 1 else "s", p, label))
            else:
                pace.append("%s %d s/question [%s, %d sheets; plan %s]" % (layer, secs, label.strip("[]"), n, p))

    guard(build_pace)
    if pace:
        learner.append(Section("PACE:", pace, more="stats %s" % sid))

    # ---- NOTES -----------------------------------------------------------------
    notes = []

    def build_notes():
        notes.extend(claude_md_notes(subj))

    guard(build_notes)
    if notes:
        learner.append(Section("NOTES:", [scrub_ids(n) if plain else n for n in notes], multiline=True,
                               more="see %s/CLAUDE.md" % subj.dirname))

    # ---- Claude section --------------------------------------------------------------
    claude.insert(0, Section("", text="SUBJECT: %s · vocab %s · schedule %s · state %s" % (
        sid, vocab_of(ws), ws.schedule_mode(), state)))
    try:
        tz_warn = dates.zone_problem(ws.timezone())
    except (DataError, OSError):
        tz_warn = None
    if tz_warn:
        claude.insert(1, Section("", text=clip("TIME ZONE: " + tz_warn, 300)))
    if st:
        if st["cold"]:
            claude.append(Section("RECHECK NOW:", ["%s %s (%.0f h)" % (c["topic"], c["name"], c["hours"] or 0)
                                                   for c in st["cold"]], more="due %s --list" % sid))
        if st["beliefs"]:
            claude.append(Section("BELIEFS DUE:", [_err_line(e, st["names"]) for e in st["beliefs"]],
                                  more="due %s --list" % sid))
        other = st["shaky"] + st["oldest"]
        if other:
            claude.append(Section("OTHER DUE:", [_err_line(e, st["names"]) for e in other],
                                  more="due %s --list" % sid))
        if st["untreated"]:
            claude.append(Section("NEEDS REPAIR:", [_err_line(e, st["names"]) for e in st["untreated"]],
                                  more="due %s --list" % sid))
    ovr = []
    for o in cfg.get("overrides") or []:
        if isinstance(o, dict):
            ovr.append("%s = %s%s%s" % (o.get("rule") or "?", o.get("value") or "?",
                                        " (locked)" if o.get("locked") else "",
                                        (' "%s"' % clip(o.get("why"), 80)) if o.get("why") else ""))
    if ovr:
        claude.append(Section("OVERRIDES:", ovr, more="see %s/subject.json" % subj.dirname))
    return learner, claude


def build_brief(ws, subj, now=None):
    """The brief text for one subject (read-only)."""
    now = now or now_in(ws)
    learner, claude = brief_sections(ws, subj, now)
    sections = learner + [Section("", text=CLAUDE_SEP)] + claude
    return fit_sections(sections)


def build_overview(ws, subjects, now):
    """A short brief across several live subjects (no counting, no writes)."""
    sections = [Section("", text="Subjects: %s. For one subject's full brief run: brief <subject>."
                        % ", ".join(s.id for s in subjects))]
    claude = []
    for subj in subjects:
        try:
            learner, cl = brief_sections(ws, subj, now)
        except (DataError, OSError) as exc:
            sections.append(Section("", text="%s: could not be read (%s)" % (subj.id, clip(exc, 100))))
            continue
        keep = [s for s in learner if s.text is not None or s.head in ("FLAGS:", "NOW/NEXT:", "DUE:")
                or s.head.startswith("TO-DO")]
        sections.extend(keep)
        for s in cl:
            if s.text is not None:
                if s.text.startswith(("UNCLOSED", "OTHER", "SAFEGUARD")):
                    claude.append(s)
            elif s.head in ("MISSED?:", "TO-DO IDS:") or s.head.startswith("NOT TAKEN"):
                s.head = "%s %s" % (subj.id, s.head)
                claude.append(s)
    claude.insert(0, Section("", text="SUBJECTS: " + " · ".join(s.id for s in subjects)))
    return fit_sections(sections + [Section("", text=CLAUDE_SEP)] + claude)


def _opens_state_path(subj):
    return subj.state_dir / "opens.json"


def count_open(ws, subj, now):
    """Increment opens_unsat on issued, unsat sheets (at most once per 3 h per subject).

    Returns the number of sheets incremented. Not counted while this subject's
    session is running.
    """
    lock = session_lock_state(subj, now)
    if lock is not None and not lock["_unclosed"]:
        return 0
    try:
        state = fio.read_json(_opens_state_path(subj), default={}) or {}
    except DataError:
        state = {}
    last = dates.try_parse_iso(state.get("last_counted")) if isinstance(state, dict) else None
    if last is not None and abs((now - last).total_seconds()) < OPEN_DEDUPE_H * 3600:
        return 0
    rows = subj.load_sheets()
    # A sheet issued ahead for a block that has not started yet (close.md builds
    # the next block's sheets at the close) is not "not taken" until that block.
    starts = {}
    try:
        for b in ws.load_blocks():
            starts[b.get("id")] = dates.try_parse_iso(b.get("start"))
    except (DataError, OSError):
        pass
    n = 0
    for s in rows:
        if s.get("status") == "issued":
            start = starts.get(s.get("block")) if s.get("block") else None
            if start is not None and start > now:
                continue
            s["opens_unsat"] = int(s.get("opens_unsat") or 0) + 1
            n += 1
    if n:
        subj.save_sheets(rows)
    fio.write_json(_opens_state_path(subj), {"v": 1, "last_counted": dates.fmt_iso(now)}, backup=False)
    return n


def _pick_subject(ws, arg):
    """(subject or None, live subjects) for brief/due: an argument, the cwd, or the only live subject."""
    if arg:
        return ws.subject(arg), None
    subj = ws.subject_from_cwd()
    if subj is not None:
        return subj, None
    live = ws.subjects("live")
    if len(live) == 1:
        return live[0], None
    return None, live


def cmd_brief(args):
    ws = wsmod.from_args(args)
    now = now_in(ws)
    subj, live = _pick_subject(ws, args.subject)
    if subj is None:
        if not live:
            text = ("No live subjects yet. Run: indelible.py subject add <id> --title <title> --profile <profile>")
        else:
            text = build_overview(ws, live, now)
        if args.json:
            _out(json.dumps({"subject": None, "text": text, "chars": len(text)}, ensure_ascii=False))
        else:
            _out(text)
        return 0
    state = subject_state(ws, subj.id)
    if state == "legacy":
        text = ("%s · legacy: this subject is run by its own CLAUDE.md (%s/CLAUDE.md). "
                "indelible reads and writes nothing for it." % (subj.title(), subj.dirname))
        _out(json.dumps({"subject": subj.id, "text": text, "chars": len(text)}, ensure_ascii=False)
             if args.json else text)
        return 0
    counted = 0
    if state != "shadow":
        try:
            with ws.lock():
                counted = count_open(ws, subj, now)
        except LockBusy:
            counted = 0
    text = build_brief(ws, subj, now)
    if args.json:
        _out(json.dumps({"subject": subj.id, "vocab": vocab_of(ws), "text": text, "chars": len(text),
                         "opens_counted": counted}, ensure_ascii=False))
    else:
        _out(text)
    return 0


# ==========================================================================
# due
# ==========================================================================

def cmd_due(args):
    ws = wsmod.from_args(args)
    subj = ws.resolve_subject(args.subject)
    now = now_in(ws)
    st = due_state(subj, now)
    plain = is_plain(ws)
    window = subj.cold_window()
    if args.json:
        def err(e):
            return {"id": e.get("id"), "topic": e.get("topic"), "kind": e.get("kind"), "rung": e.get("rung"),
                    "next_due": e.get("next_due"), "named_least_sure": bool(e.get("named_least_sure")),
                    "eligible_now": e.get("_eligible", False), "reason": e.get("_reason")}
        out = {"subject": subj.id, "now": dates.fmt_iso(now), "counts": st["counts"],
               "tiers": {"1_cold": [{"topic": c["topic"], "name": c["name"], "hours": round(c["hours"] or 0, 1)}
                                    for c in st["cold"]],
                         "2_repaired_beliefs": [err(e) for e in st["beliefs"]],
                         "3_shaky": [err(e) for e in st["shaky"]],
                         "4_oldest": [err(e) for e in st["oldest"]],
                         "5_needs_repair": [err(e) for e in st["untreated"]]}}
        _out(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    head = "%s · due at %s" % (subj.title(), fmt_when(now))
    if not args.list:
        items = due_counts_items(st, plain)
        _out(head)
        _out(" · ".join(items) if items else "Nothing due now.")
        return 0
    _out(head + " (for Claude: do not read this list aloud)")
    names = st["names"]
    _out("1. 2-day rechecks in their window (%d–%d h after the last exposure):" % (window[0], window[1]))
    for c in st["cold"] or []:
        _out("   %s %s · %.0f h since last seen" % (c["topic"], c["name"], c["hours"] or 0))
    if not st["cold"]:
        _out("   none")
    for n, key, title in ((2, "beliefs", "fixed mistakes due"), (3, "shaky", "shaky answers due"),
                          (4, "oldest", "oldest due")):
        _out("%d. %s:" % (n, title))
        rows = st[key]
        for e in rows:
            _out("   " + _err_line(e, names, with_reason=True))
        if not rows:
            _out("   none")
    _out("5. needs repair (never on a 2-day recheck):")
    for e in st["untreated"]:
        _out("   " + _err_line(e, names))
    if not st["untreated"]:
        _out("   none")
    return 0


# ==========================================================================
# Views
# ==========================================================================

BANNER = wsmod.GENERATED_BANNER


def _progress_view(ws, subj, now):
    plain = is_plain(ws)
    cfg = subj.load()
    ts_all = subj.load_topics_state()
    tz = now.tzinfo
    lines = [BANNER, "# %s: progress" % subj.title(), ""]
    tgt = cfg.get("target") or {}
    lines.append("Goal: %s · date %s · updated %s" % (tgt.get("goal") or "(not set)", tgt.get("date") or "none",
                                                    fmt_when(now)))
    lines.append("")
    col = "Mastery (0–5)" if plain else "Level"
    lines.append("| Topic | %s | Basis | Taught | Last 2-day recheck |" % col)
    lines.append("|---|---|---|---|---|")
    for t in subj.topics():
        if t.get("scope") == "out":
            continue
        st = ts_all.get(t["id"]) or {}
        taught = to_local(st.get("taught_at"), tz)
        lastc = to_local(st.get("last_cold"), tz)
        name = t.get("name") or t["id"]
        if not plain:
            name = "%s %s" % (t["id"], name)
        basis = clip(st.get("level_basis") or "no evidence yet", 90).replace("|", "/")
        lines.append("| %s | %s | %s | %s | %s |" % (name.replace("|", "/"), st.get("level", 0), basis,
                                                    fmt_day(taught) if taught else "—",
                                                    fmt_day(lastc) if lastc else "—"))
    lines.append("")
    acc = learning.accuracy_by_instrument(subj.load_attempts())
    if acc:
        lines.append("Scores by instrument (never combined into one line):")
        for inst, r in acc.items():
            label = "measured" if inst != "practice" else "practice"
            name = INSTRUMENT_PLAIN.get(inst, inst) if plain else inst
            if r["value"] is not None:
                lines.append("- %s: %d%% of %d questions [%s]" % (name, int(round(r["value"] * 100)), r["n"], label))
        lines.append("")
    lines.append("Mastery: 2 = practice at 75% or more; 3 = passed a 2-day recheck; 4 = passed a second one a week "
                 "later; 5 = held in a mock or checkpoint." if plain else
                 "Levels: 2 practice >=75%; 3p measurement >=75% (4+ asks); 3 cold pass in window; 4 second cold "
                 "pass >=7 d later; 5 mock/checkpoint after 4.")
    return "\n".join(lines) + "\n"


def _errors_view(ws, subj, now):
    plain = is_plain(ws)
    errors = subj.load_errors()
    names = {t["id"]: t.get("name") or t["id"] for t in subj.topics()}
    live = [e for e in errors if e.get("status") != "retired"]
    retired = len(errors) - len(live)
    today = now.date()
    due = [e for e in live if learning.is_due(e, today)]
    untreated = [e for e in live if e.get("status") == "untreated"]
    lines = [BANNER, "# %s: mistakes" % subj.title(), ""]
    lines.append("Open: %d · due now: %d · to fix before they come back: %d · done: %d"
                 % (len(live), len(due), len(untreated), retired))
    lines.append("")
    if plain:
        lines.append("| # | Topic | Kind | Status | Comes back | What went wrong |")
    else:
        lines.append("| Id | Topic | Kind | Status | Next due | Belief |")
    lines.append("|---|---|---|---|---|---|")
    live.sort(key=lambda e: (e.get("next_due") or "9999", e.get("id") or ""))
    for i, e in enumerate(live, 1):
        belief = clip(e.get("belief") or "", 100).replace("|", "/")
        if plain:
            back = "after fixing" if e.get("status") == "untreated" else (e.get("next_due") or "—")
            lines.append("| %d | %s | %s | %s | %s | %s |" % (
                i, names.get(e.get("topic"), e.get("topic") or "?"), ERROR_KIND_PLAIN.get(e.get("kind"), e.get("kind")),
                ERROR_STATUS_PLAIN.get(e.get("status"), e.get("status")), back, scrub_ids(belief)))
        else:
            lines.append("| %s | %s | %s | %s | %s | %s |" % (
                e.get("id"), e.get("topic"), e.get("kind"), e.get("status"), e.get("next_due") or "—", belief))
    return "\n".join(lines) + "\n"


def _log_view(ws, subj, now):
    plain = is_plain(ws)
    tz = now.tzinfo
    rows = subj.load_sessions()[-LOG_MAX:]
    lines = [BANNER, "# %s: log (last %d sessions, newest first)" % (subj.title(), LOG_MAX), ""]
    for r in reversed(rows):
        lines.append(clip("- " + _session_line(r, tz, plain, now), LOG_LINE_MAX))
    if not rows:
        lines.append("(no sessions yet)")
    return "\n".join(lines) + "\n"


def _subject_section(ws, subj, now):
    """The generated section of the subject CLAUDE.md (<= 12 lines, no ids in plain mode)."""
    plain = is_plain(ws)
    tz = now.tzinfo
    ts_all = subj.load_topics_state()
    lines = []
    lv, gaps = [], []
    for t in subj.topics():
        if t.get("scope") == "out":
            continue
        level = (ts_all.get(t["id"]) or {}).get("level", 0)
        name = t.get("name") or t["id"]
        lv.append("%s %s" % (name if plain else "%s %s" % (t["id"], name), level))
        if learning.level_rank(level) < 2:
            gaps.append(name)
    lines.append(clip(("Mastery (0–5): " if plain else "Levels: ") + (" · ".join(lv) or "no topics yet"), 400))
    if gaps:
        lines.append(clip("Gaps (mastery 0–1): " + ", ".join(gaps), 300))
    blocks = [b for b in ws.load_blocks() if b.get("subject") == subj.id and b.get("start")
              and b.get("status") in OPEN_BLOCK_STATUSES and to_local(b.get("start"), tz)
              and to_local(b.get("start"), tz) >= now]
    blocks.sort(key=lambda b: to_local(b.get("start"), tz))
    if blocks:
        lines.append("Next blocks:")
        for b in blocks[:5]:
            s, e = block_times(b, tz)
            mins = block_minutes(b)
            lines.append(clip("- %s %s%s" % (fmt_span(s, e), block_what(b, plain, topic_names(subj)), " (%d min)" % mins if mins else ""),
                              160))
    else:
        lines.append("Next blocks: none planned")
    for r in ws.open_ledger_items(kind="decision", subject=subj.id):
        sg = r.get("safeguard") or {}
        if sg.get("check_on"):
            txt = "Safeguard: %s (check on %s: %s)" % (clip(r.get("summary") or "", 80), sg.get("check_on"),
                                                     clip(sg.get("rule") or "", 60))
            lines.append(clip(scrub_ids(txt) if plain else "%s %s" % (r.get("id"), txt), 200))
            if len(lines) >= 11:
                break
    lines.append("Updated %s by indelible.py render. Read nothing else at open: run brief." % fmt_when(now))
    return "\n".join(l.replace("$", "") for l in lines[:12])


def week_text(ws, start=None, now=None):
    """The Mon–Sun table of every subject's blocks (text; no writes)."""
    now = now or now_in(ws)
    tz = now.tzinfo
    plain = is_plain(ws)
    monday = dates.week_start(dates.to_date(start) if start else now.date())
    week_days = [monday + timedelta(days=i) for i in range(7)]
    t0 = datetime(monday.year, monday.month, monday.day, tzinfo=tz)
    t1 = t0 + timedelta(days=7)
    titles = subject_titles(ws)
    names_by = dict((x.id, topic_names(x)) for x in ws.subjects())
    blocks = ws.load_blocks()
    sessions = {}
    for s in ws.subjects():
        try:
            sessions[s.id] = s.load_sessions()
        except (DataError, OSError):
            sessions[s.id] = []
    missed = set()
    for s in ws.subjects():
        try:
            lk = session_lock_state(s, now)
        except (DataError, OSError):
            lk = None
        for b in missed_blocks(ws, s, blocks, sessions.get(s.id, []), now, lk):
            missed.add(b.get("id"))
    timed = []
    for b in blocks:
        if not b.get("start") or b.get("status") == "cancelled":
            continue
        s, e = block_times(b, tz)
        if s is None or not (t0 <= s < t1):
            continue
        timed.append((s, e or s, b))
    timed.sort(key=lambda x: x[0])
    clash = set()
    for i in range(len(timed)):
        for j in range(i + 1, len(timed)):
            a, b = timed[i], timed[j]
            if b[0] >= a[1]:
                continue
            if _overlaps(a[0], a[1], b[0], b[1]):
                clash.add(a[2].get("id"))
                clash.add(b[2].get("id"))
    lines = [BANNER, "# Week %s (%s – %s)" % (dates.iso_week(monday), fmt_day(week_days[0]), fmt_day(week_days[-1])), ""]
    if plain:
        lines.append("| Day | Time | Subject | What | Min | Status |")
        lines.append("|---|---|---|---|---|---|")
    else:
        lines.append("| Day | Time | Subject | What | Min | Status | Block |")
        lines.append("|---|---|---|---|---|---|---|")
    minutes = {}
    for d in week_days:
        rows = [x for x in timed if x[0].date() == d]
        if not rows:
            lines.append("| %s | — |  |  |  |  |%s" % (fmt_day(d), "" if plain else "  |"))
            continue
        for s, e, b in rows:
            st = "missed?" if b.get("id") in missed else (b.get("status") or "?")
            status = STATUS_PLAIN.get(st, st) if plain else st
            if b.get("id") in clash:
                status += " · CLASH"
            mins = block_minutes(b)
            if mins and b.get("status") != "cancelled":
                minutes[b.get("subject")] = minutes.get(b.get("subject"), 0) + mins
            row = "| %s | %s–%s | %s | %s | %s | %s |" % (
                fmt_day(d), s.strftime("%H:%M"), e.strftime("%H:%M"), titles.get(b.get("subject"), b.get("subject")),
                block_what(b, plain, names_by.get(b.get("subject"))).replace("|", "/"), mins if mins is not None else "", status)
            if not plain:
                row += " %s |" % b.get("id")
            lines.append(row)
    lines.append("")
    lines.append("Clashes: %s" % ("none" if not clash else "%d blocks overlap (marked CLASH)" % len(clash)))
    obl = []
    for b in blocks:
        if not is_obligation(b) or b.get("status") not in OPEN_BLOCK_STATUSES:
            continue
        f, t = block_times(b, tz)
        if f is None or t is None or t < t0 or f >= t1:
            continue
        item = "- %s: 2-day recheck, between %s and %s" % (titles.get(b.get("subject"), b.get("subject")),
                                                           fmt_when(f), fmt_when(t))
        if not plain:
            item += " (%s)" % b.get("id")
        obl.append(item)
    on_demand = ws.schedule_mode() == "on_demand"
    if obl:
        lines.append("")
        lines.append("2-day rechecks open (start a session inside the window; nothing to book):" if on_demand
                     else "2-day rechecks still to book:")
        lines.extend(obl)
    try:
        cfg = ws.load_config()
    except DataError:
        cfg = {}
    tm = cfg.get("time") or {}
    parts = []
    for s in ws.subject_entries():
        if s["id"] in minutes or (s.get("target_weekly_min") and not on_demand):
            tgt = None if on_demand else s.get("target_weekly_min")
            parts.append("%s %d%s" % (titles.get(s["id"], s["id"]), minutes.get(s["id"], 0),
                                      " (target %s)" % tgt if tgt else ""))
    total = sum(minutes.values())
    if on_demand:
        # An on-demand learner books nothing, so there is no target to fall short of.
        if total:
            lines.append("")
            lines.append("Minutes booked: %s · total %d" % (" · ".join(parts), total))
    else:
        lines.append("")
        lines.append("Minutes planned: %s · total %d%s" % (" · ".join(parts) if parts else "none",
                                                           total, " of %s ceiling" % tm.get("weekly_ceiling_min")
                                                           if tm.get("weekly_ceiling_min") else ""))
    return "\n".join(lines) + "\n"


# ---- render machinery -----------------------------------------------------------

class Target(object):
    def __init__(self, key, path, mode, content):
        self.key = key          # key in render.json (workspace-relative)
        self.path = path
        self.mode = mode        # "file" or "section"
        self.content = content if mode == "section" else (content if content.endswith("\n") else content + "\n")

    def new_sha(self):
        return sha(self.content.strip("\n") if self.mode == "section" else self.content)


def renderable(ws, subj):
    return subject_state(ws, subj.id) in ("live", "paused")


def _subject_targets(ws, subj, now):
    out = []
    rel = lambda p: ws.rel(p)  # noqa: E731
    views = {
        "brief.md": BANNER + "\n" + build_brief(ws, subj, now) + "\n",
        "progress.md": _progress_view(ws, subj, now),
        "errors.md": _errors_view(ws, subj, now),
        "log.md": _log_view(ws, subj, now),
    }
    for name, text in views.items():
        p = subj.view_path(name)
        out.append(Target(rel(p), p, "file", text))
    if subj.claude_md.exists():
        out.append(Target(rel(subj.claude_md) + "#generated", subj.claude_md, "section", _subject_section(ws, subj, now)))
    return out


def _root_targets(ws, now, week_start=None):
    out = [Target("views/week.md", ws.week_view_path, "file", week_text(ws, week_start, now))]
    if ws.claude_md.exists():
        out.append(Target("CLAUDE.md#generated", ws.claude_md, "section", wsmod.root_subjects_section(ws)))
    return out


def _current(target):
    text = fio.read_text(target.path)
    if text is None:
        return None
    if target.mode == "section":
        return wsmod.marked_section(text)
    return text


def _edited(target, state):
    rec = (state.get("files") or {}).get(target.key)
    if not rec:
        return False  # never rendered: never refused
    cur = _current(target)
    if cur is None:
        return False if target.mode == "file" else (target.path.exists())
    got = sha(cur.strip("\n") if target.mode == "section" else cur)
    return got != rec.get("sha")


def _diff(target, limit=12):
    cur = _current(target) or ""
    new = target.content.strip("\n") if target.mode == "section" else target.content
    d = list(difflib.unified_diff(new.splitlines(), cur.splitlines(), "rendered", "on disk", n=0, lineterm=""))
    d = [l for l in d if not l.startswith(("---", "+++"))]
    if len(d) > limit:
        d = d[:limit] + ["... (%d more diff lines)" % (len(d) - limit)]
    return d


def collect_targets(ws, subjects, now=None, include_root=True, week_start=None):
    now = now or now_in(ws)
    out = []
    for s in subjects:
        if renderable(ws, s):
            out.extend(_subject_targets(ws, s, now))
    if include_root:
        out.extend(_root_targets(ws, now, week_start))
    return out


def hand_edits(ws, subjects, include_root=True, targets=None):
    """Workspace-relative keys of generated files edited by hand since the last render."""
    targets = collect_targets(ws, subjects, include_root=include_root) if targets is None else targets
    state = ws.load_render_state()
    return [t.key for t in targets if _edited(t, state)]


def apply_targets(ws, targets, force=False, skip_edited=False):
    """Write the targets. Returns {"written", "unchanged", "skipped", "backups"}.

    Raises CheckFailed listing the hand-edited files unless force or skip_edited.
    """
    now = now_in(ws)
    with ws.lock():
        state = ws.load_render_state()
        files = state.setdefault("files", {})
        edited = [t for t in targets if _edited(t, state)]
        if edited and not force and not skip_edited:
            lines = ["Refused: edited by hand since the last render (views are generated; nothing was written):"]
            for t in edited:
                lines.append("  %s" % t.key)
                lines.extend("    " + l for l in _diff(t))
            lines.append("Turn the edit into CLI calls (set, ledger add, note append), or overwrite with "
                         "render --force (a .bak copy is kept).")
            raise CheckFailed("\n".join(lines))
        edited_keys = set(t.key for t in edited)
        res = {"written": [], "unchanged": [], "skipped": [], "backups": []}
        for t in targets:
            if t.key in edited_keys and not force:
                res["skipped"].append(t.key)
                continue
            backup = t.key in edited_keys
            if t.mode == "section":
                text = fio.read_text(t.path)
                if text is None:
                    continue
                new = wsmod.replace_marked_section(text, t.content)
                if new != text or backup:
                    fio.write_text(t.path, new, backup=backup)
                    res["written"].append(t.key)
                else:
                    res["unchanged"].append(t.key)
            else:
                cur = fio.read_text(t.path)
                if cur == t.content and not backup:
                    res["unchanged"].append(t.key)
                else:
                    fio.write_text(t.path, t.content, backup=backup and cur is not None)
                    res["written"].append(t.key)
            if backup:
                res["backups"].append(t.key.split("#")[0] + ".bak")
            files[t.key] = {"sha": t.new_sha(), "at": dates.fmt_iso(now)}
        state["v"] = 1
        ws.save_render_state(state)
    return res


def render_subjects(ws, subjects, force=False, skip_edited=False, include_root=True, week_start=None):
    targets = collect_targets(ws, subjects, include_root=include_root, week_start=week_start)
    return apply_targets(ws, targets, force=force, skip_edited=skip_edited)


def render_week(ws, start=None, force=False, write=True):
    """Build views/week.md (Mon–Sun, every subject), write it unless write=False, return the text.

    Refuses (CheckFailed) if the file was edited by hand since the last render,
    unless force.
    """
    now = now_in(ws)
    text = week_text(ws, start, now)
    if write:
        apply_targets(ws, [Target("views/week.md", ws.week_view_path, "file", text)], force=force)
    return text


def cmd_render(args):
    ws = wsmod.from_args(args)
    target = args.target
    if target in (None, "all"):
        subjects = [s for s in ws.subjects() if renderable(ws, s)]
    else:
        subj = ws.subject(target)
        st = subject_state(ws, subj.id)
        if st in ("legacy", "shadow"):
            raise CheckFailed("Refused: %s is %s, so indelible writes nothing in its folder." % (subj.id, st))
        subjects = [subj]
    res = render_subjects(ws, subjects, force=args.force)
    _out("Views rendered: %d written, %d unchanged%s." % (
        len(res["written"]), len(res["unchanged"]),
        (", %d kept as is" % len(res["skipped"])) if res["skipped"] else ""))
    for b in res["backups"]:
        _out("  Your edited copy was kept: %s" % b)
    return 0
