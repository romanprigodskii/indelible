"""Mistakes and topics (CONTRACT section 7.5).

    error list <subject> [--status S] [--due] [--topic T] [--json]
    error repair <subject> <E-id> [--sheet ID]
    error pass <subject> <E-id>
    error fail <subject> <E-id>
    error add <subject> --topic T --kind K --mode M --belief TEXT --account TEXT
              [--sheet ID --item N [--ask A]]
    topic add <subject> <T-id> --name N --layer L [--weight W] [--floor T ...]
              [--confusable T ...] [--scope in|out]
    topic show <subject> [--json]
    topic recompute <subject>
    glossary add <subject> <term> [--def TEXT] [--gloss TEXT] [--sheet ID]
    glossary list [subject] [--json]

The ladder rules live in ``lib.learning`` (section 6.1). Keys are never
printed: when a mistake comes from a sheet, the key entry for its question is
copied, unread, to ``.indelible/keys/errors/<E-id>.json``. A belief line that
contains an accepted answer from the key is refused, and the refusal names the
question only.

Levels depend on the mistakes too (a topic with an untreated wrong idea is
held below 3), so every command here that changes a mistake recomputes them.

The glossary (``data/glossary.jsonl``) holds the words the learner owns; a
sheet may use such a word with the resolution ``glossary`` (lint rule L4).

This module also holds small helpers shared with ``cmd_grade`` and
``cmd_stats`` (parser registration, the write guard for shadow subjects, key
handling, level formatting and the level recompute).
"""

import json
import re
import sys
import unicodedata

from lib import CheckFailed, UsageError
from lib import dates, learning, schema
from lib import io as fio
from lib import ws as wsmod

READ_ONLY_STATES = ("shadow", "legacy")
MIN_LEAK_LEN = 3
BELIEF_MAX = 120


# ==========================================================================
# Shared helpers (also used by cmd_grade and cmd_stats)
# ==========================================================================

def out(text=""):
    sys.stdout.write(text + "\n")


def warn(text):
    sys.stderr.write("indelible: %s\n" % text)


def add_parser_once(subparsers, name, **kw):
    """``subparsers.add_parser`` unless another module already registered ``name``."""
    choices = getattr(subparsers, "choices", None) or {}
    if name in choices:
        warn("command '%s' is already registered; %s did not add it again" % (name, __name__))
        return None
    return subparsers.add_parser(name, **kw)


def subject_state(ws, subj):
    entry = ws.subject_entry(subj.id) or {}
    return entry.get("state", "live")


def require_writable(ws, subj):
    """Refuse (exit 1) to write for a subject in shadow or legacy mode."""
    state = subject_state(ws, subj)
    if state in READ_ONLY_STATES:
        raise CheckFailed("%s is in %s mode: indelible writes nothing for it." % (subj.id, state))


def read_key(subj, sheet_id):
    """The sealed key of a sheet as a dict (ask id -> entry), or {}. Never printed."""
    try:
        data = fio.read_json(subj.key_path(sheet_id), default=None)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def accepted_strings(entries, min_len=MIN_LEAK_LEN):
    """Accepted answer strings of at least ``min_len`` characters in key entries."""
    found = []
    for entry in (entries or {}).values():
        if not isinstance(entry, dict):
            continue
        for s in entry.get("accept") or []:
            if isinstance(s, bool) or not isinstance(s, (str, int, float)):
                continue
            s = str(s).strip()
            if len(s) >= min_len:
                found.append(s)
    return found


def norm_text(text):
    """Case-folded, NFC, runs of whitespace as one space (for leak tests)."""
    text = unicodedata.normalize("NFC", "" if text is None else str(text)).casefold()
    return re.sub(r"\s+", " ", text).strip()


def leaks_answer(text, entries):
    """True if ``text`` contains an accepted answer (any case; as a substring, so
    an answer inside a longer word counts too, as CONTRACT 7.4 L8 says)."""
    if not text:
        return False
    low = norm_text(text)
    for s in accepted_strings(entries):
        if norm_text(s) in low:
            return True
    return False


def seal_error_key(subj, error_id, entries):
    """Copy key entries (ask id -> entry) to keys/errors/<E>.json. Returns the answer_ref."""
    if not entries:
        return None
    path = subj.error_key_path(error_id)
    fio.ensure_dir(path.parent)
    fio.write_json(path, entries, mode=0o600, backup=False)
    return ".indelible/keys/errors/%s.json" % error_id


def new_error(eid, topic, kind, mode, belief, account, day, deadline=None, today=None,
              sheet=None, item=None, ask=None, named_least_sure=False, prov="practice"):
    """A new error row placed on the ladder by ``learning.add``."""
    row = {
        "v": 1, "id": eid, "opened": dates.fmt_date(day), "sheet": sheet, "item": item, "ask": ask,
        "topic": topic, "kind": kind, "mode": mode, "belief": belief, "account": account,
        "named_least_sure": bool(named_least_sure), "status": None, "repair_at": None, "rung": 0,
        "next_due": None, "passes": [], "fails": [], "answer_ref": None, "prov": prov,
    }
    return learning.add(row, day, deadline=deadline, today=today)


def fmt_level(level):
    return str(level)


def fmt_num(x):
    x = float(x)
    return ("%d" % x) if x == int(x) else ("%.1f" % x)


def fmt_day(value):
    """``2026-10-15`` -> ``Thu 15 Oct``."""
    if not value:
        return "-"
    try:
        d = dates.to_date(value)
    except ValueError:
        return str(value)
    return "%s %d %s" % (dates.weekday_name(d), d.day, d.strftime("%b"))


def error_status_phrase(e):
    st = e.get("status")
    if st == "untreated":
        return "needs repair before it comes back"
    if st == "retired":
        return "retired"
    nd = e.get("next_due")
    return "rung %s, due %s" % (e.get("rung", 0), nd or "-")


def recompute_levels(subj, extra_attempts=None, topics_state=None, errors=None):
    """(old topics state, new levels, merged state) from every attempt incl. the archive.

    ``errors`` defaults to the active mistakes on file (untreated wrong ideas
    hold a topic below 3).
    """
    old = subj.load_topics_state() if topics_state is None else topics_state
    attempts = subj.load_attempts(include_archive=True) + list(extra_attempts or [])
    errs = subj.load_errors() if errors is None else errors
    levels = learning.compute_levels_from(attempts, subj.load(), errors=errs)
    merged = learning.merge_levels(old, levels)
    return old, levels, merged


def refresh_levels(subj):
    """Recompute and save the levels; returns the changes [(topic, old, new)]."""
    old, levels, merged = recompute_levels(subj)
    subj.save_topics_state(merged)
    return learning.level_changes(old, levels)


def fmt_changes(changes, subj=None):
    parts = []
    for tid, a, b in changes:
        parts.append("%s %s → %s" % (tid, fmt_level(a), fmt_level(b)))
    return ", ".join(parts)


def split_ids(values):
    """``["T01,T02", "T03"]`` -> ``["T01", "T02", "T03"]`` (order kept, no repeats)."""
    found = []
    for v in values or []:
        for part in str(v).split(","):
            part = part.strip()
            if part and part not in found:
                found.append(part)
    return found


def _find_error(errors, eid):
    for i, e in enumerate(errors):
        if e.get("id") == eid:
            return i
    return None


def _require_error(subj, errors, eid):
    idx = _find_error(errors, eid)
    if idx is None:
        archived = [e for e in subj.load_errors(include_archive=True) if e.get("id") == eid]
        if archived:
            raise CheckFailed("%s is archived (retired and compacted); it is no longer on the ladder." % eid)
        raise UsageError("Unknown mistake %s in %s. List them with: indelible.py error list %s"
                         % (eid, subj.id, subj.id))
    return idx


# ==========================================================================
# Registration
# ==========================================================================

def register(subparsers):
    p = add_parser_once(subparsers, "error", help="list mistakes and move them on the ladder")
    if p is not None:
        sp = p.add_subparsers(dest="error_cmd", metavar="<list|repair|pass|fail|add>")

        a = sp.add_parser("list", help="list the open and recently retired mistakes")
        a.add_argument("subject", nargs="?", default=None)
        a.add_argument("--status", choices=list(schema.ERROR_STATUSES), default=None)
        a.add_argument("--due", action="store_true", help="only mistakes due today or earlier")
        a.add_argument("--topic", default=None)
        a.add_argument("--json", action="store_true")
        a.set_defaults(func=cmd_error_list)

        a = sp.add_parser("repair", help="a wrong idea was fixed (repair sheet read and drilled)")
        a.add_argument("subject")
        a.add_argument("error_id", metavar="E-id")
        a.add_argument("--sheet", default=None, help="the repair sheet id")
        a.set_defaults(func=cmd_error_repair)

        a = sp.add_parser("pass", help="the mistake's re-serve was right: next rung")
        a.add_argument("subject")
        a.add_argument("error_id", metavar="E-id")
        a.set_defaults(func=cmd_error_pass)

        a = sp.add_parser("fail", help="the mistake's re-serve was missed: back to the start")
        a.add_argument("subject")
        a.add_argument("error_id", metavar="E-id")
        a.set_defaults(func=cmd_error_fail)

        a = sp.add_parser("add", help="open a mistake that did not come through grade record")
        a.add_argument("subject")
        a.add_argument("--topic", required=True)
        a.add_argument("--kind", required=True, choices=list(schema.ERROR_KINDS))
        a.add_argument("--mode", required=True, help="a code from the subject taxonomy, e.g. V or C")
        a.add_argument("--belief", required=True,
                       help="the wrong idea, at most 120 characters, never the correct answer")
        a.add_argument("--account", required=True, help="the learner's own words, or 'no account'")
        a.add_argument("--sheet", default=None, help="the sheet the question came from")
        a.add_argument("--item", type=int, default=None, help="the item number on that sheet")
        a.add_argument("--ask", default=None, help="one question of the item (default: all of its questions)")
        a.set_defaults(func=cmd_error_add)

    p = add_parser_once(subparsers, "topic", help="add topics and show their levels")
    if p is not None:
        sp = p.add_subparsers(dest="topic_cmd", metavar="<add|show|recompute>")

        a = sp.add_parser("add", help="add a topic to a subject")
        a.add_argument("subject")
        a.add_argument("topic_id", metavar="T-id")
        a.add_argument("--name", required=True)
        a.add_argument("--layer", required=True, choices=list(schema.LAYERS))
        a.add_argument("--weight", type=float, default=None)
        a.add_argument("--floor", nargs="+", default=[], metavar="T", help="topics this one builds on")
        a.add_argument("--confusable", nargs="+", default=[], metavar="T",
                       help="topics easily confused with this one (recorded both ways)")
        a.add_argument("--scope", choices=list(schema.TOPIC_SCOPES), default="in")
        a.set_defaults(func=cmd_topic_add)

        a = sp.add_parser("show", help="levels with their basis")
        a.add_argument("subject", nargs="?", default=None)
        a.add_argument("--json", action="store_true")
        a.set_defaults(func=cmd_topic_show)

        a = sp.add_parser("recompute", help="recompute every level from the graded questions")
        a.add_argument("subject", nargs="?", default=None)
        a.set_defaults(func=cmd_topic_recompute)

    p = add_parser_once(subparsers, "glossary", help="the words the learner owns (lint L4 resolution: glossary)")
    if p is not None:
        sp = p.add_subparsers(dest="glossary_cmd", metavar="<add|list>")
        a = sp.add_parser("add", help="record a word the learner owns (after it was taught and used)")
        a.add_argument("subject")
        a.add_argument("term")
        a.add_argument("--def", dest="definition", default=None, help="the meaning, in plain words")
        a.add_argument("--gloss", default=None, help="a gloss in the learner's first language")
        a.add_argument("--sheet", default=None, help="the sheet that taught it")
        a.set_defaults(func=cmd_glossary_add)
        a = sp.add_parser("list", help="list the owned words")
        a.add_argument("subject", nargs="?", default=None)
        a.add_argument("--json", action="store_true")
        a.set_defaults(func=cmd_glossary_list)


# ==========================================================================
# error list
# ==========================================================================

def _due_key(e):
    return (e.get("next_due") or "9999-99-99", e.get("id") or "")


def error_line(e, today=None):
    belief = e.get("belief") or ""
    if len(belief) > 70:
        belief = belief[:67] + "..."
    due = e.get("next_due") or "-"
    flag = ""
    if today is not None and learning.is_due(e, today):
        flag = " (due)"
    text = "%s  %s  %s  %s  %s  rung %s  next %s%s" % (
        e.get("id"), e.get("topic") or "-", e.get("kind") or "-", e.get("mode") or "-",
        e.get("status") or "-", e.get("rung", 0), due, flag)
    if belief:
        text += '  "%s"' % belief
    return text


def cmd_error_list(args):
    ws = wsmod.from_args(args)
    subj = ws.resolve_subject(args.subject)
    today = ws.today()
    errors = subj.load_errors()
    rows = errors
    if args.status:
        rows = [e for e in rows if e.get("status") == args.status]
    if args.topic:
        rows = [e for e in rows if e.get("topic") == args.topic]
    if args.due:
        rows = [e for e in rows if learning.is_due(e, today)]
    rows = sorted(rows, key=_due_key)
    if args.json:
        out(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    counts = {}
    for e in errors:
        counts[e.get("status")] = counts.get(e.get("status"), 0) + 1
    due_n = len([e for e in errors if learning.is_due(e, today)])
    head = "%s: %d mistake%s on file" % (subj.id, len(errors), "" if len(errors) == 1 else "s")
    parts = []
    if counts.get("untreated"):
        parts.append("%d need repair" % counts["untreated"])
    ladder = counts.get("spacing", 0) + counts.get("reopened", 0)
    if ladder:
        parts.append("%d on the ladder (%d due)" % (ladder, due_n))
    if counts.get("retired"):
        parts.append("%d retired" % counts["retired"])
    if parts:
        head += " · " + " · ".join(parts)
    out(head)
    if not rows:
        out("(none match)" if errors else "(none yet)")
        return 0
    for e in rows:
        out(error_line(e, today))
    return 0


# ==========================================================================
# error repair / pass / fail
# ==========================================================================

def cmd_error_repair(args):
    ws = wsmod.from_args(args)
    subj = ws.resolve_subject(args.subject)
    require_writable(ws, subj)
    now = ws.now()
    today = now.date()
    with ws.lock():
        errors = subj.load_errors()
        idx = _require_error(subj, errors, args.error_id)
        e = errors[idx]
        if e.get("status") != "untreated":
            raise CheckFailed("%s is not waiting for repair (status %s, %s). Only an untreated wrong idea "
                              "is repaired." % (e["id"], e.get("status"), error_status_phrase(e)))
        note = None
        if args.sheet and subj.get_sheet(args.sheet) is None:
            note = "Note: sheet %s is not on file in %s; recorded anyway." % (args.sheet, subj.id)
        new = learning.repair(e, now, deadline=subj.target_date(), today=today)
        if args.sheet:
            new["repair_sheet"] = args.sheet
        errors[idx] = new
        subj.save_errors(errors)
        if e.get("topic"):
            subj.append_exposure({"v": 1, "topic": e["topic"], "at": dates.fmt_iso(now), "kind": "repair"})
        changes = refresh_levels(subj)
    out("%s repaired: back on the ladder at rung 0; its recheck is due %s (%s), at least 12 h after the fix."
        % (new["id"], new.get("next_due"), fmt_day(new.get("next_due"))))
    if e.get("topic"):
        out("Exposure logged: %s (repair), so no cold serve on it for 24 h." % e["topic"])
    if changes:
        out("Levels: " + fmt_changes(changes, subj))
    if note:
        out(note)
    return 0


def _ladder_move(args, move):
    ws = wsmod.from_args(args)
    subj = ws.resolve_subject(args.subject)
    require_writable(ws, subj)
    today = ws.today()
    with ws.lock():
        errors = subj.load_errors()
        idx = _require_error(subj, errors, args.error_id)
        e = errors[idx]
        if move == "pass" and e.get("status") == "untreated":
            raise CheckFailed("%s is untreated: repair it first (indelible.py error repair %s %s)."
                              % (e["id"], subj.id, e["id"]))
        fn = learning.pass_ if move == "pass" else learning.fail
        new = fn(e, today, deadline=subj.target_date(), today=today)
        errors[idx] = new
        subj.save_errors(errors)
        changes = refresh_levels(subj)
    out("%s %s: %s." % (new["id"], "passed" if move == "pass" else "missed", error_status_phrase(new)))
    if changes:
        out("Levels: " + fmt_changes(changes, subj))
    return 0


def cmd_error_pass(args):
    return _ladder_move(args, "pass")


def cmd_error_fail(args):
    return _ladder_move(args, "fail")


# ==========================================================================
# error add
# ==========================================================================

def _item_entries(spec, key, item_n, ask_id):
    """(item dict, {ask id: key entry}) for one item of a sheet spec."""
    for it in (spec or {}).get("items") or []:
        if it.get("n") == item_n or str(it.get("n")) == str(item_n):
            asks = [a.get("id") for a in it.get("asks") or [] if a.get("id")]
            if ask_id:
                if ask_id not in asks:
                    raise UsageError("Question %s is not part of item %s." % (ask_id, item_n))
                asks = [ask_id]
            return it, {a: key[a] for a in asks if a in key}
    raise UsageError("Item %s is not on that sheet." % item_n)


def cmd_error_add(args):
    ws = wsmod.from_args(args)
    subj = ws.resolve_subject(args.subject)
    require_writable(ws, subj)
    subj.require_topic(args.topic)
    belief = (args.belief or "").strip()
    account = (args.account or "").strip()
    if not belief:
        raise UsageError("--belief is empty: describe the wrong idea (never the correct answer).")
    if len(belief) > BELIEF_MAX:
        raise UsageError("--belief is %d characters; the limit is %d." % (len(belief), BELIEF_MAX))
    if not account:
        raise UsageError("--account is empty: give the learner's words, or 'no account'.")
    if (args.item is not None or args.ask) and not args.sheet:
        raise UsageError("--item and --ask need --sheet.")
    now = ws.now()
    today = now.date()
    notes = []
    with ws.lock():
        entries, prov, sheet_row = {}, "practice", None
        if args.sheet:
            sheet_row = subj.get_sheet(args.sheet)
            if sheet_row is None:
                raise UsageError("Unknown sheet %r in %s." % (args.sheet, subj.id))
            if schema.measures(sheet_row.get("type")):
                prov = "measured"
            key = read_key(subj, args.sheet)
            if args.item is not None:
                spec = fio.read_json(subj.spec_path(args.sheet), default=None)
                if not isinstance(spec, dict):
                    raise UsageError("No sealed spec for %s, so its item %s cannot be found."
                                     % (args.sheet, args.item))
                it, entries = _item_entries(spec, key, args.item, args.ask)
                if it.get("topic") and it.get("topic") != args.topic:
                    notes.append("Note: item %s is on topic %s, not %s; recorded as %s."
                                 % (args.item, it.get("topic"), args.topic, args.topic))
                check_against = entries
            else:
                check_against = key
            if leaks_answer(belief, check_against):
                raise CheckFailed("The belief line contains an accepted answer from the key of %s. "
                                  "Describe the wrong idea without the answer." % args.sheet)
            if args.item is not None and not entries:
                notes.append("Note: no key entry for that question; the mistake has no answer on file.")
        errors = subj.load_errors()
        eid = subj.next_error_id()
        row = new_error(eid, args.topic, args.kind, args.mode, belief, account, today,
                        deadline=subj.target_date(), today=today, sheet=args.sheet, item=args.item,
                        ask=args.ask, named_least_sure=False, prov=prov)
        problems = schema.validate_error(row)
        if problems:
            raise UsageError("; ".join(problems))
        row["answer_ref"] = seal_error_key(subj, eid, entries)
        errors.append(row)
        subj.save_errors(errors)
        changes = refresh_levels(subj)
    if changes:
        notes.insert(0, "Levels: " + fmt_changes(changes, subj))
    if row["status"] == "untreated":
        out("%s opened: %s on %s (%s); it needs a repair sheet before it comes back." % (
            eid, args.kind, args.topic, args.mode))
    else:
        out("%s opened: %s on %s (%s); first recheck due %s (%s)." % (
            eid, args.kind, args.topic, args.mode, row.get("next_due"), fmt_day(row.get("next_due"))))
    for n in notes:
        out(n)
    return 0


# ==========================================================================
# topic add / show / recompute
# ==========================================================================

def cmd_topic_add(args):
    ws = wsmod.from_args(args)
    subj = ws.resolve_subject(args.subject)
    require_writable(ws, subj)
    tid = args.topic_id
    if not schema.TOPIC_ID_RE.match(tid or ""):
        raise UsageError("Topic id %r must be letters, digits, '_' or '-' (at most 32), e.g. T05." % tid)
    name = (args.name or "").strip()
    if not name:
        raise UsageError("--name is empty.")
    if args.weight is not None and args.weight < 0:
        raise UsageError("--weight must be 0 or more.")
    floor = split_ids(args.floor)
    confusable = split_ids(args.confusable)
    if tid in floor or tid in confusable:
        raise UsageError("A topic cannot be its own floor or confusable topic.")
    notes = []
    with ws.lock():
        cfg = subj.load(reload=True)
        topics = cfg.setdefault("topics", [])
        for t in topics:
            if isinstance(t, dict) and t.get("id") == tid:
                raise CheckFailed("Topic %s already exists in %s (%s). Change it with: indelible.py set %s "
                                  "topics.%s.<field> <json>" % (tid, subj.id, t.get("name"), subj.id, tid))
        known = [t.get("id") for t in topics if isinstance(t, dict)]
        unknown = [x for x in floor + confusable if x not in known]
        if unknown:
            notes.append("Note: not topics of %s yet: %s (kept; add them when known)." % (subj.id, ", ".join(unknown)))
        before = schema.validate_subject(cfg)
        weight = args.weight
        if weight is not None and weight == int(weight):
            weight = int(weight)
        topics.append({"id": tid, "name": name, "weight": weight, "layer": args.layer, "floor": floor,
                       "confusable_with": confusable, "scope": args.scope})
        mirrored = []
        for t in topics:
            if isinstance(t, dict) and t.get("id") in confusable:
                lst = t.setdefault("confusable_with", [])
                if tid not in lst:
                    lst.append(tid)
                    mirrored.append(t["id"])
        after = schema.validate_subject(cfg)
        fresh = [p for p in after if p not in before]
        if fresh:
            raise UsageError("Topic not added: " + "; ".join(fresh))
        subj.save(cfg)
        old, levels, merged = recompute_levels(subj)
        subj.save_topics_state(merged)
    desc = "%s added to %s: %s · %s" % (tid, subj.id, name, args.layer)
    if weight is not None:
        desc += " · weight %g" % weight
    if floor:
        desc += " · builds on %s" % ", ".join(floor)
    if confusable:
        desc += " · confusable with %s" % ", ".join(confusable)
    if args.scope != "in":
        desc += " · out of scope"
    out(desc)
    if mirrored:
        out("Also recorded the other way: %s now %s %s as confusable."
            % (", ".join(mirrored), "lists" if len(mirrored) == 1 else "list", tid))
    for n in notes:
        out(n)
    return 0


def _topic_rows(subj):
    state = subj.load_topics_state()
    attempts = subj.load_attempts(include_archive=True)
    levels = learning.compute_levels_from(attempts, subj.load(), errors=subj.load_errors())
    rows = []
    listed = [t["id"] for t in subj.topics()]
    for tid in listed + [k for k in levels if k not in listed]:
        t = subj.topic(tid) or {}
        st = state.get(tid) or {}
        lv = levels.get(tid) or {"level": 0, "level_basis": "no evidence yet"}
        rows.append({
            "id": tid, "name": t.get("name") or "", "layer": t.get("layer"), "scope": t.get("scope", "in"),
            "level": lv["level"], "level_basis": lv["level_basis"],
            "stored_level": st.get("level") if st else None,
            "taught_at": st.get("taught_at"), "taught_by": st.get("taught_by"), "last_cold": st.get("last_cold"),
        })
    return rows


def cmd_topic_show(args):
    ws = wsmod.from_args(args)
    subj = ws.resolve_subject(args.subject)
    rows = _topic_rows(subj)
    if args.json:
        out(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    out("%s (%s) · levels 0-5, computed from graded questions" % (subj.title(), subj.id))
    if not rows:
        out("(no topics yet; add one with: indelible.py topic add %s T01 --name ... --layer ...)" % subj.id)
        return 0
    stale = False
    for r in rows:
        line = "%s %s · %s · level %s · %s" % (r["id"], r["name"], r["layer"] or "-", fmt_level(r["level"]),
                                               r["level_basis"])
        if r["scope"] == "out":
            line += " · out of scope"
        if r["taught_at"]:
            line += " · taught %s" % dates.fmt_date(dates.try_parse_iso(r["taught_at"]) or r["taught_at"])
            if r["taught_by"]:
                line += " by %s" % r["taught_by"]
        if r["stored_level"] is not None and str(r["stored_level"]) != str(r["level"]):
            line += " (stored %s)" % fmt_level(r["stored_level"])
            stale = True
        out(line)
    if stale:
        out("Stored levels are out of date. Run: indelible.py topic recompute %s" % subj.id)
    return 0


def cmd_topic_recompute(args):
    ws = wsmod.from_args(args)
    subj = ws.resolve_subject(args.subject)
    require_writable(ws, subj)
    with ws.lock():
        old, levels, merged = recompute_levels(subj)
        subj.save_topics_state(merged)
    changes = learning.level_changes(old, levels)
    if changes:
        out("%s levels recomputed: %s" % (subj.id, fmt_changes(changes, subj)))
    else:
        out("%s levels recomputed: no change (%d topics)." % (subj.id, len(levels)))
    return 0


# ==========================================================================
# glossary add / list
# ==========================================================================

GLOSS_MAX = 300


def glossary_terms(subj):
    """Lowercase terms in the subject's glossary (the words the learner owns)."""
    out = set()
    for g in subj.load_glossary():
        t = " ".join(str(g.get("term") or "").lower().split())
        if t:
            out.add(t)
    return out


def cmd_glossary_add(args):
    ws = wsmod.from_args(args)
    subj = ws.resolve_subject(args.subject)
    require_writable(ws, subj)
    term = " ".join((args.term or "").split())
    if not term:
        raise UsageError("Give the word, e.g. glossary add %s paraphrase --def \"the same idea in other words\""
                         % subj.id)
    for flag, v in (("--def", args.definition), ("--gloss", args.gloss)):
        if v is not None and len(v) > GLOSS_MAX:
            raise UsageError("%s is longer than %d characters" % (flag, GLOSS_MAX))
    now = ws.now()
    key = term.lower()
    with ws.lock():
        rows = subj.load_glossary()
        found = None
        for r in rows:
            if " ".join(str(r.get("term") or "").lower().split()) == key:
                found = r
                break
        if found is None:
            found = {"v": 1, "term": term, "def": None, "gloss": None, "sheet": None,
                     "added": dates.fmt_iso(now)}
            rows.append(found)
            verb = "added"
        else:
            verb = "updated"
        if args.definition is not None:
            found["def"] = " ".join(args.definition.split()) or None
        if args.gloss is not None:
            found["gloss"] = " ".join(args.gloss.split()) or None
        if args.sheet is not None:
            found["sheet"] = args.sheet
        found["updated"] = dates.fmt_iso(now)
        subj.save_glossary(rows)
    out("Glossary %s: '%s' (%d word%s owned in %s). Sheets may now use it with the resolution glossary."
        % (verb, term, len(rows), "" if len(rows) == 1 else "s", subj.id))
    return 0


def cmd_glossary_list(args):
    ws = wsmod.from_args(args)
    subj = ws.resolve_subject(args.subject)
    rows = sorted(subj.load_glossary(), key=lambda r: str(r.get("term") or "").lower())
    if args.json:
        out(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        out("No words in the %s glossary yet. Add one with: glossary add %s <term> --def TEXT" % (subj.id, subj.id))
        return 0
    out("%s glossary: %d word%s the learner owns" % (subj.id, len(rows), "" if len(rows) == 1 else "s"))
    for r in rows:
        line = "- %s" % r.get("term")
        if r.get("gloss"):
            line += " (%s)" % r["gloss"]
        if r.get("def"):
            line += ": %s" % r["def"]
        out(line)
    return 0
