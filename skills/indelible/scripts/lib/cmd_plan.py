"""Plan blocks, their checks, and calendar operations (contract section 7.6).

    plan add <subject> --kind K --start ISO --min N [--protected] [--measurement] [--soft]
             [--content TEXT] [--pair B-...]
    plan add <subject> --kind cold --content cold:<T> [--pair B-...] [--window-from ISO --window-to ISO]
             (no --start: an obligation, a recheck with a window and no time yet)
    plan place <block-id> --start ISO --min N
    plan move <block-id> --start ISO [--min N]
    plan cancel <block-id> --reason TEXT
    plan done <block-id>
    plan miss <block-id> --reason TEXT
    plan list [--subject S] [--from DATE] [--to DATE] [--json]
    plan week [--start DATE] [--force]
    plan check [--json]
    plan diff [--subject S] [--json]
    cal ack --from results.json
    cal ics <out.ics> [--from DATE] [--to DATE] [--subject S] [--ops all|create]

``plan/blocks.jsonl`` is a snapshot holding every subject's blocks. Claude
proposes blocks, these commands store them, and ``plan check`` validates the
future ones. There is no solver in v0.1.

Recheck (``kind: cold``) windows come from, in order:
  1. the block's own ``window`` (an obligation made by ``session taught``,
     or one placed with ``plan place``);
  2. its ``pair`` block, while that block is not done: from the pair's end
     + cold_window_h[0] to the pair's start + cold_window_h[1], so the
     recheck is valid whenever inside the pair the teaching happens;
  3. the last recorded warm exposure of its ``cold:<T>`` topics, while the
     topic has not been served cold since it was taught.

Moving a block moves the rechecks paired to it by the same amount. A window
derived from a planned pair is stored with ``"basis": "pair"`` and moves
with it; a window from a real teaching time never moves.

Which topics a planned block warms up (for the 24-hour rule and the
confusable-topics warning): ``teach:<T>``, ``repair:<T>``, ``review:<T>``,
``drill:<T>`` or ``chat:<T>`` in its content, plus the ``cold:<T>`` topics
of the rechecks paired to it. Hours are elapsed hours, so windows stay right
across a clock change.

Fields this module adds to a block record: ``moves`` (the ics SEQUENCE),
``cancel_reason`` and ``cancelled_at``, ``misses`` (every ``plan miss``:
``{at, slot, reason}``; a missed block that is rebooked with ``plan move``
keeps its history and still counts as missed); in ``cal``, ``end`` (the end
at the last ack) and ``cancelled`` (the calendar item was marked cancelled,
so the diff stops offering the cancel).

Calendar fallback: when the configured provider (e.g. google) could not be
written and the blocks went out as an ``.ics`` file instead, they are acked
with ``provider: ics`` and the configured provider stays as it is. Once that
provider works again, ``plan diff`` offers every future block whose ``cal``
belongs to another provider as a ``create`` for it (the takeover). ``cal ics
--ops create`` exports only the blocks the diff would create, so a file never
re-sends a moved event that an import cannot update.

Calendar titles and notes never name a topic. ``plan diff`` writes them;
``cal ack`` records what the calendar holds; ``cal ics`` exports a file.
Nothing here prints an answer or a key.
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from lib import CheckFailed, DataError, UsageError, VERSION, SKILL_DIR
from lib import dates, learning, schema
from lib import ics
from lib import io as fio
from lib import ws as wsmod

# Statuses
OPEN = ("planned", "synced")
LIVE = ("planned", "synced", "missed?", "moved")      # still in the plan
OCCUPY = LIVE + ("done",)                              # uses the time slot
MOVABLE = ("planned", "synced", "missed?", "missed", "moved")

MEASURE_KINDS = ("mock", "diagnostic", "checkpoint")
WARM_VERBS = ("teach", "repair", "review", "drill", "chat")

BEDTIME_GAP_MIN = 30
MEASURE_GAP_H = 3.0
NO_EXPOSURE_H = 24.0
OBLIGATION_DUE_H = 24.0
NOTES_MAX = 600
CONTENT_MAX = 200
REASON_MAX = 200
DEFAULT_RECHECK_MIN = 20
DEFAULT_REMINDER_MIN = 15
MAX_BLOCK_MIN = 720

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

TOKEN_RE = re.compile(r"\b(cold|teach|repair|review|drill|chat):([A-Za-z0-9_-]+(?:,[A-Za-z0-9_-]+)*)")
RECHECK_WORD_RE = re.compile(r"\brecheck|\bcold:", re.I)
HAS_TIME_RE = re.compile(r"\d[T t]\d")

KIND_WORDS = {
    "teach": "new skill", "cold": "2-day recheck (mixed)", "repair": "fix mistakes", "review": "review",
    "mixed": "mixed practice", "mock": "mock test", "diagnostic": "diagnostic test",
    "checkpoint": "checkpoint test", "words": "words practice", "oral": "speaking practice",
    "project": "project work", "long": "long session", "tutor_lesson": "tutor lesson",
    "buffer": "spare time", "admin": "planning and admin",
}

_DESK = "Clear the desk: notes and books closed."
_PHOTO = "Photograph or type your answers for marking."
_TEST_DESK = "Clear the desk: notes, books and phone away."
CARD_STEPS = {
    "cold": [_DESK, "Sit the 2-day recheck first, timed, without looking anything up.",
             "Write the check beside each answer, then fill in the Least-sure line.", _PHOTO],
    "teach": [_DESK, "Read the new-skill sheet, then close it.",
              "Do the drills, with the check beside each answer.", _PHOTO],
    "repair": [_DESK, "Work through the fix-mistakes sheet in order.",
               "Write the check beside each answer.", _PHOTO],
    "review": [_DESK, "Work through the review sheet in order.", "Write the check beside each answer.", _PHOTO],
    "mixed": [_DESK, "Work through the mixed sheet in order.", "Write the check beside each answer.", _PHOTO],
    "words": [_DESK, "Do the words sheet without a dictionary.", "Fill in the Least-sure line at the end.", _PHOTO],
    "mock": [_TEST_DESK, "Sit it in one go, timed, like the real thing.",
             "Write the start and stop times on the sheet.", _PHOTO],
    "diagnostic": [_TEST_DESK, "Sit it in one go; \"I don't know\" is always an accepted answer.",
                   "Write the start and stop times on the sheet.", _PHOTO],
    "checkpoint": [_TEST_DESK, "Sit it in one go, timed.", "Write the start and stop times on the sheet.", _PHOTO],
    "oral": ["Find a quiet place where you can speak out loud.", "Open Claude and ask for the speaking scenario.",
             "Note anything you could not say."],
    "project": ["Open your project folder.", "Open Claude and pick up the next step.", "Note where you stopped."],
    "long": [_DESK, "Open Claude: the session plan is in the brief.", "Take the planned break.", _PHOTO],
    "tutor_lesson": ["Bring your questions and your last homework.", "Take part in the lesson as usual.",
                     "Afterwards, tell Claude what was covered."],
    "buffer": ["This is spare time kept free for catching up.", "Open Claude to see whether anything needs it.",
               "If nothing does, the time is yours."],
    "admin": ["Open Claude in your study folder.", "Sort the planning or admin item for this subject.",
              "Look over the week plan before you stop."],
}
CARD_FALLBACK = {
    "cold": "Short on time: sit it anyway and stop when time runs out; a recheck can't move to another day.",
    "teach": "Short on time: read the sheet and do the first drill block only.",
    "mock": "Short on time: tell Claude before you start, so the test can move.",
    "diagnostic": "Short on time: tell Claude before you start, so the test can move.",
    "checkpoint": "Short on time: tell Claude before you start, so the test can move.",
    "oral": "Short on time: do one scenario.",
    "project": "Short on time: do one small step and note it.",
    "tutor_lesson": "If the lesson is cancelled, tell Claude so the time can be used.",
    "buffer": "Short on time: skip it; nothing is lost.",
    "admin": "Short on time: tell Claude, and it moves to the next session.",
}
DEFAULT_FALLBACK = "Short on time: do the first half and tell Claude where you stopped."
RECHECK_STEP = "Sit the 2-day recheck first."
RECHECK_FALLBACK = "Short on time: do the recheck only; it is the part that can't move."


# ==========================================================================
# Registration
# ==========================================================================

def register(subparsers):
    p = subparsers.add_parser("plan", help="plan blocks: add, place, move, cancel, done, miss, list, week, check, diff")
    sp = p.add_subparsers(dest="plan_cmd", metavar="<action>")

    a = sp.add_parser("add", help="add a block (prints its id); without --start, a recheck obligation")
    a.add_argument("subject")
    a.add_argument("--kind", required=True, choices=schema.BLOCK_KINDS)
    a.add_argument("--start", default=None, help="ISO time, e.g. 2026-10-15T07:00+01:00")
    a.add_argument("--min", dest="minutes", type=int, default=None, help="length in minutes")
    a.add_argument("--protected", action="store_true")
    a.add_argument("--measurement", action="store_true")
    a.add_argument("--soft", action="store_true")
    a.add_argument("--content", default=None, help="plain words; a recheck added by hand uses cold:<topic-id>")
    a.add_argument("--pair", default=None, help="the block this one belongs to (a recheck's teach block)")
    a.add_argument("--window-from", dest="window_from", default=None, help="obligation window start (no --start)")
    a.add_argument("--window-to", dest="window_to", default=None, help="obligation window end (no --start)")
    a.set_defaults(func=cmd_plan_add)

    a = sp.add_parser("place", help="give an obligation a time inside its window")
    a.add_argument("block")
    a.add_argument("--start", required=True)
    a.add_argument("--min", dest="minutes", type=int, required=True)
    a.set_defaults(func=cmd_plan_place)

    a = sp.add_parser("move", help="move a block (its paired rechecks move by the same amount)")
    a.add_argument("block")
    a.add_argument("--start", required=True)
    a.add_argument("--min", dest="minutes", type=int, default=None)
    a.set_defaults(func=cmd_plan_move)

    a = sp.add_parser("cancel", help="cancel a block (it stays on file, marked cancelled)")
    a.add_argument("block")
    a.add_argument("--reason", required=True)
    a.set_defaults(func=cmd_plan_cancel)

    a = sp.add_parser("done", help="mark a block done")
    a.add_argument("block")
    a.set_defaults(func=cmd_plan_done)

    a = sp.add_parser("miss", help="mark a block missed")
    a.add_argument("block")
    a.add_argument("--reason", required=True)
    a.set_defaults(func=cmd_plan_miss)

    a = sp.add_parser("list", help="list blocks; past unrecorded ones show as missed? (nothing is written)")
    a.add_argument("--subject", default=None)
    a.add_argument("--from", dest="from_date", default=None, metavar="DATE")
    a.add_argument("--to", dest="to_date", default=None, metavar="DATE")
    a.add_argument("--json", action="store_true")
    a.set_defaults(func=cmd_plan_list)

    a = sp.add_parser("week", help="write views/week.md (Mon-Sun, every subject) and print it")
    a.add_argument("--start", default=None, metavar="DATE", help="any date in the week (default: this week)")
    a.add_argument("--force", action="store_true", help="overwrite a hand-edited views/week.md (keeps a .bak)")
    a.set_defaults(func=cmd_plan_week)

    a = sp.add_parser("check", help="validate every future block and obligation (exit 1 on a hard problem)")
    a.add_argument("--json", action="store_true")
    a.set_defaults(func=cmd_plan_check)

    a = sp.add_parser("diff", help="calendar operations (create, move, cancel) against the recorded calendar state")
    a.add_argument("--subject", default=None)
    a.add_argument("--json", action="store_true")
    a.set_defaults(func=cmd_plan_diff)

    c = subparsers.add_parser("cal", help="calendar: ack written items, export .ics")
    csp = c.add_subparsers(dest="cal_cmd", metavar="<action>")
    a = csp.add_parser("ack", help="record calendar ids after a write: rows of {block, provider, id, etag, start}")
    a.add_argument("--from", dest="from_file", required=True, metavar="FILE", help="JSON file, or - for stdin")
    a.set_defaults(func=cmd_cal_ack)
    a = csp.add_parser("ics", help="write an RFC 5545 .ics file of the timed blocks")
    a.add_argument("out", help="output .ics path")
    a.add_argument("--from", dest="from_date", default=None, metavar="DATE", help="first day (default: today)")
    a.add_argument("--to", dest="to_date", default=None, metavar="DATE", help="last day (default: no limit)")
    a.add_argument("--subject", default=None)
    a.add_argument("--ops", choices=["all", "create"], default="all",
                   help="create: only the blocks plan diff would create (a file cannot move an imported event)")
    a.set_defaults(func=cmd_cal_ics)


def _out(text=""):
    sys.stdout.write(text + "\n")


# ==========================================================================
# Context
# ==========================================================================

class Ctx(object):
    """The workspace, its config, time zone and the current time, loaded once."""

    def __init__(self, ws):
        self.ws = ws
        self.cfg = ws.load_config()
        self.tz = ws.tzinfo()
        self.now = dates.now().astimezone(self.tz)
        self._subj = {}
        self._cache = {}

    # ---- config -------------------------------------------------------------
    @property
    def tcfg(self):
        return self.cfg.get("time") or {}

    def on_demand(self):
        return self.tcfg.get("schedule") == "on_demand"

    def vocab_plain(self):
        return ((self.cfg.get("learner") or {}).get("vocab") or "plain") == "plain"

    # ---- subjects -----------------------------------------------------------
    def subject(self, sid):
        """The Subject, or None when it is not in indelible.json."""
        if sid not in self._subj:
            entry = self.ws.subject_entry(sid)
            self._subj[sid] = wsmod.Subject(self.ws, sid, entry.get("dir") or sid) if entry else None
        return self._subj[sid]

    def _cached(self, key, fn):
        if key not in self._cache:
            try:
                self._cache[key] = fn()
            except (DataError, OSError):
                self._cache[key] = None
        return self._cache[key]

    def subject_cfg(self, sid):
        s = self.subject(sid)
        return (self._cached(("cfg", sid), s.load) if s else None) or {}

    def title(self, sid):
        return self.subject_cfg(sid).get("title") or sid

    def cold_window(self, sid):
        w = self.subject_cfg(sid).get("cold_window_h") or list(learning.DEFAULT_COLD_WINDOW_H)
        try:
            return float(w[0]), float(w[1])
        except (TypeError, ValueError, IndexError):
            return learning.DEFAULT_COLD_WINDOW_H

    def topic_ids(self, sid):
        return [t.get("id") for t in self.subject_cfg(sid).get("topics") or [] if isinstance(t, dict)]

    def confusable(self, sid):
        """Symmetric set of confusable topic pairs."""
        out = set()
        for t in self.subject_cfg(sid).get("topics") or []:
            if not isinstance(t, dict):
                continue
            for o in t.get("confusable_with") or []:
                out.add((t.get("id"), o))
                out.add((o, t.get("id")))
        return out

    def exposures(self, sid):
        s = self.subject(sid)
        return (self._cached(("exp", sid), s.load_exposures) if s else None) or []

    def topics_state(self, sid):
        s = self.subject(sid)
        return (self._cached(("ts", sid), s.load_topics_state) if s else None) or {}

    def sessions(self, sid):
        s = self.subject(sid)
        return (self._cached(("sess", sid), s.load_sessions) if s else None) or []

    def session_lock(self, sid):
        s = self.subject(sid)
        return self._cached(("lock", sid), s.read_session_lock) if s else None


# ==========================================================================
# Time helpers
# ==========================================================================

def _local(value, tz):
    dt = dates.try_parse_iso(value)
    return dt.astimezone(tz) if dt is not None else None


def parse_when(ctx, value, what="--start"):
    """An ISO time with a clock part; no offset means the workspace time zone."""
    text = str(value or "").strip()
    if not HAS_TIME_RE.search(text):
        raise UsageError("%s needs a date and a time, like 2026-10-15T07:00+01:00 (got %r)" % (what, value))
    try:
        dt = dates.parse_iso(text, tz=ctx.tz)
    except ValueError:
        raise UsageError("%s is not an ISO time like 2026-10-15T07:00+01:00 (got %r)" % (what, value))
    return dt.astimezone(ctx.tz)


def parse_day(value, what):
    try:
        return dates.to_date(value)
    except (ValueError, TypeError):
        raise UsageError("%s must be a date YYYY-MM-DD (got %r)" % (what, value))


def iso(dt):
    return dates.fmt_iso(dt) if dt is not None else None


def day_label(d):
    d = dates.to_date(d)
    return "%s %d %s" % (dates.WEEKDAYS[d.weekday()], d.day, MONTHS[d.month - 1])


def when_label(dt):
    return "%s %s" % (day_label(dt), dt.strftime("%H:%M")) if dt is not None else "?"


def span_label(s, e):
    if s is None:
        return "?"
    if e is None:
        return when_label(s)
    if e.date() == s.date():
        return "%s–%s" % (when_label(s), e.strftime("%H:%M"))
    return "%s – %s" % (when_label(s), when_label(e))


def at_local(d, hhmm, tz):
    """A local datetime on date d at HH:MM (DST-aware with zoneinfo)."""
    return datetime.combine(d, dates.parse_hhmm(hhmm)).replace(tzinfo=tz)


def overlaps(a0, a1, b0, b1):
    if None in (a0, a1, b0, b1):
        return False
    return a0 < b1 and b0 < a1


def fmt_hours(h):
    return ("%.0f" % h) if abs(h - round(h)) < 0.05 else ("%.1f" % h)


def plus(dt, hours=0, minutes=0):
    """dt plus an elapsed duration, kept in dt's time zone (right across a clock change)."""
    return dates.plus(dt, hours=hours, minutes=minutes)


def hours_from(a, b):
    """Elapsed hours from a to b (aware datetimes; right across a clock change)."""
    return dates.hours_from(a, b)


def next_quarter(dt):
    dt = dt.replace(second=0, microsecond=0)
    extra = (15 - dt.minute % 15) % 15
    return dt + timedelta(minutes=extra or 15)


# ==========================================================================
# Block helpers
# ==========================================================================

def b_start(b, tz):
    return _local(b.get("start"), tz)


def b_end(b, tz):
    return _local(b.get("end"), tz)


def b_window(b, tz):
    w = b.get("window")
    if not isinstance(w, dict):
        return None
    f, t = _local(w.get("from"), tz), _local(w.get("to"), tz)
    if f is None or t is None:
        return None
    return f, t


def b_minutes(b):
    s, e = dates.try_parse_iso(b.get("start")), dates.try_parse_iso(b.get("end"))
    if s is None or e is None:
        return 0
    return max(0, int(round((e - s).total_seconds() / 60.0)))


def is_obligation(b):
    return not b.get("start") and isinstance(b.get("window"), dict)


def is_measurement(b):
    return bool(b.get("measurement")) or b.get("kind") in MEASURE_KINDS


def _tokens(b):
    content = b.get("content")
    if not isinstance(content, str):
        return []
    out = []
    for m in TOKEN_RE.finditer(content):
        for t in m.group(2).split(","):
            t = t.strip()
            if t:
                out.append((m.group(1), t))
    return out


def cold_topics(b, known=None):
    """Topics named by ``cold:<T>`` in a block's content (filtered to known ids when given)."""
    out = []
    for verb, t in _tokens(b):
        if verb == "cold" and t not in out and (not known or t in known):
            out.append(t)
    return out


def paired_colds(block, blocks):
    """Recheck blocks that belong to ``block`` (their pair is it, or its pair is them)."""
    out = []
    for c in blocks:
        if c is block or c.get("kind") != "cold":
            continue
        if c.get("pair") == block.get("id") or (block.get("pair") and block.get("pair") == c.get("id")):
            out.append(c)
    return out


def exposed_topics(ctx, b, blocks):
    """Topics a (non-recheck) block warms up: teach/repair/review/drill/chat:<T> tokens,
    plus the topics of the rechecks paired to it."""
    if b.get("kind") == "cold":
        return []
    known = ctx.topic_ids(b.get("subject"))
    out = []
    for verb, t in _tokens(b):
        if verb in WARM_VERBS and t not in out and (not known or t in known):
            out.append(t)
    for c in paired_colds(b, blocks):
        for t in cold_topics(c, known):
            if t not in out:
                out.append(t)
    return out


def cold_window_for(ctx, b, by_id, pair_times=None):
    """The recheck window of a cold block: ``(from, to, basis, ref)`` or None.

    ``ref`` is the time the hours are counted from (None for a stored window).
    ``pair_times`` overrides the pair's (start, end), for a move being checked.
    """
    tz = ctx.tz
    if b.get("kind") != "cold":
        return None
    w = b_window(b, tz)
    if w is not None:
        return w[0], w[1], (b.get("window") or {}).get("basis") or "window", None
    lo, hi = ctx.cold_window(b.get("subject"))
    pair = by_id.get(b.get("pair")) if b.get("pair") else None
    if pair is not None and pair.get("kind") != "cold":
        ps, pe = pair_times if pair_times else (b_start(pair, tz), b_end(pair, tz))
        if ps is not None and pe is not None and (pair_times or pair.get("status") != "done"):
            return plus(pe, hours=lo), plus(ps, hours=hi), "pair", ps
    known = ctx.topic_ids(b.get("subject"))
    topics = cold_topics(b, known)
    start = b_start(b, tz) or ctx.now
    lows, highs, refs = [], [], []
    for t in topics:
        if not learning.is_first_serve(ctx.topics_state(b.get("subject")).get(t)):
            continue
        last = learning.last_exposure(t, ctx.exposures(b.get("subject")), before=start)
        if last is None:
            continue
        last = last.astimezone(tz)
        lows.append(plus(last, hours=lo))
        highs.append(plus(last, hours=hi))
        refs.append(last)
    if lows:
        return max(lows), min(highs), "exposure", max(refs)
    if pair is not None and pair.get("kind") != "cold":
        ps, pe = b_start(pair, tz), b_end(pair, tz)
        if ps is not None and pe is not None:
            return plus(pe, hours=lo), plus(ps, hours=hi), "pair", ps
    return None


def _window_opens_later(ctx, b, s):
    """(topic, last exposure, lo) when a recheck's first-serve topic was seen less than
    cold_window_h[0] hours (but 24 h or more) before the block starts, judged from
    the recorded exposures as L7 does; None otherwise. The stored window comes
    from the teaching time, so a drill sheet sat later shifts the real start."""
    lo, _ = ctx.cold_window(b.get("subject"))
    known = ctx.topic_ids(b.get("subject"))
    for t in cold_topics(b, known):
        if not learning.is_first_serve(ctx.topics_state(b.get("subject")).get(t)):
            continue
        last = learning.last_exposure(t, ctx.exposures(b.get("subject")), before=s)
        if last is None:
            continue
        h = hours_from(last, s)
        if NO_EXPOSURE_H <= h < lo:
            return t, last.astimezone(ctx.tz), lo
    return None


def window_text(w):
    return "%s – %s" % (when_label(w[0]), when_label(w[1]))


def ws_display(ws):
    """The workspace path for a card, with the home folder shown as ~."""
    root = str(ws.root)
    home = os.path.expanduser("~")
    try:
        rel = Path(root).resolve().relative_to(Path(home).resolve())
        return "~" if not rel.parts else "~/" + rel.as_posix()
    except (ValueError, OSError):
        return root


# ==========================================================================
# Loading and saving
# ==========================================================================

def find_block(blocks, block_id):
    for b in blocks:
        if b.get("id") == block_id:
            return b
    raise UsageError("Unknown block '%s'. List them with: indelible.py plan list" % block_id)


def _check_reason(text, what="--reason"):
    text = " ".join(str(text or "").split())
    if not text:
        raise UsageError("%s must not be empty" % what)
    if len(text) > REASON_MAX:
        raise UsageError("%s is longer than %d characters" % (what, REASON_MAX))
    return text


def _check_minutes(n, what="--min"):
    if n is None:
        raise UsageError("%s is required" % what)
    if n < 1 or n > MAX_BLOCK_MIN:
        raise UsageError("%s must be between 1 and %d minutes (got %s)" % (what, MAX_BLOCK_MIN, n))
    return n


def _save(ws, blocks, changed):
    """Validate the rows this command changed, then write the snapshot."""
    for b in changed:
        problems = schema.validate_block(b)
        if problems:
            raise DataError("Refused to save %s: %s" % (b.get("id"), "; ".join(problems)))
    ws.save_blocks(blocks)


# ==========================================================================
# plan add / place / move / cancel / done / miss
# ==========================================================================

def cmd_plan_add(args):
    ws = wsmod.from_args(args)
    ctx = Ctx(ws)
    subj = ws.subject(args.subject)
    state = (ws.subject_entry(subj.id) or {}).get("state", "live")
    if state in ("legacy", "shadow"):
        raise CheckFailed("Refused: %s is %s, so indelible plans nothing for it." % (subj.id, state))
    content = None
    if args.content is not None:
        content = " ".join(args.content.split())
        if len(content) > CONTENT_MAX:
            raise UsageError("--content is longer than %d characters" % CONTENT_MAX)
        content = content or None
    kind = args.kind
    start = end = None
    window = None
    if args.start:
        if args.window_from or args.window_to:
            raise UsageError("Give either --start (a timed block) or --window-from/--window-to (an obligation)")
        start = parse_when(ctx, args.start)
        end = plus(start, minutes=_check_minutes(args.minutes))
    elif args.minutes is not None:
        raise UsageError("--min needs --start (an obligation has a window, not a time)")

    with ws.lock():
        blocks = ws.load_blocks()
        by_id = dict((b.get("id"), b) for b in blocks)
        if args.pair and args.pair not in by_id:
            raise UsageError("Unknown --pair block '%s'" % args.pair)
        if args.pair and by_id[args.pair].get("subject") != subj.id:
            raise UsageError("--pair %s belongs to %s, not %s" % (args.pair, by_id[args.pair].get("subject"), subj.id))
        if start is None:
            window = _obligation_window(ctx, args, kind, content, subj.id, by_id)
        day = (start or window[0]).date()
        bid = ws.next_block_id(subj.id, day)
        row = {
            "v": 1, "id": bid, "subject": subj.id, "kind": kind,
            "start": iso(start), "end": iso(end),
            "window": None, "protected": bool(args.protected or kind == "cold"),
            "measurement": bool(args.measurement or kind in MEASURE_KINDS),
            "soft": bool(args.soft), "pair": args.pair or None, "content": content,
            "status": "planned", "cal": None, "moved_from": None, "miss_reason": None,
        }
        if window is not None:
            row["window"] = {"from": iso(window[0]), "to": iso(window[1])}
            if window[2]:
                row["window"]["basis"] = window[2]
        blocks.append(row)
        _save(ws, blocks, [row])

    _out(bid)
    if start is not None:
        _out("  %s · %s · %s · %dm" % (span_label(start, end), subj.id, kind, b_minutes(row)))
        if kind == "cold":
            w = cold_window_for(ctx, row, dict((b.get("id"), b) for b in blocks))
            if w is not None and not (w[0] <= start <= w[1]):
                _out("  Note: this recheck starts outside its window (%s); plan check fails until it moves."
                     % window_text(w))
            elif w is None and not cold_topics(row):
                _out("  Note: no cold:<topic-id> in --content, so plan check cannot guard this recheck's window.")
    else:
        _out("  obligation · %s · %s · window %s" % (subj.id, kind, window_text(window)))
    return 0


def _obligation_window(ctx, args, kind, content, sid, by_id):
    """(from, to, basis) for a block added without --start."""
    if args.window_from or args.window_to:
        if not (args.window_from and args.window_to):
            raise UsageError("Give both --window-from and --window-to")
        f = parse_when(ctx, args.window_from, "--window-from")
        t = parse_when(ctx, args.window_to, "--window-to")
        if t <= f:
            raise UsageError("--window-to must be after --window-from")
        return f, t, None
    if kind != "cold":
        raise UsageError("--start is required (only a recheck, kind cold, can be added as an obligation)")
    probe = {"kind": "cold", "subject": sid, "pair": args.pair, "content": content, "start": None}
    w = cold_window_for(ctx, probe, by_id)
    if w is None:
        raise UsageError("No window for this recheck: give --pair <teach block>, a cold:<topic-id> with a "
                         "recorded exposure, or --window-from/--window-to")
    basis = "pair" if w[2] == "pair" else "exposure"
    return w[0], w[1], basis


def cmd_plan_place(args):
    ws = wsmod.from_args(args)
    ctx = Ctx(ws)
    start = parse_when(ctx, args.start)
    end = plus(start, minutes=_check_minutes(args.minutes))
    with ws.lock():
        blocks = ws.load_blocks()
        b = find_block(blocks, args.block)
        if not is_obligation(b):
            if b.get("start"):
                raise CheckFailed("Refused: %s already has a time (%s). Use: plan move %s --start ISO"
                                  % (b["id"], span_label(b_start(b, ctx.tz), b_end(b, ctx.tz)), b["id"]))
            raise CheckFailed("Refused: %s has no window to place into." % b["id"])
        if b.get("status") not in OPEN:
            raise CheckFailed("Refused: %s is %s." % (b["id"], b.get("status")))
        w = b_window(b, ctx.tz)
        if w is None:
            raise DataError("%s has an unreadable window" % b["id"])
        if not (w[0] <= start <= w[1]):
            raise CheckFailed("Refused: %s is outside the window of %s: %s. Pick a start inside it."
                              % (when_label(start), b["id"], window_text(w)))
        b["start"], b["end"] = iso(start), iso(end)
        _save(ws, blocks, [b])
    _out("Placed %s: %s (window %s)." % (b["id"], span_label(start, end), window_text(w)))
    _out("Next: plan check")
    return 0


def cmd_plan_move(args):
    ws = wsmod.from_args(args)
    ctx = Ctx(ws)
    new_start = parse_when(ctx, args.start)
    if args.minutes is not None:
        _check_minutes(args.minutes)
    tz = ctx.tz
    with ws.lock():
        blocks = ws.load_blocks()
        by_id = dict((b.get("id"), b) for b in blocks)
        b = find_block(blocks, args.block)
        if b.get("status") in ("done", "cancelled"):
            raise CheckFailed("Refused: %s is %s; add a new block instead." % (b["id"], b.get("status")))
        if is_obligation(b):
            raise CheckFailed("Refused: %s has no time yet. Use: plan place %s --start ISO --min N"
                              % (b["id"], b["id"]))
        old_s, old_e = b_start(b, tz), b_end(b, tz)
        if old_s is None:
            raise DataError("%s has an unreadable start" % b["id"])
        minutes = args.minutes if args.minutes is not None else (b_minutes(b) or DEFAULT_RECHECK_MIN)
        new_end = plus(new_start, minutes=minutes)
        delta = new_start - old_s  # same tz: a wall-clock shift, so 07:00 stays 07:00 across a clock change

        problems = []
        if b.get("kind") == "cold":
            w = cold_window_for(ctx, b, by_id)
            if w is not None and not (w[0] <= new_start <= w[1]):
                problems.append("%s would start %s, outside its recheck window %s."
                                % (b["id"], when_label(new_start), window_text(w)))

        cascade = []  # (block, new start, new end, new window or None)
        if b.get("kind") != "cold":
            for c in paired_colds(b, blocks):
                if c.get("status") not in MOVABLE:
                    continue
                cw = c.get("window") if isinstance(c.get("window"), dict) else None
                shift_window = bool(cw) and cw.get("basis") == "pair"
                new_w = None
                if shift_window:  # derived from this block's planned time: derive it again
                    lo, hi = ctx.cold_window(c.get("subject"))
                    new_w = (plus(new_end, hours=lo), plus(new_start, hours=hi))
                if is_obligation(c):
                    if new_w is not None:
                        cascade.append((c, None, None, new_w))
                    continue
                cs, ce = b_start(c, tz), b_end(c, tz)
                if cs is None:
                    continue
                ns, ne = cs + delta, (ce + delta) if ce is not None else None
                if new_w is not None:
                    w = new_w
                elif cw:
                    w = b_window(c, tz)
                else:
                    w = cold_window_for(ctx, c, by_id, pair_times=(new_start, new_end))
                if w is not None and not (w[0] <= ns <= w[1]):
                    problems.append("its recheck %s would start %s, outside its window %s."
                                    % (c["id"], when_label(ns), window_text(w)))
                cascade.append((c, ns, ne, new_w))
        if problems:
            raise CheckFailed("Refused: nothing was moved.\n  " + "\n  ".join(problems) +
                              "\n  Fix: move the recheck inside its window first (plan move <recheck> --start ISO),"
                              " or pick a time that keeps it inside.")

        _apply_move(b, new_start, new_end)
        for c, ns, ne, new_w in cascade:
            if ns is not None:
                _apply_move(c, ns, ne)
            if new_w is not None:
                c["window"] = dict(c["window"], **{"from": iso(new_w[0]), "to": iso(new_w[1])})
        _save(ws, blocks, [b] + [x[0] for x in cascade])

    _out("Moved %s: %s → %s (%dm)." % (b["id"], when_label(old_s), when_label(new_start), minutes))
    for c, ns, ne, new_w in cascade:
        if ns is not None:
            _out("  Its 2-day recheck %s moved too: %s → %s (inside its window)."
                 % (c["id"], when_label(ns - delta), when_label(ns)))
        else:
            _out("  Its 2-day recheck %s (not placed yet) now has the window %s."
                 % (c["id"], window_text(new_w)))
    if b.get("cal"):
        _out("  It is in the calendar: plan diff lists the move.")
    _out("Next: plan check")
    return 0


def _apply_move(b, new_start, new_end):
    """Move a block. A missed block that is rebooked goes back to planned but keeps
    its miss (``misses`` and ``miss_reason``), so reviews still count it."""
    b["moved_from"] = b.get("start")
    b["start"], b["end"] = iso(new_start), iso(new_end)
    b["moves"] = int(b.get("moves") or 0) + 1
    if b.get("status") in ("missed", "missed?", "moved"):
        b["status"] = "planned"


def cmd_plan_cancel(args):
    ws = wsmod.from_args(args)
    ctx = Ctx(ws)
    reason = _check_reason(args.reason)
    with ws.lock():
        blocks = ws.load_blocks()
        b = find_block(blocks, args.block)
        if b.get("status") == "cancelled":
            _out("%s is already cancelled." % b["id"])
            return 0
        if b.get("status") == "done":
            raise CheckFailed("Refused: %s is done; a finished block is kept as it is." % b["id"])
        b["status"] = "cancelled"
        b["cancel_reason"] = reason
        b["cancelled_at"] = iso(ctx.now)
        others = [c for c in paired_colds(b, blocks) if c.get("status") in LIVE]
        _save(ws, blocks, [b])
    _out("Cancelled %s (%s). Reason: %s" % (b["id"], _where(ctx, b), reason))
    if b.get("cal"):
        _out("  It is in the calendar: plan diff lists it, to be marked cancelled there (not deleted).")
    for c in others:
        _out("  Its 2-day recheck %s is still planned; cancel it too only if the teaching is not happening."
             % c["id"])
    return 0


def cmd_plan_done(args):
    ws = wsmod.from_args(args)
    ctx = Ctx(ws)
    with ws.lock():
        blocks = ws.load_blocks()
        b = find_block(blocks, args.block)
        if b.get("status") == "done":
            _out("%s is already done." % b["id"])
            return 0
        if b.get("status") == "cancelled":
            raise CheckFailed("Refused: %s is cancelled." % b["id"])
        b["status"] = "done"
        b["miss_reason"] = None
        _save(ws, blocks, [b])
    _out("Done: %s (%s)." % (b["id"], _where(ctx, b)))
    return 0


def cmd_plan_miss(args):
    ws = wsmod.from_args(args)
    ctx = Ctx(ws)
    reason = _check_reason(args.reason)
    with ws.lock():
        blocks = ws.load_blocks()
        b = find_block(blocks, args.block)
        if b.get("status") in ("done", "cancelled"):
            raise CheckFailed("Refused: %s is %s." % (b["id"], b.get("status")))
        if is_obligation(b):
            raise CheckFailed("Refused: %s has no time yet, so it cannot be missed." % b["id"])
        s = b_start(b, ctx.tz)
        if s is not None and s > ctx.now:
            raise CheckFailed("Refused: %s has not started yet (%s). Move or cancel it instead."
                              % (b["id"], when_label(s)))
        earlier = [m for m in (b.get("misses") or []) if isinstance(m, dict)]
        same_slot = [m for m in earlier if _same_slot(ctx, m.get("slot"), b.get("start"))]
        b["status"] = "missed"
        b["miss_reason"] = reason
        b["misses"] = earlier + [{"at": iso(ctx.now), "slot": b.get("start"), "reason": reason}]
        _save(ws, blocks, [b])
    _out("Missed: %s (%s). Reason: %s" % (b["id"], _where(ctx, b), reason))
    if same_slot:
        _out("  This slot (%s %s) was missed before (%s): offer a different slot rather than the same one again."
             % (dates.WEEKDAYS[s.weekday()] if s else "?", s.strftime("%H:%M") if s else "?",
                ", ".join(str(m.get("reason")) for m in same_slot)))
    _out("Rebook it with: plan move %s --start ISO (it keeps its id and its miss history)." % b["id"])
    return 0


def _same_slot(ctx, a, b):
    """Same weekday and clock time (the 'same slot twice' pattern)."""
    x, y = _local(a, ctx.tz), _local(b, ctx.tz)
    return x is not None and y is not None and x.weekday() == y.weekday() and x.strftime("%H:%M") == y.strftime("%H:%M")


def _where(ctx, b):
    s, e = b_start(b, ctx.tz), b_end(b, ctx.tz)
    if s is not None:
        return span_label(s, e)
    w = b_window(b, ctx.tz)
    return ("window " + window_text(w)) if w else "no time"


# ==========================================================================
# plan list
# ==========================================================================

def missed_ids(ctx, blocks):
    """Ids of blocks past their end, planned or synced, not soft, with no overlapping session."""
    if ctx.on_demand():
        return set()
    out = set()
    tz, now = ctx.tz, ctx.now
    spans, linked = {}, set()
    for b in blocks:
        sid = b.get("subject")
        if sid in spans:
            continue
        rows = []
        for r in ctx.sessions(sid):
            if r.get("block"):
                linked.add(r["block"])
            act = r.get("actual") or {}
            rows.append((_local(act.get("start"), tz), _local(act.get("end"), tz)))
        lock = ctx.session_lock(sid)
        if lock:
            ls = _local(lock.get("start"), tz)
            le = _local(lock.get("planned_end"), tz)
            if ls is not None:
                rows.append((ls, max(now, le) if le is not None else now))
            if lock.get("block"):
                linked.add(lock["block"])
        spans[sid] = rows
    for b in blocks:
        if b.get("status") not in OPEN or b.get("soft") or b.get("kind") == "buffer":
            continue
        s, e = b_start(b, tz), b_end(b, tz)
        if s is None:
            continue
        e = e or s
        if e > now or b.get("id") in linked:
            continue
        if any(overlaps(s, e, a, z) for a, z in spans.get(b.get("subject"), [])):
            continue
        out.add(b.get("id"))
    return out


def _sort_key(ctx, b):
    s = b_start(b, ctx.tz)
    if s is None:
        w = b_window(b, ctx.tz)
        s = w[0] if w else None
    return (s.astimezone(ctx.tz).isoformat() if s else "9999", b.get("id") or "")


def cmd_plan_list(args):
    ws = wsmod.from_args(args)
    ctx = Ctx(ws)
    tz = ctx.tz
    if args.subject:
        ws.subject(args.subject)  # unknown subject -> exit 2
    d0 = parse_day(args.from_date, "--from") if args.from_date else None
    d1 = parse_day(args.to_date, "--to") if args.to_date else None
    lo = datetime.combine(d0, datetime.min.time()).replace(tzinfo=tz) if d0 else None
    hi = datetime.combine(d1 + timedelta(days=1), datetime.min.time()).replace(tzinfo=tz) if d1 else None
    blocks = ws.load_blocks()
    missed = missed_ids(ctx, blocks)
    rows = []
    for b in blocks:
        if args.subject and b.get("subject") != args.subject:
            continue
        s, e = b_start(b, tz), b_end(b, tz)
        if s is not None:
            a, z = s, e or s
        else:
            w = b_window(b, tz)
            if w is None:
                a = z = None
            else:
                a, z = w
        if a is not None:
            if lo is not None and z < lo:
                continue
            if hi is not None and a >= hi:
                continue
        elif lo is not None or hi is not None:
            continue
        rows.append(b)
    rows.sort(key=lambda b: _sort_key(ctx, b))

    if args.json:
        out = []
        for b in rows:
            r = dict(b)
            if b.get("id") in missed:
                r["status"] = "missed?"
                r["stored_status"] = b.get("status")
            r["minutes"] = b_minutes(b) if b.get("start") else None
            out.append(r)
        _out(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        _out("No blocks%s." % (" in that range" if (d0 or d1) else " yet"))
        return 0
    for b in rows:
        st = "missed?" if b.get("id") in missed else (b.get("status") or "?")
        s = b_start(b, tz)
        if s is not None:
            when = span_label(s, b_end(b, tz))
            mins = "%dm" % b_minutes(b)
        else:
            w = b_window(b, tz)
            when = "not placed; window %s" % (window_text(w) if w else "?")
            mins = "-"
        extra = []
        if b.get("protected"):
            extra.append("protected")
        if is_measurement(b):
            extra.append("measurement")
        if b.get("soft"):
            extra.append("soft")
        if b.get("pair"):
            extra.append("pair " + b["pair"])
        misses = [m for m in (b.get("misses") or []) if isinstance(m, dict)]
        if misses and st != "missed":
            extra.append("missed %s (%s), rebooked" % (when_label(_local(misses[-1].get("slot"), tz)),
                                                      misses[-1].get("reason") or "no reason"))
        line = "%s  %s  %s  %s  %s  %s" % (when, b.get("subject"), b.get("kind"), mins, st, b.get("id"))
        if b.get("content"):
            line += "  \"%s\"" % b["content"]
        if extra:
            line += "  [%s]" % ", ".join(extra)
        _out(line)
    return 0


# ==========================================================================
# plan week
# ==========================================================================

def cmd_plan_week(args):
    ws = wsmod.from_args(args)
    if args.start:
        parse_day(args.start, "--start")
    render = None
    try:
        from lib import cmd_brief
        render = getattr(cmd_brief, "render_week", None)
    except Exception:  # the brief module is optional; fall back to the local table
        render = None
    if callable(render):
        text = render(ws, start=args.start, force=args.force)
    else:
        ctx = Ctx(ws)
        text = week_text(ctx, args.start)
        with ws.lock():
            fio.write_text(ws.week_view_path, text, backup=bool(args.force))
    sys.stdout.write(text if text.endswith("\n") else text + "\n")
    return 0


def week_text(ctx, start=None):
    """A Mon–Sun table of every subject's blocks (fallback when cmd_brief is absent)."""
    tz = ctx.tz
    monday = dates.week_start(dates.to_date(start) if start else ctx.now.date())
    t0 = datetime.combine(monday, datetime.min.time()).replace(tzinfo=tz)
    t1 = t0 + timedelta(days=7)
    blocks = ctx.ws.load_blocks()
    missed = missed_ids(ctx, blocks)
    plain = ctx.vocab_plain()
    lines = [wsmod.GENERATED_BANNER,
             "# Week %s (%s – %s)" % (dates.iso_week(monday), day_label(monday), day_label(monday + timedelta(days=6))),
             ""]
    lines.append("| Day | Time | Subject | What | Min | Status |" + ("" if plain else " Block |"))
    lines.append("|---|---|---|---|---|---|" + ("" if plain else "---|"))
    minutes = {}
    for i in range(7):
        d = monday + timedelta(days=i)
        day_rows = []
        for b in blocks:
            s = b_start(b, tz)
            if s is None or b.get("status") == "cancelled" or s.date() != d:
                continue
            day_rows.append((s, b))
        day_rows.sort(key=lambda x: x[0])
        if not day_rows:
            lines.append("| %s | — |  |  |  |  |%s" % (day_label(d), "" if plain else "  |"))
            continue
        for s, b in day_rows:
            st = "missed?" if b.get("id") in missed else b.get("status", "?")
            mins = b_minutes(b)
            if b.get("status") != "missed":
                minutes[b.get("subject")] = minutes.get(b.get("subject"), 0) + mins
            row = "| %s | %s–%s | %s | %s | %d | %s |" % (
                day_label(d), s.strftime("%H:%M"), (b_end(b, tz) or s).strftime("%H:%M"),
                ctx.title(b.get("subject")), KIND_WORDS.get(b.get("kind"), b.get("kind")), mins, st)
            if not plain:
                row += " %s |" % b.get("id")
            lines.append(row)
    obl = []
    for b in blocks:
        if not is_obligation(b) or b.get("status") not in OPEN:
            continue
        w = b_window(b, tz)
        if w is None or w[1] < t0 or w[0] >= t1:
            continue
        obl.append("- %s: 2-day recheck, between %s and %s%s" % (
            ctx.title(b.get("subject")), when_label(w[0]), when_label(w[1]),
            "" if plain else " (%s)" % b.get("id")))
    if obl:
        head = ("2-day rechecks open (start a session inside the window; nothing to book):" if ctx.on_demand()
                else "2-day rechecks still to book:")
        lines += ["", head] + obl
    total = sum(minutes.values())
    ceiling = ctx.tcfg.get("weekly_ceiling_min")
    if not ctx.on_demand():
        lines += ["", "Minutes planned: %d%s" % (total, (" of a %s ceiling" % ceiling) if ceiling else "")]
    elif total:
        lines += ["", "Minutes booked: %d" % total]
    return "\n".join(lines) + "\n"


# ==========================================================================
# plan check
# ==========================================================================

class Findings(object):
    def __init__(self, ctx):
        self.ctx = ctx
        self.rows = []

    def add(self, level, rule, block, message, fix, when=None, **extra):
        row = {"level": level, "rule": rule, "block": block.get("id") if block else None,
               "subject": block.get("subject") if block else extra.pop("subject", None),
               "when": when, "message": message, "fix": fix}
        row.update(extra)
        self.rows.append(row)


def _sleep_spans(ctx, d0, d1):
    sleep = ctx.tcfg.get("sleep") or {}
    bed, wake = sleep.get("bed"), sleep.get("wake")
    if not (dates.is_hhmm(bed) and dates.is_hhmm(wake)):
        return []
    out = []
    d = d0
    while d <= d1:
        b = at_local(d, bed, ctx.tz)
        w = at_local(d, wake, ctx.tz)
        if w <= b:
            w = at_local(d + timedelta(days=1), wake, ctx.tz)
        out.append((b, w))
        d += timedelta(days=1)
    return out


def _blocked_spans(ctx, d0, d1):
    out = []
    entries = [e for e in (ctx.tcfg.get("blocked") or []) if isinstance(e, dict)]
    d = d0
    while d <= d1:
        wd = dates.WEEKDAYS[d.weekday()]
        for e in entries:
            if e.get("date"):
                try:
                    if dates.to_date(e["date"]) != d:
                        continue
                except ValueError:
                    continue
            elif e.get("days"):
                try:
                    if wd not in dates.expand_days(e["days"]):
                        continue
                except ValueError:
                    continue
            else:
                continue
            f, t = e.get("from"), e.get("to")
            if dates.is_hhmm(f) and dates.is_hhmm(t):
                a, z = at_local(d, f, ctx.tz), at_local(d, t, ctx.tz)
                if z <= a:
                    z = at_local(d + timedelta(days=1), t, ctx.tz)
            else:
                a = at_local(d, "00:00", ctx.tz)
                z = at_local(d + timedelta(days=1), "00:00", ctx.tz)
            out.append((a, z, e.get("what") or "blocked time"))
        d += timedelta(days=1)
    return out


def _window_spans(ctx, d):
    out = []
    wd = dates.WEEKDAYS[d.weekday()]
    for w in ctx.tcfg.get("windows") or []:
        if not isinstance(w, dict):
            continue
        try:
            days = dates.expand_days(w.get("days"))
        except ValueError:
            continue
        if wd not in days or not (dates.is_hhmm(w.get("from")) and dates.is_hhmm(w.get("to"))):
            continue
        a, z = at_local(d, w["from"], ctx.tz), at_local(d, w["to"], ctx.tz)
        if z <= a:
            z = at_local(d + timedelta(days=1), w["to"], ctx.tz)
        out.append((a, z))
    return out


def _week_of(dt):
    return dates.week_start(dt.date())


def run_checks(ctx, blocks):
    """All plan check findings for the future blocks and open obligations."""
    tz, now = ctx.tz, ctx.now
    f = Findings(ctx)
    by_id = dict((b.get("id"), b) for b in blocks)
    tcfg = ctx.tcfg

    timed = []   # (start, end, block) for blocks that occupy time
    for b in blocks:
        if b.get("status") not in OCCUPY or not b.get("start"):
            continue
        s, e = b_start(b, tz), b_end(b, tz)
        if s is None or e is None or e <= s:
            if b.get("status") in LIVE and (e is None or e > now):
                f.add("FAIL", "record", b, "%s has an unreadable or empty start/end." % b.get("id"),
                      "plan move %s --start ISO --min N" % b.get("id"))
            continue
        timed.append((s, e, b))
    timed.sort(key=lambda x: (x[0], x[2].get("id") or ""))
    future = [(s, e, b) for s, e, b in timed if e > now and b.get("status") in LIVE]
    obligations = [b for b in blocks if is_obligation(b) and b.get("status") in OPEN]

    # ---- hard: sleep and bedtime ------------------------------------------
    sleep = tcfg.get("sleep") or {}
    for s, e, b in future:
        spans = _sleep_spans(ctx, s.date() - timedelta(days=1), e.date())
        dur_min = hours_from(s, e) * 60.0
        for bed, wake in spans:
            cutoff = plus(bed, minutes=-BEDTIME_GAP_MIN)
            if overlaps(s, e, bed, wake):
                if s < bed:
                    fix_start = plus(cutoff, minutes=-dur_min)
                    fix = "plan move %s --start %s (ends %d min before bedtime)" % (
                        b["id"], iso(fix_start), BEDTIME_GAP_MIN)
                else:
                    fix = "plan move %s --start %s (after waking)" % (b["id"], iso(wake))
                f.add("FAIL", "sleep", b, "%s overlaps the sleep window (%s–%s)."
                      % (span_label(s, e), sleep.get("bed"), sleep.get("wake")), fix, when=iso(s))
                break
            if overlaps(s, e, cutoff, bed):
                fix_start = plus(cutoff, minutes=-dur_min)
                f.add("FAIL", "bedtime", b, "%s ends within %d min of bedtime (%s)."
                      % (span_label(s, e), BEDTIME_GAP_MIN, sleep.get("bed")),
                      "plan move %s --start %s" % (b["id"], iso(fix_start)), when=iso(s))
                break

    # ---- hard: blocked time -----------------------------------------------
    for s, e, b in future:
        for a, z, what in _blocked_spans(ctx, s.date() - timedelta(days=1), e.date()):
            if overlaps(s, e, a, z):
                if z - a >= timedelta(hours=23):
                    fix = "move it to another day: plan move %s --start ISO" % b["id"]
                else:
                    fix = "plan move %s --start %s (after %s)" % (b["id"], iso(z), what)
                f.add("FAIL", "blocked", b, "%s overlaps %s (%s)." % (span_label(s, e), what, span_label(a, z)),
                      fix, when=iso(s))
                break

    # ---- hard: overlapping blocks ------------------------------------------
    for i in range(len(timed)):
        s1, e1, b1 = timed[i]
        for j in range(i + 1, len(timed)):
            s2, e2, b2 = timed[j]
            if s2 >= e1:
                break
            if not overlaps(s1, e1, s2, e2):
                continue
            later = b2
            if not (e2 > now and b2.get("status") in LIVE) and not (e1 > now and b1.get("status") in LIVE):
                continue
            f.add("FAIL", "overlap", later, "%s (%s) overlaps %s (%s)."
                  % (later.get("id"), span_label(s2, e2), b1.get("id"), span_label(s1, e1)),
                  "plan move %s --start %s" % (later["id"], iso(e1)), when=iso(s2), other=b1.get("id"))

    # ---- hard: recheck window and the 24-hour rule -------------------------
    exposing = []  # (start, end, block, topics) for planned blocks that warm topics up
    horizon = plus(now, hours=-NO_EXPOSURE_H)  # older blocks cannot be within 24 h of a future recheck
    for s, e, b in timed:
        if e <= horizon:
            continue
        topics = exposed_topics(ctx, b, blocks)
        if topics:
            exposing.append((s, e, b, topics))
    for s, e, b in future:
        if b.get("kind") != "cold":
            continue
        w = cold_window_for(ctx, b, by_id)
        late = _window_opens_later(ctx, b, s)
        if late is not None and (w is None or w[0] <= s <= w[1]):
            t, last, lo = late
            f.add("FAIL", "cold_window", b, "Recheck %s starts %s h after %s was last seen (%s); the recheck "
                  "window opens at %s h." % (b["id"], fmt_hours(hours_from(last, s)), t, when_label(last),
                                             fmt_hours(lo)),
                  "plan move %s --start %s" % (b["id"], iso(max(plus(last, hours=lo), next_quarter(now)))),
                  when=iso(s), topic=t)
        if w is not None and not (w[0] <= s <= w[1]):
            if w[3] is not None:
                h = hours_from(w[3], s)
                lo, hi = ctx.cold_window(b.get("subject"))
                what = "starts %s h after %s; the window is %s–%s h (%s)" % (
                    fmt_hours(h), "its teach block" if w[2] == "pair" else "the last exposure",
                    fmt_hours(lo), fmt_hours(hi), window_text(w))
            else:
                what = "starts %s, outside its window %s" % (when_label(s), window_text(w))
            if w[1] > now:
                target = max(w[0], next_quarter(now))
                fix = "plan move %s --start %s" % (b["id"], iso(target))
                if w[2] == "pair":
                    fix += " (or move its teach block; the recheck follows)"
            else:
                fix = ("the window has passed: run it at the next session as a late recheck [practice], then "
                       "plan cancel %s --reason \"window passed\" and book a fresh recheck" % b["id"])
            f.add("FAIL", "cold_window", b, "Recheck %s %s." % (b["id"], what), fix, when=iso(s))
        known = ctx.topic_ids(b.get("subject"))
        cutoff = plus(s, hours=-NO_EXPOSURE_H)
        for t in cold_topics(b, known):
            last = learning.last_exposure(t, ctx.exposures(b.get("subject")), before=s)
            if last is not None and last.astimezone(tz) > cutoff:
                last = last.astimezone(tz)
                f.add("FAIL", "cold_24h", b, "Recheck %s: %s was seen %s, less than 24 h before it."
                      % (b["id"], t, when_label(last)),
                      "plan move %s --start %s" % (b["id"], iso(plus(last, hours=NO_EXPOSURE_H))),
                      when=iso(s), topic=t)
                continue
            for xs, xe, x, topics in exposing:
                if x is b or x.get("subject") != b.get("subject") or t not in topics:
                    continue
                if xs < s and xe > cutoff:
                    f.add("FAIL", "cold_24h", b, "Recheck %s: %s (%s) works on %s less than 24 h before it."
                          % (b["id"], x.get("id"), span_label(xs, xe), t),
                          "plan move %s --start %s (or move %s earlier)"
                          % (b["id"], iso(plus(xe, hours=NO_EXPOSURE_H)), x.get("id")),
                          when=iso(s), topic=t, other=x.get("id"))
                    break

    # ---- hard: 3 h between measurements -----------------------------------
    meas = [(s, e, b) for s, e, b in timed if is_measurement(b)]
    for s, e, b in meas:
        if not (e > now and b.get("status") in LIVE):
            continue
        for s0, e0, b0 in meas:
            if b0 is b or e0 > s:
                continue
            gap = hours_from(e0, s)
            if gap < MEASURE_GAP_H:
                f.add("FAIL", "measurement_gap", b, "Measurement %s starts %s h after measurement %s ends (needs %s h)."
                      % (b["id"], fmt_hours(gap), b0.get("id"), fmt_hours(MEASURE_GAP_H)),
                      "plan move %s --start %s" % (b["id"], iso(plus(e0, hours=MEASURE_GAP_H))),
                      when=iso(s), other=b0.get("id"))
                break

    # ---- hard: weekly ceiling ------------------------------------------------
    weeks = sorted(set(_week_of(s) for s, e, b in future))
    week_min, subj_week_min = {}, {}
    for s, e, b in timed:
        if b.get("status") not in OCCUPY:
            continue
        wk = _week_of(s)
        m = b_minutes(b)
        week_min[wk] = week_min.get(wk, 0) + m
        key = (wk, b.get("subject"))
        subj_week_min[key] = subj_week_min.get(key, 0) + m
    ceiling = tcfg.get("weekly_ceiling_min")
    if isinstance(ceiling, (int, float)) and ceiling > 0:
        for wk in weeks:
            total = week_min.get(wk, 0)
            if total > ceiling:
                over = int(total - ceiling)
                cands = [b for s, e, b in future if _week_of(s) == wk]
                buf = [b for b in cands if b.get("kind") == "buffer"]
                loose = sorted([b for b in cands if not b.get("protected")], key=lambda b: -b_minutes(b))
                pick = (buf or loose or [None])[0]
                if pick is not None:
                    fix = ("cut %d min following the drop order, e.g. plan cancel %s "
                           "--reason \"over the weekly ceiling\"" % (over, pick["id"]))
                else:
                    fix = "cut %d min this week, or raise time.weekly_ceiling_min with the learner's yes" % over
                f.add("FAIL", "ceiling", None, "Week %s has %d min planned; the ceiling is %d min (%d over)."
                      % (dates.iso_week(wk), total, ceiling, over), fix, week=dates.iso_week(wk))

    # ---- hard: obligations closing within 24 h, unplaced -----------------
    for b in obligations:
        w = b_window(b, tz)
        if w is None:
            f.add("FAIL", "record", b, "%s has an unreadable window." % b.get("id"),
                  "plan cancel %s --reason \"unreadable window\" and book a fresh recheck" % b.get("id"))
            continue
        left = hours_from(now, w[1])
        if left > OBLIGATION_DUE_H:
            continue
        if left <= 0:
            msg = "Recheck %s was never placed and its window closed %s." % (b["id"], when_label(w[1]))
            fix = ("run it at the next session as a late recheck [practice], then plan cancel %s "
                   "--reason \"window passed\" and book a fresh recheck" % b["id"])
        else:
            msg = "Recheck %s is not placed and its window closes %s (in %s h)." % (
                b["id"], when_label(w[1]), fmt_hours(left))
            target = max(w[0], next_quarter(now))
            if ctx.on_demand():
                fix = "tell the learner the window: between %s and %s" % (when_label(target), when_label(w[1]))
            else:
                fix = "plan place %s --start %s --min %d" % (b["id"], iso(target), DEFAULT_RECHECK_MIN)
        f.add("FAIL", "obligation_due", b, msg, fix, when=iso(w[1]))

    # ---- soft: study windows -------------------------------------------------
    if tcfg.get("windows"):
        for s, e, b in future:
            if b.get("soft"):
                continue
            inside = any(a <= s and e <= z for a, z in _window_spans(ctx, s.date()) + _window_spans(
                ctx, s.date() - timedelta(days=1)))
            if inside:
                continue
            day_windows = _window_spans(ctx, s.date())
            if day_windows:
                fix = "plan move %s --start %s (that day's study window)" % (b["id"], iso(day_windows[0][0]))
            else:
                fix = "move it to a day with a study window, or add this slot to time.windows with the learner's yes"
            f.add("WARN", "outside_window", b, "%s is outside the study windows." % span_label(s, e), fix, when=iso(s))

    # ---- soft: subject minimum ----------------------------------------------
    if weeks:
        wk = _week_of(now)
        span = []
        while wk <= weeks[-1]:
            span.append(wk)
            wk += timedelta(days=7)
        for entry in ctx.ws.subject_entries("live"):
            minimum = entry.get("min_weekly_min")
            if not isinstance(minimum, (int, float)) or minimum <= 0:
                continue
            for wk in span:
                got = subj_week_min.get((wk, entry["id"]), 0)
                if got < minimum:
                    f.add("WARN", "under_minimum", None, "Week %s: %s has %d min planned, under its minimum of %d."
                          % (dates.iso_week(wk), entry["id"], got, minimum),
                          "plan add %s --kind review --start ISO --min %d" % (entry["id"], int(minimum - got)),
                          subject=entry["id"], week=dates.iso_week(wk))

    # ---- soft: confusable topics taught the same day -----------------------
    taught = {}  # (subject, date) -> [(topic, block or None, start)]
    future_days = set((b.get("subject"), s.date()) for s, e, b in future)
    for s, e, b in timed:
        if b.get("kind") == "cold" or (b.get("subject"), s.date()) not in future_days:
            continue
        topics = [t for v, t in _tokens(b) if v == "teach"]
        if b.get("kind") in ("teach", "tutor_lesson"):
            topics += [t for t in exposed_topics(ctx, b, blocks) if t not in topics]
        for t in topics:
            taught.setdefault((b.get("subject"), s.date()), []).append((t, b, s))
    for sid, d in sorted(future_days, key=lambda x: (x[0] or "", x[1])):
        for x in ctx.exposures(sid):
            if x.get("kind") != "teach":
                continue
            at = _local(x.get("at"), tz)
            if at is not None and at.date() == d:
                taught.setdefault((sid, d), []).append((x.get("topic"), None, at))
    reported = set()
    for (sid, d), items in sorted(taught.items(), key=lambda kv: (kv[0][0] or "", kv[0][1])):
        if (sid, d) not in future_days:
            continue
        pairs = ctx.confusable(sid)
        items = sorted(items, key=lambda x: x[2])
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                t1, bl1, _ = items[i]
                t2, bl2, s2 = items[j]
                if t1 == t2 or (t1, t2) not in pairs:
                    continue
                key = (sid, d, frozenset((t1, t2)))
                if key in reported:
                    continue
                reported.add(key)
                target = bl2 or bl1
                if target is None:
                    continue
                f.add("WARN", "confusable", target, "%s and %s are easy to mix up and are both taught on %s."
                      % (t1, t2, day_label(d)),
                      "plan move %s --start ISO (another day)" % target["id"], when=iso(s2))

    # ---- soft: rest day -------------------------------------------------------
    rest = tcfg.get("rest_day")
    if rest:
        try:
            rest_idx = dates.weekday_index(rest)
        except ValueError:
            rest_idx = None
        if rest_idx is not None:
            for s, e, b in future:
                if s.weekday() == rest_idx:
                    f.add("WARN", "rest_day", b, "%s falls on the rest day (%s)." % (span_label(s, e), rest),
                          "plan move %s --start ISO (another day), unless the learner asked for it" % b["id"],
                          when=iso(s))

    order = {"FAIL": 0, "WARN": 1}
    f.rows.sort(key=lambda r: (order.get(r["level"], 2), r.get("when") or "", r.get("block") or ""))
    return f.rows, {"blocks": len(future), "obligations": len(obligations)}


def cmd_plan_check(args):
    ws = wsmod.from_args(args)
    ctx = Ctx(ws)
    blocks = ws.load_blocks()
    rows, checked = run_checks(ctx, blocks)
    fails = sum(1 for r in rows if r["level"] == "FAIL")
    warns = sum(1 for r in rows if r["level"] == "WARN")
    result = "FAIL" if fails else "PASS"
    if args.json:
        _out(json.dumps({"result": result, "fails": fails, "warns": warns, "checked": checked,
                         "findings": rows}, ensure_ascii=False, indent=2))
    else:
        for r in rows:
            _out("%s %s: %s" % (r["level"], r["rule"], r["message"]))
            _out("  Fix: %s" % r["fix"])
        _out("plan check: %s · %d hard, %d warning%s · %d block%s and %d open recheck%s checked" % (
            result, fails, warns, "" if warns == 1 else "s", checked["blocks"],
            "" if checked["blocks"] == 1 else "s", checked["obligations"],
            "" if checked["obligations"] == 1 else "s"))
    return 1 if fails else 0


# ==========================================================================
# plan diff (calendar cards)
# ==========================================================================

def card_title(ctx, b):
    """``<Subject title> · <kind in plain words> · <min>m``; never a topic name."""
    return "%s · %s · %dm" % (ctx.title(b.get("subject")), KIND_WORDS.get(b.get("kind"), "study"), b_minutes(b))


def card_notes(ctx, b):
    """The card body (<= 600 characters): marker, 3–6 steps, fallback, start line.

    Built from the block's kind only, so it never names a topic or quotes content.
    """
    kind = b.get("kind")
    steps = list(CARD_STEPS.get(kind) or CARD_STEPS["review"])
    fallback = CARD_FALLBACK.get(kind, DEFAULT_FALLBACK)
    content = b.get("content") if isinstance(b.get("content"), str) else ""
    if kind != "cold" and RECHECK_WORD_RE.search(content or ""):
        steps.insert(1 if steps and steps[0] in (_DESK, _TEST_DESK) else 0, RECHECK_STEP)
        fallback = RECHECK_FALLBACK
    steps = steps[:6]
    start_line = 'Start: open Claude in %s and say "start %s"' % (ws_display(ctx.ws), b.get("subject"))

    def build(steps, start_line):
        lines = ["[ind:%s]" % b.get("id")]
        lines += ["%d. %s" % (i + 1, s) for i, s in enumerate(steps)]
        lines += [fallback, start_line]
        return "\n".join(lines)

    text = build(steps, start_line)
    while len(text) > NOTES_MAX and len(steps) > 3:
        steps = steps[:-1]
        text = build(steps, start_line)
    if len(text) > NOTES_MAX:
        text = build(steps, 'Start: open Claude in your study folder and say "start %s"' % b.get("subject"))
    return text[:NOTES_MAX]


CONNECTORS = ("ticktick", "google", "other")


def diff_rows(ctx, blocks, subject=None):
    """(rows, unchanged count). Rows: {op, block, subject, title, start, end, notes, was?, cal_id?}.

    When the configured provider is a connector and a block's ``cal`` belongs to
    another provider (e.g. an .ics fallback), the block is a ``create`` for the
    configured one (``takeover`` names the old provider), and a cancelled one
    needs nothing there.
    """
    tz, now = ctx.tz, ctx.now
    provider = (ctx.cfg.get("calendar") or {}).get("provider")
    rows, unchanged = [], 0
    for b in blocks:
        if subject and b.get("subject") != subject:
            continue
        cal = b.get("cal") if isinstance(b.get("cal"), dict) else None
        other = bool(cal) and provider in CONNECTORS and cal.get("provider") not in (None, provider)
        st = b.get("status")
        if st == "cancelled":
            if cal and not cal.get("cancelled") and not other:
                rows.append(_diff_row(ctx, "cancel", b, cal))
            continue
        if not b.get("start") or st not in LIVE:
            continue
        s, e = b_start(b, tz), b_end(b, tz)
        if s is None or e is None or e <= now:
            continue
        if not cal:
            rows.append(_diff_row(ctx, "create", b, None))
            continue
        if other:
            row = _diff_row(ctx, "create", b, None)
            row["takeover"] = cal.get("provider")
            rows.append(row)
            continue
        cs, ce = _local(cal.get("start"), tz), _local(cal.get("end"), tz)
        if cs is None or cs != s or (ce is not None and ce != e):
            rows.append(_diff_row(ctx, "move", b, cal))
        else:
            unchanged += 1
    order = {"create": 0, "move": 1, "cancel": 2}
    rows.sort(key=lambda r: (r["start"] or "9999", order[r["op"]], r["block"]))
    return rows, unchanged


def _diff_row(ctx, op, b, cal):
    s, e = b_start(b, ctx.tz), b_end(b, ctx.tz)
    row = {"op": op, "block": b.get("id"), "subject": b.get("subject"), "title": card_title(ctx, b),
           "start": iso(s), "end": iso(e), "notes": card_notes(ctx, b)}
    if cal:
        row["was"] = cal.get("start")
        row["cal_id"] = cal.get("id")
        row["provider"] = cal.get("provider")
    return row


def cmd_plan_diff(args):
    ws = wsmod.from_args(args)
    ctx = Ctx(ws)
    if args.subject:
        ws.subject(args.subject)
    rows, unchanged = diff_rows(ctx, ws.load_blocks(), args.subject)
    if args.json:
        _out(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    n = dict((op, sum(1 for r in rows if r["op"] == op)) for op in ("create", "move", "cancel"))
    _out("Add %d · Move %d · Cancel %d · Unchanged %d" % (n["create"], n["move"], n["cancel"], unchanged))
    for r in rows:
        s, e = _local(r["start"], ctx.tz), _local(r["end"], ctx.tz)
        if r["op"] == "create":
            _out("+ %s  %s" % (span_label(s, e), r["title"]))
        elif r["op"] == "move":
            _out("~ %s → %s  %s" % (when_label(_local(r.get("was"), ctx.tz)), when_label(s), r["title"]))
        else:
            _out("- %s  %s (mark cancelled, not deleted)" % (when_label(s), r["title"]))
    if not rows:
        _out("Nothing to write: the calendar matches the plan.")
    return 0


# ==========================================================================
# cal ack / cal ics
# ==========================================================================

def _read_rows(path_arg):
    if path_arg == "-":
        buf = getattr(sys.stdin, "buffer", None)
        text = buf.read().decode("utf-8-sig", errors="replace") if buf is not None else sys.stdin.read()
        try:
            data = json.loads(text) if text.strip() else []
        except ValueError as exc:
            raise UsageError("stdin is not JSON: %s" % exc)
    else:
        p = Path(path_arg).expanduser()
        if not p.is_file():
            raise UsageError("File not found: %s" % p)
        data = fio.read_json(p, default=[])
    if isinstance(data, dict):
        data = data.get("rows") or data.get("results") or ([data] if data.get("block") else [])
    if not isinstance(data, list):
        raise UsageError("Expected a list of {block, provider, id, etag, start} rows")
    return data


def cmd_cal_ack(args):
    ws = wsmod.from_args(args)
    ctx = Ctx(ws)
    rows = _read_rows(args.from_file)
    clean = []
    for i, r in enumerate(rows):
        if not isinstance(r, dict) or not isinstance(r.get("block"), str):
            raise UsageError("Row %d needs a block id" % (i + 1))
        provider = r.get("provider")
        if provider not in schema.CAL_PROVIDERS or provider == "none":
            raise UsageError("Row %d: provider must be one of: %s" % (
                i + 1, ", ".join(p for p in schema.CAL_PROVIDERS if p != "none")))
        cid = r.get("id")
        if cid is None or str(cid).strip() == "":
            raise UsageError("Row %d (%s) needs the calendar item id" % (i + 1, r["block"]))
        start = None
        if r.get("start"):
            start = dates.try_parse_iso(r["start"], tz=ctx.tz)
            if start is None:
                raise UsageError("Row %d (%s): start is not an ISO time" % (i + 1, r["block"]))
        clean.append((r["block"], provider, str(cid), r.get("etag"), start))
    synced = cancelled = 0
    unknown, changed = [], []
    with ws.lock():
        blocks = ws.load_blocks()
        by_id = dict((b.get("id"), b) for b in blocks)
        for bid, provider, cid, etag, start in clean:
            b = by_id.get(bid)
            if b is None:
                unknown.append(bid)
                continue
            bs = b_start(b, ctx.tz)
            start = start.astimezone(ctx.tz) if start is not None else bs
            cal = {"provider": provider, "id": cid, "etag": etag, "start": iso(start), "end": None}
            if bs is not None and start is not None and start == bs:
                cal["end"] = b.get("end")
            if b.get("status") == "cancelled":
                cal["cancelled"] = True
                cancelled += 1
            elif b.get("status") in LIVE:
                b["status"] = "synced"
                synced += 1
            b["cal"] = cal
            changed.append(b)
        _save(ws, blocks, changed)
    _out("Acknowledged %d row%s: %d synced, %d cancelled in the calendar." % (
        len(clean) - len(unknown), "" if len(clean) - len(unknown) == 1 else "s", synced, cancelled))
    if unknown:
        _out("Unknown blocks, not recorded: %s" % ", ".join(unknown))
        return 1
    return 0


def _inside(path, folder):
    try:
        Path(path).resolve().relative_to(Path(folder).resolve())
        return True
    except (ValueError, OSError):
        return False


def cmd_cal_ics(args):
    ws = wsmod.from_args(args)
    ctx = Ctx(ws)
    out = Path(args.out).expanduser()
    if not out.is_absolute():
        out = Path.cwd() / out
    if _inside(out, SKILL_DIR):
        raise UsageError("Refused: write the .ics inside the workspace (e.g. %s), not inside the skill folder"
                         % ws.rel(ws.ics_dir / out.name))
    if args.subject:
        ws.subject(args.subject)
    d0 = parse_day(args.from_date, "--from") if args.from_date else ctx.now.date()
    d1 = parse_day(args.to_date, "--to") if args.to_date else None
    if d1 is not None and d1 < d0:
        raise UsageError("--to is before --from")
    reminder = (ctx.cfg.get("calendar") or {}).get("reminder_min")
    if not isinstance(reminder, int) or reminder < 0:
        reminder = DEFAULT_REMINDER_MIN
    events = []
    blocks = sorted(ws.load_blocks(), key=lambda b: _sort_key(ctx, b))
    only = None
    if getattr(args, "ops", "all") == "create":
        # The diff's creates, minus blocks already sent out in an .ics file (a takeover
        # row for another provider must not be exported to a file a second time).
        only = set(r["block"] for r in diff_rows(ctx, blocks, args.subject)[0]
                   if r["op"] == "create" and r.get("takeover") != "ics")
    for b in blocks:
        if b.get("status") == "cancelled" or not b.get("start"):
            continue
        if args.subject and b.get("subject") != args.subject:
            continue
        if only is not None and b.get("id") not in only:
            continue
        s, e = b_start(b, ctx.tz), b_end(b, ctx.tz)
        if s is None or e is None or e <= s:
            continue
        if s.date() < d0 or (d1 is not None and s.date() > d1):
            continue
        events.append({
            "uid": "%s@indelible" % b["id"], "dtstamp": ctx.now, "start": s, "end": e,
            "summary": card_title(ctx, b), "description": card_notes(ctx, b),
            "sequence": int(b.get("moves") or 0), "alarm_min": reminder, "categories": ["indelible"],
        })
    text = ics.build_calendar(events, version=VERSION, name="Study")
    with ws.lock():
        fio.write_text(out, text, backup=False)
    _out("Wrote %d event%s to %s (%s to %s)." % (len(events), "" if len(events) == 1 else "s", out,
                                                day_label(d0), day_label(d1) if d1 else "the last block"))
    if events:
        _out("Import it into a calendar named \"Study\". A file can't move or cancel events already imported%s."
             % ("" if only is not None else "; for new blocks only, use --ops create"))
    return 0
