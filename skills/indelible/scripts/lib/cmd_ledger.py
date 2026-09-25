"""The ledger (to-dos, decisions, my mistakes, hypotheses) and append-only notes.

    ledger add owed --subject S --what TEXT --due ISO [--by learner|claude]
    ledger add decision --subject S --summary TEXT --why TEXT [--check-on DATE --rule TEXT --action TEXT]
    ledger add defect --subject S --category C --what TEXT --fix-type T --fix TEXT
    ledger add hypothesis --subject S --statement TEXT --rule TEXT
    ledger close <L-id> [--status done|dropped|scored] [--note TEXT]
    ledger list [--kind K] [--open] [--subject S] [--json]
    note append <subject> <name>        (text on stdin)

``ledger.jsonl`` is append-only: closing a row appends a ``status`` event and
the latest event for a ref wins. A defect whose category was already logged
once cannot be fixed by ``rule`` again: it needs a structural fix (template,
lint, script or planner).

Other modules may call ``append_row(ws, row)``, ``add_owed(...)``,
``add_defect(...)`` and ``rule_fix_refused(ws, category)``.
"""

import json
import re
import sys

from lib import CheckFailed, UsageError
from lib import dates, schema
from lib import io as fio
from lib import ws as wsmod

NOTE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,60}$")
BY = ["learner", "claude"]


def register(subparsers):
    p = subparsers.add_parser("ledger", help="to-dos, decisions, my mistakes and hypotheses (append-only)")
    sp = p.add_subparsers(dest="ledger_cmd", metavar="<add|close|list>")

    add = sp.add_parser("add", help="add a row")
    asp = add.add_subparsers(dest="ledger_kind", metavar="<owed|decision|defect|hypothesis>")

    a = asp.add_parser("owed", help="a dated to-do (a promise)")
    a.add_argument("--subject", default=None)
    a.add_argument("--what", required=True)
    a.add_argument("--due", required=True, help="date and time, e.g. 2026-10-20T20:00+01:00")
    a.add_argument("--by", choices=BY, default="learner")
    a.set_defaults(func=cmd_add_owed)

    a = asp.add_parser("decision", help="a decision, optionally with a pre-registered safeguard")
    a.add_argument("--subject", default=None)
    a.add_argument("--summary", required=True)
    a.add_argument("--why", required=True, help="the learner's own words")
    a.add_argument("--by", choices=BY, default="learner")
    a.add_argument("--check-on", dest="check_on", default=None, help="YYYY-MM-DD")
    a.add_argument("--rule", default=None, help="what result fires the safeguard")
    a.add_argument("--action", default=None, help="what happens if it fires")
    a.set_defaults(func=cmd_add_decision)

    a = asp.add_parser("defect", help="my mistake (Claude's), with its fix")
    a.add_argument("--subject", default=None)
    a.add_argument("--category", required=True, choices=schema.DEFECT_CATEGORIES)
    a.add_argument("--what", required=True)
    a.add_argument("--fix-type", dest="fix_type", required=True, choices=schema.FIX_TYPES)
    a.add_argument("--fix", required=True)
    a.set_defaults(func=cmd_add_defect)

    a = asp.add_parser("hypothesis", help="a change to test, with its decision rule")
    a.add_argument("--subject", default=None)
    a.add_argument("--statement", required=True)
    a.add_argument("--rule", required=True, help="the result that decides it")
    a.set_defaults(func=cmd_add_hypothesis)

    c = sp.add_parser("close", help="close a row (appends a status event)")
    c.add_argument("ref", metavar="L-id")
    c.add_argument("--status", choices=schema.LEDGER_CLOSE_STATUSES, default="done")
    c.add_argument("--note", default=None)
    c.set_defaults(func=cmd_close)

    ls = sp.add_parser("list", help="list rows with their latest status")
    ls.add_argument("--kind", choices=[k for k in schema.LEDGER_KINDS if k != "status"], default=None)
    ls.add_argument("--open", action="store_true", help="only rows that are still open")
    ls.add_argument("--subject", default=None)
    ls.add_argument("--json", action="store_true")
    ls.set_defaults(func=cmd_list)

    p = subparsers.add_parser("note", help="append-only notes")
    nsp = p.add_subparsers(dest="note_cmd", metavar="<append>")
    n = nsp.add_parser("append", help="append stdin to <subject>/notes/<name>.md under a time heading")
    n.add_argument("subject")
    n.add_argument("name", help="note file name, e.g. session, review, fatigue, explanations")
    n.set_defaults(func=cmd_note_append)


def _out(text=""):
    sys.stdout.write(text + "\n")


# ==========================================================================
# Shared helpers (used by cmd_session too)
# ==========================================================================

def _now(ws):
    from lib import cmd_brief
    return cmd_brief.now_in(ws)


def _text(value, name, max_len=None):
    v = " ".join((value or "").split())
    if not v:
        raise UsageError("--%s must not be empty" % name)
    if max_len and len(v) > max_len:
        raise UsageError("--%s is %d characters; keep it to %d" % (name, len(v), max_len))
    return v


def _subject_id(ws, sid):
    if sid in (None, ""):
        return None
    return ws.subject(sid).id  # raises UsageError for an unknown subject


def append_row(ws, row):
    """Validate and append one ledger row (the caller holds the write lock). Returns the row."""
    row = dict(row)
    row.setdefault("v", 1)
    if row.get("kind") != "status" and not row.get("id"):
        row["id"] = ws.next_ledger_id()
    problems = schema.validate_ledger(row)
    if problems:
        raise UsageError("Refused: the ledger row would be invalid: " + "; ".join(problems))
    ws.append_ledger(row)
    return row


def prior_defects(ws, category, rows=None):
    rows = ws.load_ledger(include_archive=True) if rows is None else rows
    return [r for r in rows if r.get("kind") == "defect" and r.get("category") == category]


def rule_fix_refused(ws, category, rows=None):
    """True when this category was logged before, so ``fix_type=rule`` is not enough again."""
    return bool(prior_defects(ws, category, rows))


def add_owed(ws, subject, what, due, by="learner", at=None, extra=None):
    row = {"v": 1, "kind": "owed", "subject": subject, "by": by, "what": what,
           "due": dates.fmt_iso(due), "at": dates.fmt_iso(at or _now(ws))}
    row.update(extra or {})
    return append_row(ws, row)


def add_defect(ws, subject, category, what, fix_type, fix, at=None, extra=None):
    """Append a defect. Raises CheckFailed if fix_type is rule for a repeat category."""
    if fix_type == "rule" and rule_fix_refused(ws, category):
        earlier = prior_defects(ws, category)
        raise CheckFailed(
            "Refused: '%s' was already logged (%s). A repeat needs a structural fix, not a rule: "
            "--fix-type template, lint, script or planner." % (category, ", ".join(
                "%s fix_type %s" % (r.get("id"), r.get("fix_type")) for r in earlier[-3:])))
    row = {"v": 1, "kind": "defect", "subject": subject, "category": category, "what": what,
           "fix_type": fix_type, "fix": fix, "at": dates.fmt_iso(at or _now(ws))}
    row.update(extra or {})
    return append_row(ws, row)


def _parse_due(value, now):
    text = (value or "").strip()
    if dates.is_date(text):
        raise UsageError("--due needs a time as well as a date, e.g. %sT20:00%s" % (text, dates.fmt_offset(now)))
    try:
        return dates.parse_iso(text, tz=now.tzinfo).astimezone(now.tzinfo)
    except ValueError:
        raise UsageError("--due must be an ISO date and time, e.g. 2026-10-20T20:00+01:00 (got %r)" % value)


def _fmt(dt_str, now):
    from lib import cmd_brief
    dt = cmd_brief.to_local(dt_str, now.tzinfo)
    return cmd_brief.fmt_when(dt, now) if dt else (dt_str or "?")


# ==========================================================================
# ledger add
# ==========================================================================

def cmd_add_owed(args):
    ws = wsmod.from_args(args)
    now = _now(ws)
    sid = _subject_id(ws, args.subject)
    what = _text(args.what, "what", 300)
    due = _parse_due(args.due, now)
    with ws.lock():
        row = add_owed(ws, sid, what, due, by=args.by, at=now)
    note = " (already past)" if due < now else ""
    _out("Added %s: to do%s, due %s%s: %s" % (row["id"], " for " + sid if sid else "", _fmt(row["due"], now),
                                              note, what))
    return 0


def cmd_add_decision(args):
    ws = wsmod.from_args(args)
    now = _now(ws)
    sid = _subject_id(ws, args.subject)
    summary = _text(args.summary, "summary", 300)
    why = _text(args.why, "why", 500)
    sg_parts = [args.check_on, args.rule, args.action]
    row = {"v": 1, "kind": "decision", "subject": sid, "by": args.by, "summary": summary, "why": why,
           "at": dates.fmt_iso(now)}
    if any(x is not None for x in sg_parts):
        if not all(x not in (None, "") for x in sg_parts):
            raise UsageError("A safeguard needs all three: --check-on DATE --rule TEXT --action TEXT")
        if not dates.is_date(args.check_on):
            raise UsageError("--check-on must be a date YYYY-MM-DD (got %r)" % args.check_on)
        row["safeguard"] = {"check_on": args.check_on, "rule": _text(args.rule, "rule", 300),
                            "action": _text(args.action, "action", 300)}
    with ws.lock():
        row = append_row(ws, row)
    extra = ""
    if row.get("safeguard"):
        extra = "; safeguard armed, checked on %s" % row["safeguard"]["check_on"]
    _out("Added %s: decision%s: %s%s" % (row["id"], " for " + sid if sid else "", summary, extra))
    return 0


def cmd_add_defect(args):
    ws = wsmod.from_args(args)
    now = _now(ws)
    sid = _subject_id(ws, args.subject)
    what = _text(args.what, "what", 300)
    fix = _text(args.fix, "fix", 300)
    with ws.lock():
        row = add_defect(ws, sid, args.category, what, args.fix_type, fix, at=now)
    n = len(prior_defects(ws, args.category))
    _out("Added %s: my mistake (%s, fix: %s). %s" % (
        row["id"], args.category, args.fix_type,
        "First time in this category." if n <= 1 else "This category has now been logged %d times." % n))
    return 0


def cmd_add_hypothesis(args):
    ws = wsmod.from_args(args)
    now = _now(ws)
    sid = _subject_id(ws, args.subject)
    row = {"v": 1, "kind": "hypothesis", "subject": sid, "statement": _text(args.statement, "statement", 300),
           "rule": _text(args.rule, "rule", 300), "at": dates.fmt_iso(now)}
    with ws.lock():
        row = append_row(ws, row)
    _out("Added %s: hypothesis: %s (decided by: %s)" % (row["id"], row["statement"], row["rule"]))
    return 0


# ==========================================================================
# ledger close / list
# ==========================================================================

def cmd_close(args):
    ws = wsmod.from_args(args)
    now = _now(ws)
    ref = (args.ref or "").strip()
    if not schema.LEDGER_ID_RE.match(ref):
        raise UsageError("Expected a ledger id like L-0004 (got %r)" % args.ref)
    with ws.lock():
        rows = ws.load_ledger(include_archive=True)
        target = None
        for r in rows:
            if r.get("id") == ref and r.get("kind") != "status":
                target = r
        if target is None:
            raise UsageError("No ledger row %s. List them with: ledger list" % ref)
        latest = ws.ledger_status(rows).get(ref)
        if latest and latest.get("status") not in (None, "open"):
            raise CheckFailed("%s is already %s (%s). Nothing was changed." % (
                ref, latest.get("status"), latest.get("at")))
        row = {"v": 1, "kind": "status", "ref": ref, "status": args.status, "at": dates.fmt_iso(now)}
        if args.note:
            row["note"] = " ".join(args.note.split())
        append_row(ws, row)
    _out("Closed %s (%s): %s" % (ref, args.status, target.get("what") or target.get("summary")
                                 or target.get("statement") or target.get("said") or target.get("kind")))
    return 0


def _row_text(r):
    k = r.get("kind")
    if k == "owed":
        return r.get("what") or ""
    if k == "decision":
        return r.get("summary") or ""
    if k == "defect":
        return "%s: %s (fix %s: %s)" % (r.get("category"), r.get("what"), r.get("fix_type"), r.get("fix"))
    if k == "hypothesis":
        return "%s (rule: %s)" % (r.get("statement"), r.get("rule"))
    if k == "override":
        return '"%s" predict: %s' % (r.get("said"), r.get("predict"))
    return ""


def cmd_list(args):
    ws = wsmod.from_args(args)
    now = _now(ws)
    sid = _subject_id(ws, args.subject)
    rows = ws.load_ledger()
    status = ws.ledger_status(rows)
    out = []
    for r in rows:
        if r.get("kind") == "status" or not r.get("id"):
            continue
        if args.kind and r.get("kind") != args.kind:
            continue
        if sid and r.get("subject") not in (sid, None):
            continue
        st = status.get(r["id"])
        cur = st.get("status") if st else "open"
        if args.open and cur not in (None, "open"):
            continue
        out.append((r, cur or "open", st))
    if args.json:
        rows_out = []
        for r, cur, st in out:
            d = dict(r)
            d["_status"] = cur
            if st and st.get("note"):
                d["_status_note"] = st.get("note")
            rows_out.append(d)
        _out(json.dumps(rows_out, ensure_ascii=False, indent=2))
        return 0
    if not out:
        _out("No ledger rows match.")
        return 0
    for r, cur, st in out:
        parts = [r["id"], r.get("kind")]
        if r.get("subject"):
            parts.append(r["subject"])
        if r.get("kind") == "owed" and r.get("due"):
            due = dates.try_parse_iso(r["due"])
            parts.append(("OVERDUE " if cur == "open" and due is not None and due < now else "due ")
                         + _fmt(r["due"], now))
        sg = r.get("safeguard") or {}
        if sg.get("check_on"):
            parts.append("check on %s" % sg["check_on"])
        parts.append(_row_text(r))
        parts.append("[%s]" % cur)
        _out(" · ".join(str(p) for p in parts if p))
    return 0


# ==========================================================================
# note append
# ==========================================================================

def _read_stdin():
    buf = getattr(sys.stdin, "buffer", None)
    if buf is not None:
        data = buf.read()
        text = data.decode("utf-8-sig", errors="replace")
    else:
        text = sys.stdin.read()
    return text.replace("\r\n", "\n").replace("\r", "\n")


def cmd_note_append(args):
    ws = wsmod.from_args(args)
    subj = ws.subject(args.subject)
    name = args.name[:-3] if args.name.endswith(".md") else args.name
    if not NOTE_NAME_RE.match(name or ""):
        raise UsageError("Note name %r: use letters, digits, - and _ (e.g. session, review, explanations)" % args.name)
    text = _read_stdin().strip("\n")
    if not text.strip():
        raise UsageError("Nothing on stdin: pipe the note text in, e.g. echo \"...\" | indelible.py note append %s %s"
                         % (subj.id, name))
    now = _now(ws)
    path = subj.notes_path(name)
    with ws.lock():
        fio.ensure_dir(path.parent)
        exists = path.exists() and path.stat().st_size > 0
        chunk = ("\n" if exists else "") + "## %s\n\n%s\n" % (dates.fmt_iso(now), text.rstrip())
        if exists:
            with open(str(path), "rb") as fh:
                fh.seek(-1, 2)
                if fh.read(1) != b"\n":
                    chunk = "\n" + chunk
        with open(str(path), "a", encoding="utf-8", newline="\n") as fh:
            fh.write(chunk)
            fh.flush()
    n = len(text.split("\n"))
    _out("Noted in %s (%d line%s)." % (ws.rel(path), n, "" if n == 1 else "s"))
    return 0


# ==========================================================================
# Notes helpers (used by session close)
# ==========================================================================

NOTE_HEAD_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)\s*$")


def notes_since(subj, since):
    """Text of every note section whose timestamp heading is at or after ``since``."""
    out = []
    if not subj.notes_dir.exists():
        return out
    for p in sorted(subj.notes_dir.glob("*.md")):
        text = fio.read_text(p) or ""
        sections, cur_at, buf = [], None, []
        for line in text.split("\n"):
            m = NOTE_HEAD_RE.match(line)
            if m:
                sections.append((cur_at, buf))
                cur_at, buf = dates.try_parse_iso(m.group(1)), []
            else:
                buf.append(line)
        sections.append((cur_at, buf))
        for at, lines in sections:
            if at is not None and at >= since:
                out.append("\n".join(lines))
    return out


def within(ts, lo, hi=None):
    """True if the ISO time ``ts`` is at or after ``lo`` (and at or before ``hi``)."""
    t = dates.try_parse_iso(ts)
    if t is None or t < lo:
        return False
    return hi is None or t <= hi
