"""Session commands: the lock, exposures, taught topics, overrides and the close checklist.

    session open [subject] --planned MIN [--block ID] [--kind K] [--park-other]
    session status [subject]
    session expose <subject> <topic> [--kind chat|teach|repair|drill|review]
    session taught <subject> <topic> [--by sheet|external|chat|tutor] [--block ID]
    session override <subject> "<said>" --predict "<items>"
    session close [subject] [--note TEXT] [--defer REASON]

The lock is ``<subject>/.indelible/session.lock``. A lock is *unclosed* when
now is more than 2 h past its planned end, or ``.indelible/unclosed`` exists
(written when the learner parks the subject to study another one).

``session close`` runs checks C1-C8 about the session since the lock start
and prints one PASS, FAIL or INFO line per check. C2 does not ask for the
grading of read-then-close sheets (theory, external, example, triage): their
pencil items are done with the page open and are never mastery evidence.
Recheck windows and the 24-hour rule use elapsed hours (``dates.plus``), so
they stay right across a clock change. On PASS it appends the
session row, removes the lock, marks the linked block done and renders the
views. On FAIL it exits 1 and the lock stays, unless ``--defer REASON`` turns
every failing check into a to-do (a ledger ``owed`` row) due in 24 h.
"""

import copy
import re
import sys
from datetime import datetime, timedelta

from lib import CheckFailed, DataError, UsageError
from lib import dates, learning, schema
from lib import ws as wsmod
from lib import io as fio
from lib import cmd_brief as brief
from lib import cmd_ledger as ledger

# Promise words in English and in the personas' first languages (pt, es, de).
PROMISE_RE = re.compile(r"\b(tomorrow|later|next time|amanhã|mais tarde|mañana|luego|morgen|später)\b",
                        re.IGNORECASE | re.UNICODE)
# Read-then-close sheets: their pencil items are done with the page open, so
# they are never mastery evidence and need no grading at close (C2).
PENCIL_TYPES = ("theory", "external", "example", "triage")
NOTE_MAX = 120
DEFER_DUE_H = 24
C2_OWED_H = 24
C5_HORIZON_H = 12
PLANNED_MIN, PLANNED_MAX = 5, 720
OPEN = brief.OPEN_BLOCK_STATUSES
VERDICT_WORDS = (("right", "right"), ("half", "half"), ("wrong", "wrong"), ("dont_know", "don't know"),
                 ("skip", "skipped"))


def register(subparsers):
    p = subparsers.add_parser("session", help="the session lock, exposures and the close checklist")
    sp = p.add_subparsers(dest="session_cmd", metavar="<open|status|expose|taught|override|close>")

    o = sp.add_parser("open", help="write the session lock and print the budget")
    o.add_argument("subject", nargs="?", default=None)
    o.add_argument("--planned", type=int, required=True, metavar="MIN", help="planned minutes")
    o.add_argument("--block", default=None, metavar="ID", help="the plan block this session runs")
    o.add_argument("--kind", choices=schema.BLOCK_KINDS, default=None, help="default: the block's kind, else teach")
    o.add_argument("--park-other", dest="park_other", action="store_true",
                   help="park another subject's open session (it will close late)")
    o.set_defaults(func=cmd_open)

    s = sp.add_parser("status", help="one line: minutes used, close start, questions so far")
    s.add_argument("subject", nargs="?", default=None)
    s.set_defaults(func=cmd_status)

    e = sp.add_parser("expose", help="record that a topic was taught or discussed outside a sheet")
    e.add_argument("subject")
    e.add_argument("topic")
    e.add_argument("--kind", choices=schema.EXPOSURE_KINDS, default="chat")
    e.set_defaults(func=cmd_expose)

    t = sp.add_parser("taught", help="a topic was taught: books its 2-day recheck window")
    t.add_argument("subject")
    t.add_argument("topic")
    t.add_argument("--by", choices=schema.TAUGHT_BY, default="sheet")
    t.add_argument("--block", default=None, metavar="ID", help="the teach block (pairs the recheck with it)")
    t.set_defaults(func=cmd_taught)

    v = sp.add_parser("override", help="log the learner's override with an item-level prediction")
    v.add_argument("subject")
    v.add_argument("said", help="the learner's words")
    v.add_argument("--predict", required=True, help='which items, e.g. "items 2 and 5 right"')
    v.set_defaults(func=cmd_override)

    c = sp.add_parser("close", help="run the close checklist and close the session")
    c.add_argument("subject", nargs="?", default=None)
    c.add_argument("--note", default=None, help="at most 120 characters")
    c.add_argument("--defer", default=None, metavar="REASON",
                   help="turn every failing check into a to-do due in 24 h and close anyway")
    c.set_defaults(func=cmd_close)


def _out(text=""):
    sys.stdout.write(text + "\n")


def _fmt(dt):
    return dates.fmt_iso(dt)


def _require_writable(ws, subj):
    st = brief.subject_state(ws, subj.id)
    if st in ("legacy", "shadow"):
        raise CheckFailed("Refused: %s is %s, so indelible writes nothing for it." % (subj.id, st))


def _date(value):
    try:
        return dates.to_date(value) if value else None
    except ValueError:
        return None


# ==========================================================================
# open / status
# ==========================================================================

def cmd_open(args):
    ws = wsmod.from_args(args)
    subj = ws.resolve_subject(args.subject)
    _require_writable(ws, subj)
    P = args.planned
    if P < PLANNED_MIN or P > PLANNED_MAX:
        raise UsageError("--planned must be between %d and %d minutes (got %d)" % (PLANNED_MIN, PLANNED_MAX, P))
    now = brief.now_in(ws).replace(second=0, microsecond=0)
    cfg = ws.load_config()
    sess = cfg.get("session") or {}
    titles = brief.subject_titles(ws)
    with ws.lock():
        lk = brief.session_lock_state(subj, now)
        if lk is not None:
            if lk["_unclosed"]:
                raise CheckFailed(
                    "Refused: the session for %s that started %s was never closed. Close it first: session close %s "
                    "(it is logged as late), then open a new one." % (subj.title(), brief.fmt_when(lk["_start"], now),
                                                                       subj.id))
            raise CheckFailed(
                "Refused: a session for %s is already open (started %s, planned end %s). Carry on; run: "
                "session status %s"
                % (subj.title(), brief.fmt_when(lk["_start"], now), lk["_planned_end"].strftime("%H:%M"), subj.id))
        others = []
        for other in ws.subjects():
            if other.id == subj.id:
                continue
            ol = brief.session_lock_state(other, now)
            if ol is None or ol["_parked"]:
                continue
            others.append((other, ol))
        if others and not args.park_other:
            lines = ["Another subject has a session open:"]
            for other, ol in others:
                lines.append("  %s (%s): %s started %s, planned end %s%s" % (
                    titles.get(other.id, other.id), other.id, ol.get("session_id") or "?",
                    brief.fmt_when(ol["_start"], now), brief.fmt_when(ol["_planned_end"], now),
                    " (unclosed)" if ol["_unclosed"] else ""))
            lines.append("Ask the learner: close it first (session close <subject>), or park it "
                         "(run this again with --park-other). Nothing was changed.")
            raise CheckFailed("\n".join(lines))
        block = None
        if args.block:
            block = ws.get_block(args.block)
            if block is None:
                raise UsageError("No block %s. List them with: plan list --subject %s" % (args.block, subj.id))
            if block.get("subject") != subj.id:
                raise UsageError("Block %s belongs to %s, not %s" % (args.block, block.get("subject"), subj.id))
        kind = args.kind or (block or {}).get("kind") or "teach"
        sid = subj.next_session_id()
        end = dates.plus(now, minutes=P)
        cstart = learning.close_start(now, P).astimezone(now.tzinfo)
        lock = {"v": 1, "session_id": sid, "start": _fmt(now), "planned_min": P, "planned_end": _fmt(end),
                "close_start": _fmt(cstart), "block": block.get("id") if block else None, "kind": kind}
        for other, ol in others:
            fio.write_json(other.unclosed_path, {"v": 1, "parked_at": _fmt(now), "session_id": ol.get("session_id"),
                                                 "for": subj.id}, backup=False)
        subj.write_session_lock(lock)

    scfg = subj.load()
    layer = learning.dominant_layer(scfg)
    bmin = sess.get("break_min")
    budget = learning.session_budget(P, layer, scfg.get("pace_s"), sess.get("break_every_min") or 75,
                                     10 if bmin is None else bmin)
    _out("Session open: %s · %d min · %s–%s · close starts %s" % (
        subj.title(), P, brief.fmt_when(now, now), end.strftime("%H:%M"), cstart.strftime("%H:%M")))
    _out("Budget: %s work minutes · %d questions in total, the 2-day recheck included (%s, %s s per question) · "
         "grading about %s min" % (_num(budget["work_min"]), budget["asks_budget"], layer, budget["pace_s"],
                                   _num(budget["grading_est_min"])))
    if budget["breaks"]:
        times = [dates.plus(now, minutes=off).strftime("%H:%M") for off in budget["break_offsets_min"]]
        _out("Breaks: %d min at %s" % (budget["break_min"], ", ".join(times)))
    else:
        _out("Breaks: none")
    mx = sess.get("max_min")
    if isinstance(mx, int) and P > mx:
        _out("Note: %d min is over the learner's usual maximum of %d min." % (P, mx))
    for other, ol in others:
        _out("Parked: %s. Its close is still owed and will be logged as late." % titles.get(other.id, other.id))
    _out("Lock: %s%s · kind %s" % (sid, (" · block " + block["id"]) if block else "", kind))
    return 0


def _num(x):
    return ("%d" % x) if float(x) == int(x) else ("%.1f" % x)


def _attempts_since(subj, start, now, session_id=None):
    """Asks graded in this session: tagged with its id, or graded (else taken) since the lock start."""
    out = []
    hi = now + timedelta(minutes=1)
    for a in subj.load_attempts():
        if session_id and a.get("session") == session_id:
            out.append(a)
            continue
        if a.get("session") and session_id:
            continue  # graded in another session
        t = dates.try_parse_iso(a.get("graded_at")) or dates.try_parse_iso(a.get("at"))
        if t is not None and start <= t <= hi:
            out.append(a)
    return out


def cmd_status(args):
    ws = wsmod.from_args(args)
    subj = ws.resolve_subject(args.subject)
    now = brief.now_in(ws)
    lk = brief.session_lock_state(subj, now)
    if lk is None:
        _out("[indelible] no session open for %s" % subj.title())
        return 0
    if lk["_unclosed"]:
        _out("[indelible] the %s session from %s was not closed · run the close first"
             % (subj.title(), brief.fmt_when(lk["_start"], now)))
        return 0
    elapsed = max(0, int((now - lk["_start"]).total_seconds() // 60))
    q = len(_attempts_since(subj, lk["_start"], now, lk.get("session_id")))
    cs = lk["_close_start"]
    line = "[indelible] %d/%d min · close starts %s · questions so far %d" % (
        elapsed, int(lk["_planned_min"]), cs.strftime("%H:%M") if cs else "?", q)
    if cs is not None and now >= cs:
        line += " · closing time"
    _out(line)
    return 0


# ==========================================================================
# expose / taught / override
# ==========================================================================

def _cold_blocks_for(ws, subj, tid, blocks=None):
    blocks = ws.load_blocks() if blocks is None else blocks
    return [b for b in blocks if b.get("subject") == subj.id and b.get("kind") == "cold"
            and b.get("status") in OPEN and tid in brief.block_topics(b)]


def cmd_expose(args):
    ws = wsmod.from_args(args)
    subj = ws.subject(args.subject)
    _require_writable(ws, subj)
    t = subj.require_topic(args.topic)
    now = brief.now_in(ws)
    row = {"v": 1, "topic": t["id"], "at": _fmt(now), "kind": args.kind}
    problems = schema.validate_exposure(row)
    if problems:
        raise UsageError("; ".join(problems))
    with ws.lock():
        subj.append_exposure(row)
    until = dates.plus(now, hours=learning.NO_EXPOSURE_H)  # elapsed hours: right across a clock change
    _out("Noted: %s %s seen (%s) at %s. It cannot be on a 2-day recheck before %s." % (
        t["id"], t.get("name") or "", args.kind, now.strftime("%H:%M"), brief.fmt_when(until, now)))
    for b in _cold_blocks_for(ws, subj, t["id"]):
        s, _ = brief.block_times(b, now.tzinfo)
        if b.get("start") and s is not None and now <= s < until:
            _out("WARN: the 2-day recheck booked %s (%s) includes %s and is now within 24 h of this exposure: "
                 "move it (plan move %s --start ISO), or it will not count." % (
                     brief.fmt_when(s, now), b.get("id"), t["id"], b.get("id")))
    return 0


def cmd_taught(args):
    ws = wsmod.from_args(args)
    subj = ws.subject(args.subject)
    _require_writable(ws, subj)
    t = subj.require_topic(args.topic)
    tid = t["id"]
    now = brief.now_in(ws)
    lo, hi = subj.cold_window()
    pair = args.block
    if pair and ws.get_block(pair) is None:
        raise UsageError("No block %s. List them with: plan list --subject %s" % (pair, subj.id))
    if not pair:
        lk = brief.session_lock_state(subj, now)
        if lk is not None and not lk["_unclosed"]:
            pair = lk.get("block")
    # Elapsed hours (through UTC), so the window is exactly lo-hi hours even
    # across a clock change, the same arithmetic as eligibility and plan check.
    wf = dates.plus(now, hours=lo)
    wt = dates.plus(now, hours=hi)
    window = {"from": _fmt(wf), "to": _fmt(wt)}
    created, updated, warn = None, [], []
    with ws.lock():
        subj.append_exposure({"v": 1, "topic": tid, "at": _fmt(now), "kind": "teach"})
        ts_all = subj.load_topics_state()
        row = ts_all.get(tid) or {}
        for k, v in learning.TOPIC_STATE_DEFAULTS.items():
            row.setdefault(k, copy.deepcopy(v))
        row["taught_at"] = _fmt(now)
        row["taught_by"] = args.by
        ts_all[tid] = row
        subj.save_topics_state(ts_all)

        blocks = ws.load_blocks()
        existing = []
        for b in _cold_blocks_for(ws, subj, tid, blocks):
            s = dates.try_parse_iso(b.get("start"))
            if s is not None and s < now:
                continue
            existing.append(b)
        if not existing:
            bid = ws.next_block_id(subj.id, wf.date())
            created = {"v": 1, "id": bid, "subject": subj.id, "kind": "cold", "start": None, "end": None,
                       "window": window, "protected": True, "measurement": False, "soft": False, "pair": pair,
                       "content": "cold:%s" % tid, "status": "planned", "cal": None, "moved_from": None,
                       "miss_reason": None}
            problems = schema.validate_block(created)
            if problems:
                raise UsageError("; ".join(problems))
            blocks.append(created)
            ws.save_blocks(blocks)
        else:
            for b in existing:
                if brief.block_topics(b) == [tid]:
                    b["window"] = dict(window)
                    if pair and not b.get("pair"):
                        b["pair"] = pair
                    updated.append(b)
                s = brief.to_local(b.get("start"), now.tzinfo)
                if s is not None and not (wf <= s <= wt):
                    warn.append(b)
            if updated:
                ws.save_blocks(blocks)
    _out("Taught: %s %s (by %s). 2-day recheck window: %s – %s." % (
        tid, t.get("name") or "", args.by, brief.fmt_when(wf, now), brief.fmt_when(wt, now)))
    on_demand = ws.schedule_mode() == "on_demand"
    if created:
        if on_demand:
            _out("Recheck booked as %s (unplaced; on-demand learner: leave it unplaced and name the window in "
                 "the close message)." % created["id"])
        else:
            _out("Recheck to place: %s. Put it in the first session inside the window: plan place %s --start ISO "
                 "--min N" % (created["id"], created["id"]))
    for b in updated:
        _out("Recheck %s: window moved to the new one (the last teaching resets it)." % b.get("id"))
    for b in warn:
        _out("WARN: the recheck booked %s (%s) is outside the new window: move it inside (plan move %s --start ISO)."
             % (brief.fmt_when(brief.to_local(b.get("start"), now.tzinfo), now), b.get("id"), b.get("id")))
    return 0


def cmd_override(args):
    ws = wsmod.from_args(args)
    subj = ws.subject(args.subject)
    _require_writable(ws, subj)
    said = " ".join((args.said or "").split())
    predict = " ".join((args.predict or "").split())
    if not said:
        raise UsageError("Give the learner's words, e.g. session override %s \"I know this, skip the theory\" "
                         "--predict \"items 1 to 4 right\"" % subj.id)
    if not predict:
        raise UsageError("--predict needs the learner's item-level prediction (never a total)")
    now = brief.now_in(ws)
    row = {"v": 1, "kind": "override", "subject": subj.id, "said": said, "predict": predict, "scored": None,
           "at": _fmt(now)}
    lk = brief.session_lock_state(subj, now)
    if lk is not None and not lk["_unclosed"] and lk.get("session_id"):
        row["session"] = lk["session_id"]
    with ws.lock():
        row = ledger.append_row(ws, row)
    _out("Override logged: %s. Prediction to score at marking: %s" % (row["id"], predict))
    return 0


# ==========================================================================
# close
# ==========================================================================

class Check(object):
    def __init__(self, code, name, status, detail, todo=None, by="claude", refs=None):
        self.code, self.name, self.status, self.detail = code, name, status, detail
        self.todo, self.by, self.refs = todo, by, list(refs or [])

    def line(self):
        return "%s %s %s: %s" % (self.status, self.code, self.name, self.detail)


def _mentions(text, ident):
    return bool(re.search(r"(?<![A-Za-z0-9-])%s(?![A-Za-z0-9-])" % re.escape(ident), text or ""))


def run_checks(ws, subj, lk, now, note):
    """Checks C1-C8 about the session since the lock start. Returns [Check]."""
    tz = now.tzinfo
    start = lk["_start"]
    day0 = start.date()
    day_start = datetime(day0.year, day0.month, day0.day, tzinfo=tz)
    today = now.date()
    sheets = subj.load_sheets()
    errors = subj.load_errors()
    exposures = subj.load_exposures()
    blocks = ws.load_blocks()
    rows = ws.load_ledger()
    names = {t["id"]: t.get("name") or t["id"] for t in subj.topics()}
    out = []

    def sat_on(s):
        return _date((s.get("sat") or {}).get("date"))

    taken = [s for s in sheets if s.get("status") != "void" and sat_on(s) and day0 <= sat_on(s) <= today]

    # C1 evidence
    missing = [s["id"] for s in taken if not s.get("evidence")]
    if missing:
        out.append(Check("C1", "evidence", "FAIL",
                         "no photo or file filed for: %s (run: scan ingest %s <id> <paths> or --typed FILE)"
                         % (", ".join(missing), subj.id),
                         todo="Send the photo or file of your answers for %s" % ", ".join(missing),
                         by="learner", refs=missing))
    else:
        out.append(Check("C1", "evidence", "PASS",
                         "%d sheet%s taken today, each with a photo or file" % (len(taken), "" if len(taken) == 1 else "s")
                         if taken else "no sheets taken today"))

    # C2 graded
    owed = []
    for r in ws.open_ledger_items(kind="owed", subject=subj.id, rows=rows):
        due = dates.try_parse_iso(r.get("due"))
        if due is not None and due <= now + timedelta(hours=C2_OWED_H):
            owed.append(r)
    bad, carried, pencils = [], [], []
    for s in taken:
        if s.get("status") == "graded":
            continue
        if s.get("type") in PENCIL_TYPES:
            pencils.append(s["id"])
            continue
        measuring = s.get("measures") is True or s.get("type") in schema.MEASURING_TYPES
        if measuring:
            bad.append("%s (measuring: grade it now)" % s["id"])
            continue
        if any(_mentions(r.get("what"), s["id"]) for r in owed):
            carried.append(s["id"])
            continue
        bad.append("%s (practice: grade it, or add a to-do due within 24 h naming it)" % s["id"])
    if bad:
        ids = [b.split(" ", 1)[0] for b in bad]
        out.append(Check("C2", "graded", "FAIL", "not graded: " + "; ".join(bad),
                         todo="Grade %s" % ", ".join(ids), refs=ids))
    elif not taken:
        out.append(Check("C2", "graded", "PASS", "nothing taken today"))
    elif len(pencils) == len(taken):
        out.append(Check("C2", "graded", "PASS", "nothing to grade: read-then-close sheets need no grading (%s)"
                         % ", ".join(pencils)))
    else:
        out.append(Check("C2", "graded", "PASS", "all graded" + (
            "; to-do within 24 h for %s" % ", ".join(carried) if carried else "") + (
            "; read-then-close sheets need no grading: %s" % ", ".join(pencils) if pencils else "")))

    # C3 errors
    opened = [e for e in errors if _date(e.get("opened")) and day0 <= _date(e.get("opened")) <= today]
    incomplete = []
    for e in opened:
        miss = []
        if e.get("kind") not in schema.ERROR_KINDS:
            miss.append("kind")
        if not str(e.get("mode") or "").strip():
            miss.append("mode")
        if not str(e.get("account") or "").strip():
            miss.append('account (or "no account")')
        if not e.get("next_due") and e.get("status") != "untreated":
            miss.append("due date")
        if miss:
            incomplete.append((e.get("id") or "?", miss))
    if incomplete:
        out.append(Check("C3", "errors", "FAIL", "; ".join("%s missing %s" % (i, ", ".join(m)) for i, m in incomplete),
                         todo="Complete today's mistake records (kind, type, your account, due date)",
                         refs=[i for i, _ in incomplete]))
    else:
        out.append(Check("C3", "errors", "PASS", "%d mistake%s opened today, each complete" % (
            len(opened), "" if len(opened) == 1 else "s") if opened else "no mistakes opened today"))

    # C4 cold booked
    lo, hi = subj.cold_window()
    taught = {}
    for x in exposures:
        if x.get("kind") != "teach":
            continue
        t = brief.to_local(x.get("at"), tz)
        if t is None or t < start or t > now + timedelta(minutes=1):
            continue
        if x.get("topic") not in taught or t > taught[x["topic"]]:
            taught[x.get("topic")] = t
    unbooked = []
    for tid, at in sorted(taught.items()):
        wf, wt = dates.plus(at, hours=lo), dates.plus(at, hours=hi)
        ok = False
        for b in _cold_blocks_for(ws, subj, tid, blocks):
            if brief.is_obligation(b):
                _, bt = brief.block_times(b, tz)
                if bt is None or bt >= now:
                    ok = True
            else:
                s = brief.to_local(b.get("start"), tz)
                if s is not None and wf <= s <= wt:
                    ok = True
        if not ok:
            unbooked.append((tid, wf, wt))
    if unbooked:
        out.append(Check("C4", "cold booked", "FAIL", "; ".join(
            "no 2-day recheck booked for %s (window %s – %s): run session taught %s %s, or place a cold block "
            "inside the window" % (tid, brief.fmt_when(wf, now), brief.fmt_when(wt, now), subj.id, tid)
            for tid, wf, wt in unbooked),
            todo="Book the 2-day recheck for today's new material", refs=[u[0] for u in unbooked]))
    else:
        out.append(Check("C4", "cold booked", "PASS",
                         "2-day recheck booked for %s" % ", ".join(sorted(taught)) if taught else "nothing taught today"))

    # C5 repair before cold
    untreated = {}
    for e in errors:
        if e.get("status") == "untreated" and e.get("topic"):
            untreated.setdefault(e["topic"], []).append(e.get("id") or "?")
    horizon = now + timedelta(hours=C5_HORIZON_H)
    clashes = []
    for b in blocks:
        if b.get("subject") != subj.id or b.get("kind") != "cold" or b.get("status") not in OPEN:
            continue
        s, e = brief.block_times(b, tz)
        if s is None:
            continue
        if s > horizon or (e is not None and e < now) or (e is None and s < now):
            continue
        for tid in brief.block_topics(b):
            if tid in untreated:
                clashes.append((b, s, tid))
    if clashes:
        out.append(Check("C5", "repair before cold", "FAIL", "; ".join(
            "the 2-day recheck %s (%s) includes %s, which has an unfixed mistake (%s): repair it first or move "
            "the recheck" % (("at " if b.get("start") else "window opening ") + brief.fmt_when(s, now), b.get("id"),
                             tid, ", ".join(untreated[tid])) for b, s, tid in clashes),
            todo="Fix the mistake before its 2-day recheck, or move the recheck",
            refs=sorted(set([c[0].get("id") for c in clashes] + [i for c in clashes for i in untreated[c[2]]]))))
    else:
        out.append(Check("C5", "repair before cold", "PASS",
                         "no 2-day recheck in the next %d h includes a topic with an unfixed mistake" % C5_HORIZON_H))

    # C6 promises
    texts = [note] if note else []
    texts += ledger.notes_since(subj, day_start)
    hits = sorted(set(m.group(1).lower() for t in texts for m in PROMISE_RE.finditer(t or "")))
    if hits:
        made = [r for r in rows if r.get("kind") == "owed" and r.get("subject") in (subj.id, None)
                and ledger.within(r.get("at"), day_start)]
        if made:
            out.append(Check("C6", "promises", "PASS", "'%s' in today's notes, and %d to-do%s created today" % (
                "', '".join(hits), len(made), "" if len(made) == 1 else "s")))
        else:
            out.append(Check("C6", "promises", "FAIL",
                             "'%s' in the close note or today's notes, and no to-do was created today: "
                             "ledger add owed --subject %s --what TEXT --due ISO" % ("', '".join(hits), subj.id),
                             todo="Put a date and time on the promise in today's note"))
    else:
        out.append(Check("C6", "promises", "PASS", "no promise words in today's notes"))

    # C7 views
    try:
        edited = brief.hand_edits(ws, [subj])
    except (DataError, OSError) as exc:
        edited = []
        out.append(Check("C7", "views", "FAIL", "could not prepare the views: %s" % exc,
                         todo="Refresh the study views"))
    else:
        if edited:
            out.append(Check("C7", "views", "FAIL",
                             "edited by hand since the last render: %s. Ask the learner, then render %s --force "
                             "(a .bak copy is kept)" % (", ".join(edited), subj.id),
                             todo="Refresh the study views (one was edited by hand)", refs=edited))
        else:
            out.append(Check("C7", "views", "PASS", "rendered by this close"))

    # C8 next sheets (INFO)
    nxt = _next_block(ws, subj, now, exclude=lk.get("block"), blocks=blocks)
    if nxt is None:
        out.append(Check("C8", "next sheets", "INFO", "no next block planned for %s" % subj.id))
    else:
        ready = [s["id"] for s in sheets if s.get("block") == nxt.get("id")
                 and s.get("status") in ("issued", "sat", "graded")]
        s, _ = brief.block_times(nxt, tz)
        if ready:
            out.append(Check("C8", "next sheets", "INFO", "the next block (%s, %s) has %d sheet%s ready: %s" % (
                brief.fmt_when(s, now), nxt.get("id"), len(ready), "" if len(ready) == 1 else "s", ", ".join(ready))))
        else:
            out.append(Check("C8", "next sheets", "INFO",
                             "the next block (%s, %s) has no sheet issued yet: build after the close message"
                             % (brief.fmt_when(s, now), nxt.get("id"))))
    return out


def _next_block(ws, subj, now, exclude=None, blocks=None):
    blocks = ws.load_blocks() if blocks is None else blocks
    tz = now.tzinfo
    best = None
    for b in blocks:
        if b.get("subject") != subj.id or not b.get("start") or b.get("status") not in OPEN:
            continue
        if exclude and b.get("id") == exclude:
            continue
        s = brief.to_local(b.get("start"), tz)
        if s is None or s <= now:
            continue
        if best is None or s < best[0]:
            best = (s, b)
    return best[1] if best else None


def _next_obligation(ws, subj, now, blocks=None):
    blocks = ws.load_blocks() if blocks is None else blocks
    best = None
    for b in blocks:
        if b.get("subject") != subj.id or not brief.is_obligation(b) or b.get("status") not in OPEN:
            continue
        f, t = brief.block_times(b, now.tzinfo)
        if t is None or t < now:
            continue
        if best is None or t < best[1]:
            best = (f, t, b)
    return best


def _log_defect(ws, subj, category, what, rule_fix, alt_type, alt_fix, now):
    if ledger.rule_fix_refused(ws, category):
        return ledger.add_defect(ws, subj.id, category, what, alt_type, alt_fix, at=now)
    return ledger.add_defect(ws, subj.id, category, what, "rule", rule_fix, at=now)


def _session_row(ws, subj, lk, now, note, status, todos, sheets):
    tz = now.tzinfo
    start = lk["_start"]
    atts = _attempts_since(subj, start, now, lk.get("session_id"))
    tallies = {"n": len(atts)}
    for v in schema.VERDICTS:
        tallies[v] = len([a for a in atts if a.get("verdict") == v])
    ids = []
    for a in atts:
        if a.get("sheet") and a["sheet"] not in ids:
            ids.append(a["sheet"])
    for s in sheets:
        d = _date((s.get("sat") or {}).get("date"))
        if d and start.date() <= d <= now.date() and s.get("status") != "void" and s.get("id") not in ids:
            ids.append(s["id"])
    source = "clock"
    end = now
    if lk["_unclosed"]:
        acts = [dates.try_parse_iso(a.get("at")) for a in atts]
        acts += [dates.try_parse_iso(x.get("at")) for x in subj.load_exposures()]
        acts = [t for t in acts if t is not None and start < t <= now]
        if acts:
            end, source = max(acts).astimezone(tz), "last_activity"
        else:
            end, source = min(lk["_planned_end"], now), "planned"
    elapsed = max(0, int(round((end - start).total_seconds() / 60.0)))
    P = int(lk["_planned_min"] or 0)
    block = ws.get_block(lk.get("block")) if lk.get("block") else None
    row = {"v": 1, "id": lk.get("session_id") or subj.next_session_id(), "block": lk.get("block"),
           "kind": lk.get("kind") or "teach",
           "planned": {"start": (block or {}).get("start") or _fmt(start), "min": P},
           "actual": {"start": _fmt(start), "end": _fmt(end), "elapsed_min": elapsed},
           "sheets": ids, "asks": tallies, "overrun_min": max(0, elapsed - P), "note": note,
           "closed": {"at": _fmt(now), "status": status}}
    if source != "clock":
        row["actual"]["time_source"] = source
    if todos:
        row["todos"] = [t["id"] for t in todos]
    return row


def _mark_block_done(ws, block_id):
    if not block_id:
        return False
    blocks = ws.load_blocks()
    for b in blocks:
        if b.get("id") == block_id and b.get("status") not in ("cancelled", "done"):
            b["status"] = "done"
            ws.save_blocks(blocks)
            return True
    return False


def cmd_close(args):
    ws = wsmod.from_args(args)
    subj = ws.resolve_subject(args.subject)
    _require_writable(ws, subj)
    note = " ".join((args.note or "").split())
    if len(note) > NOTE_MAX:
        raise UsageError("--note is %d characters; keep it to %d (details go in: note append %s session)"
                         % (len(note), NOTE_MAX, subj.id))
    defer = None
    if args.defer is not None:
        defer = " ".join(args.defer.split())
        if not defer:
            raise UsageError("--defer needs a reason, e.g. --defer \"photo of block B not available\"")
    now = brief.now_in(ws)
    plain = brief.is_plain(ws)
    with ws.lock():
        lk = brief.session_lock_state(subj, now)
        if lk is None:
            raise CheckFailed("No session is open for %s, so there is nothing to close." % subj.id)
        late = lk["_unclosed"]
        checks = run_checks(ws, subj, lk, now, note)
        for c in checks:
            _out(c.line())
        fails = [c for c in checks if c.status == "FAIL"]
        if fails and not defer:
            _out("Not closed: %d check%s failed; the lock stays. Fix each FAIL line and run session close again, "
                 "or add --defer \"<reason>\" to turn them into to-dos due in 24 h."
                 % (len(fails), "" if len(fails) == 1 else "s"))
            return 1
        todos, defects = [], []
        due = now + timedelta(hours=DEFER_DUE_H)
        for c in fails:
            todos.append(ledger.add_owed(ws, subj.id, c.todo, due, by=c.by, at=now,
                                         extra={"refs": c.refs, "why": defer, "check": c.code}))
        if any(c.code == "C6" for c in fails):
            defects.append(_log_defect(
                ws, subj, "promise_broken", "a promise in today's notes had no dated to-do at close",
                "every 'tomorrow' or 'later' gets ledger add owed with a due time before the close",
                "script", "session close turns the promise into a to-do due in 24 h (check C6 with --defer)", now))
        if late:
            hours = max(0.0, (now - lk["_planned_end"]).total_seconds() / 3600.0)
            defects.append(_log_defect(
                ws, subj, "late_close", "the session of %s was closed %.0f h after its planned end"
                % (brief.fmt_when(lk["_start"]), hours),
                "start the close at the close start printed by session open; the brief flags unclosed sessions",
                "planner", "a calendar reminder at each block's close start", now))
        status = "late" if late else ("with-todos" if todos else "same-day")
        sheets = subj.load_sheets()
        row = _session_row(ws, subj, lk, now, note, status, todos, sheets)
        problems = schema.validate_session(row)
        if problems:
            raise UsageError("Refused: the session row would be invalid: " + "; ".join(problems))
        subj.append_session(row)
        subj.remove_session_lock()
        block_done = _mark_block_done(ws, lk.get("block"))
        try:
            res = brief.render_subjects(ws, [subj], skip_edited=True)
            views = "Views rendered." if not res["skipped"] else (
                "Views rendered; %d edited by hand left as they are." % len(res["skipped"]))
        except (DataError, OSError, CheckFailed) as exc:
            views = "Views not refreshed (%s). Run: render %s" % (str(exc).split("\n")[0], subj.id)

    asks = row["asks"]
    parts = ["session of %d min (planned %d)" % (row["actual"]["elapsed_min"], row["planned"]["min"])]
    if asks["n"]:
        parts.append("%d question%s graded: %s" % (asks["n"], "" if asks["n"] == 1 else "s", ", ".join(
            "%d %s" % (asks[k], w) for k, w in VERDICT_WORDS if asks.get(k))))
    else:
        parts.append("no questions graded")
    parts.append({"same-day": "closed the same day", "late": "closed late",
                  "with-todos": "closed with %d to-do%s" % (len(todos), "" if len(todos) == 1 else "s")}[status])
    saved = "Saved: " + " · ".join(parts) + "."
    if defer and not fails:
        saved += " (Nothing needed deferring.)"
    _out(saved)
    for t in todos:
        what = brief.scrub_ids(t["what"]) if plain else "%s %s" % (t["id"], t["what"])
        _out("To do: %s (due %s)." % (what, brief.fmt_when(brief.to_local(t["due"], now.tzinfo), now)))
    for d in defects:
        words = {"late_close": "late close", "promise_broken": "a promise without a date"}.get(d["category"],
                                                                                            d["category"])
        _out("Logged as my mistake: %s." % words if plain else "Defect logged: %s %s (fix %s)." % (
            d["id"], d["category"], d["fix_type"]))
    nxt = _next_block(ws, subj, now)
    obl = _next_obligation(ws, subj, now)
    if nxt is not None:
        s, _ = brief.block_times(nxt, now.tzinfo)
        mins = brief.block_minutes(nxt)
        _out("Next: %s · %s%s." % (brief.fmt_when(s, now), brief.block_what(nxt, True, brief.topic_names(subj)),
                                   " · %d min" % mins if mins else ""))
    elif obl is not None:
        _out("Next: 2-day recheck, best between %s and %s." % (brief.fmt_when(obl[0], now),
                                                               brief.fmt_when(obl[1], now)))
    else:
        _out("Next: nothing booked for %s." % subj.title())
    extra = [views]
    if block_done and not plain:
        extra.append("Block %s marked done." % lk.get("block"))
    elif block_done:
        extra.append("The planned block is marked done.")
    _out(" ".join(extra))
    return 0
