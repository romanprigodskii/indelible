"""Grading (CONTRACT section 7.5).

    grade record <subject> <sheet-id> --from grades.json [--shaky]

What it does, in order:
  1. Checks the sheet: evidence of the whole sheet must be on file (a
     failure-gate photo alone is not enough), and the status must be taken
     (an ``issued`` sheet with evidence counts as taken). A sheet is graded
     once; a verdict is never amended afterwards.
  2. Checks the grades file against the sealed spec: every graded question
     exists, a miss that opens a mistake has a mode (and an account), a
     belief line never contains an accepted answer from the key, and a sheet
     with the Least-sure line says how it came back (``least_sure_line``:
     named, none or blank; named when a question is named).
  3. Appends one attempt per question. Topic and layer come from the spec
     (a question may carry its own ``topic``, e.g. one hidden-test group of a
     code task), the instrument from the sheet type, ``cold`` is true on cold
     sheets, and ``interval_h`` is the time from the topic's last warm
     exposure to the sitting. On a cold sheet, a question whose topic was seen
     in the 24 h before the sitting is marked ``contaminated``: recorded, but
     not counted (seen too recently).
  4. Moves re-served mistakes (origin ``error:`` or ``sentinel:``) on the
     ladder: all questions right -> pass, anything else -> fail. Only a cold,
     mixed or measuring sheet moves the ladder, and only when the mistake's
     topic was not seen in the 24 h before the sitting (the note says "not
     counted"). A repair, theory, example or drills sheet never does, and an
     untreated wrong idea is never moved (repair it first).
  5. Opens a mistake for each wrong, half or "don't know" question with a
     ``kind`` (and, with ``--shaky``, one for each item whose right answers
     are on the Least-sure line: they count toward the level once it comes
     back right, and an earlier recheck that then counts is closed). The
     question's key entry is copied, unread, to
     ``.indelible/keys/errors/<E-id>.json``.
  6. Closes the 2-day recheck block this sheet served (the sheet's linked
     block, else the open recheck whose window or time holds the sitting);
     later rechecks stay open. Any measuring sheet serves one through its
     ``cold:`` items: a cold sheet, a words recheck, the late-recheck probe of
     plan.md section 7 (a diagnostic, mock or checkpoint too). A ``cold:``
     item on a practice sheet serves nothing: it leaves the recheck open and
     the topic's ``last_cold`` unset. Nor does a topic with fewer than
     MIN_COLD_ASKS counted questions (a words recheck excepted): it can't be a
     cold pass, so the note says so and its recheck stays open. A practice sheet
     logs a ``drill`` exposure per topic, timed at the sitting, and moves the
     window of a 2-day recheck still to come, as session expose does; a
     measuring sheet logs none (feedback given afterwards is logged with
     ``session expose``). Then the sheet is marked graded and the levels are
     recomputed.

Output: the score with its label, the unnamed-wrong count (on a sheet with
the Least-sure line; "left blank" when it was), check lines, the mistakes
opened (ids only), ladder moves, level changes and the rechecks closed.
Nothing from the key is ever printed.
"""

import json
import re
from datetime import timedelta

from lib import CheckFailed, DataError, UsageError
from lib import dates, learning, schema
from lib import io as fio
from lib import ws as wsmod
from lib.cmd_brief import block_topics, exposure_lines, fmt_when, rebook_first_recheck
from lib.cmd_sheet import filed_asks
from lib.cmd_learning import (
    add_parser_once, error_status_phrase, fmt_changes, fmt_num, leaks_answer, new_error, out,
    read_key, recompute_levels, require_writable, seal_error_key,
)

ORIGIN_ERROR_RE = re.compile(r"^(error|sentinel):(E-[a-z0-9-]+-\d+)$")
COLD_ORIGIN_RE = re.compile(r"^cold:([A-Za-z0-9_-]+)$")
OPEN_BLOCK_STATUSES = ("planned", "synced", "missed?")
MISS_VERDICTS = ("wrong", "half", "dont_know")
SCORES = {"right": 1, "half": 0.5, "wrong": 0, "dont_know": 0, "skip": 0}
FUTURE_SLACK_MIN = 5
ISSUE_SLACK_MIN = 5       # a sitting time this far before the issue is a clock difference, not a slip
LEAST_SURE_MODE = "least-sure"
# Sheet types whose error:/sentinel: questions move the ladder (a measuring serve).
LADDER_TYPES = ("cold", "mixed") + tuple(schema.MEASURING_TYPES)
SERVED_SLACK_H = 2.0      # a sitting this close to a recheck block's time or window serves it
JUST_SAT_H = 3.0          # with no start or stop, a sheet graded this soon after its issue was sat just now


def register(subparsers):
    p = add_parser_once(subparsers, "grade", help="record the marking of a sheet")
    if p is None:
        return
    sp = p.add_subparsers(dest="grade_cmd", metavar="<record>")
    r = sp.add_parser("record", help="record verdicts for one sitting from a grades file")
    r.add_argument("subject")
    r.add_argument("sheet", metavar="sheet-id")
    r.add_argument("--from", dest="from_path", required=True, metavar="GRADES_JSON",
                   help="the grades file (run: indelible.py schema grades)")
    r.add_argument("--shaky", action="store_true",
                   help="right answers on the Least-sure line open a shaky mistake (ladder at +3 days)")
    r.set_defaults(func=cmd_grade_record)


# ==========================================================================
# Helpers
# ==========================================================================

def _load_grades(path):
    try:
        data = fio.read_json(path, default=None)
    except DataError as exc:
        raise UsageError(str(exc))
    if data is None:
        raise UsageError("No grades file at %s (or it is empty)." % path)
    return data


def _sat_just_now(sheet, day, now):
    """True when a sheet with no start or stop was plainly sat in this session: issued
    today, and graded within max(3 h, 3 x its minutes) of the issue. A sheet with no
    issue time on record (an older row) keeps the old fallback."""
    issued = dates.try_parse_iso(sheet.get("issued_at"))
    if issued is None:
        return True
    try:
        est = float(sheet.get("est_min") or 0)
    except (TypeError, ValueError):
        est = 0.0
    limit_h = max(JUST_SAT_H, 3 * est / 60.0)
    return (day == now.date() and issued.astimezone(now.tzinfo).date() == now.date()
            and dates.hours_from(issued, now) <= limit_h)


def sitting_time(ws, sheet, grades, now, needs_time=False):
    """(aware datetime of the sitting, sitting fields, end of the sitting) from the grades file, then the sheet row.

    With no start or stop time, the sitting is taken as now (today) or 12:00 (an
    earlier day), never before the sheet was issued. When ``needs_time`` (a
    recheck, or a re-served mistake: the time decides the 2-day window and the
    24-hour rule), that guess is made only for a sheet plainly sat in this
    session; otherwise it refuses (exit 2). A sitting more than ISSUE_SLACK_MIN
    minutes before the issue is refused too (a wrong date, or a 12-hour clock).
    """
    taken = sheet.get("sat") or {}
    day_s = grades.get("date") or taken.get("date")
    try:
        day = dates.to_date(day_s) if day_s else now.date()
    except ValueError:
        raise UsageError("The sitting date %r is not YYYY-MM-DD." % day_s)
    if day > now.date():
        raise UsageError("The sitting date %s is in the future." % dates.fmt_date(day))
    start = grades.get("start") or taken.get("start")
    stop = grades.get("stop") or taken.get("stop")
    tz = ws.tzinfo()
    try:
        start_dt = dates.at_time(day, start, tz) if start else None
        stop_dt = dates.at_time(day, stop, tz) if stop else None
    except ValueError as exc:
        raise UsageError("Bad start or stop time: %s" % exc)
    if start_dt is not None and stop_dt is not None and stop_dt < start_dt:
        stop_dt += timedelta(days=1)
    at = start_dt or stop_dt
    issued = dates.try_parse_iso(sheet.get("issued_at"))
    sid = sheet.get("id") or "?"
    if at is None:
        if needs_time and not _sat_just_now(sheet, day, now):
            raise UsageError(
                "Not recorded: %s was issued %s and has no start or stop time. The sitting time decides the "
                "2-day window and the 24-hour rule. Ask the learner when they started it, then add \"date\" and "
                "\"start\" to the grades file (or run: sheet sat %s %s --date YYYY-MM-DD --start HH:MM)."
                % (sid, dates.fmt_iso(issued.astimezone(tz)) if issued else "earlier",
                   sheet.get("subject") or "<subject>", sid))
        at = now if day == now.date() else dates.at_time(day, "12:00", tz)
        if issued is not None and at < issued and issued.astimezone(tz).date() == day:
            at = issued.astimezone(tz)  # a guess, so never before the sheet existed
    if issued is not None and at < dates.plus(issued, minutes=-ISSUE_SLACK_MIN):
        raise UsageError("The sitting time %s is before %s was issued (%s). Check the date and the start time "
                         "(24-hour clock)." % (dates.fmt_iso(at), sid, dates.fmt_iso(issued.astimezone(tz))))
    if at > dates.plus(now, minutes=FUTURE_SLACK_MIN):
        raise UsageError("The sitting time %s is later than now (%s)." % (dates.fmt_iso(at), dates.fmt_iso(now)))
    end = stop_dt or at
    return at, {"start": start, "stop": stop, "date": dates.fmt_date(day)}, end


def cold_topics_of(block):
    """Every topic of a block's ``cold:T04,T01`` content (the same parse as brief and plan)."""
    return block_topics(block)


def _serves(block, sit_at, tz):
    """True if a sitting at ``sit_at`` serves this recheck block (its time or window, with slack).

    A placed block is served near its time. One whose time passed before the
    sitting (it was not sat then) is also served by a sitting inside its window;
    one booked for later stays open."""
    slack = SERVED_SLACK_H
    s, e = dates.try_parse_iso(block.get("start")), dates.try_parse_iso(block.get("end"))
    if s is not None:
        e = e or s
        if dates.plus(s, hours=-slack) <= sit_at <= dates.plus(e, hours=slack):
            return True
        if e > sit_at:
            return False
    w = block.get("window") if isinstance(block.get("window"), dict) else {}
    f, t = dates.try_parse_iso(w.get("from")), dates.try_parse_iso(w.get("to"))
    if f is None or t is None:
        return False
    return dates.plus(f, hours=-slack) <= sit_at <= dates.plus(t, hours=slack)


def close_cold_obligations(ws, subject_id, topics, sit_at=None, sheet_block=None):
    """Mark done the recheck block this sitting served. Returns [(topic, block id)].

    The served block is the sheet's linked block when it is an open recheck
    holding one of ``topics``; otherwise every open recheck block of those
    topics whose time (or, for an obligation or a block whose time passed
    unsat, whose window) holds the sitting, within SERVED_SLACK_H hours. Later
    rechecks, booked for another day, stay open.
    """
    if not topics:
        return []
    blocks = ws.load_blocks()
    closed = []
    linked = None
    if sheet_block:
        for b in blocks:
            if (b.get("id") == sheet_block and b.get("subject") == subject_id and b.get("kind") == "cold"
                    and b.get("status") in OPEN_BLOCK_STATUSES and any(t in topics for t in cold_topics_of(b))):
                linked = b
    for b in blocks:
        if b.get("subject") != subject_id or b.get("kind") != "cold":
            continue
        if b.get("status") not in OPEN_BLOCK_STATUSES:
            continue
        hit = [t for t in cold_topics_of(b) if t in topics]
        if not hit:
            continue
        if linked is not None:
            if b is not linked:
                continue
        elif sit_at is not None and not _serves(b, sit_at, None):
            continue
        b["status"] = "done"
        closed.extend((t, b.get("id")) for t in hit)
    if closed:
        ws.save_blocks(blocks)
    return closed


def _num_score(verdict):
    return SCORES.get(verdict, 0)


# ==========================================================================
# grade record
# ==========================================================================

def cmd_grade_record(args):
    ws = wsmod.from_args(args)
    subj = ws.resolve_subject(args.subject)
    require_writable(ws, subj)
    grades = _load_grades(args.from_path)
    problems = schema.validate_grades(grades)
    if problems:
        raise UsageError("The grades file has problems:\n  " + "\n  ".join(problems))
    sid = args.sheet
    now = ws.now()
    today = now.date()

    with ws.lock():
        sheet = subj.get_sheet(sid)
        if sheet is None:
            raise UsageError("Unknown sheet %r in %s. List them with: indelible.py sheet show %s"
                             % (sid, subj.id, subj.id))
        status = sheet.get("status")
        if status == "graded":
            raise CheckFailed("%s is already graded (%s). A verdict is never amended after the record: "
                              "log a defect instead." % (sid, sheet.get("graded_at") or "earlier"))
        if status == "void":
            raise CheckFailed("%s was dropped (void); it cannot be graded." % sid)
        if not sheet.get("evidence"):
            raise CheckFailed("No evidence is filed for %s. File it first: indelible.py scan ingest %s %s "
                              "<photos> (or --typed FILE, or --transcript -)." % (sid, subj.id, sid))
        whole, gate = filed_asks(sheet)
        if not whole:
            raise CheckFailed("Only a failure-gate photo (%s) is filed for %s. A sheet is graded once, when the "
                              "whole sheet is back: file it first: indelible.py scan ingest %s %s <photos>."
                              % (", ".join(gate), sid, subj.id, sid))
        if status not in ("sat", "issued"):
            raise CheckFailed("%s is %s: only an issued sheet that was taken can be graded." % (sid, status))
        recorded = [a for a in subj.load_attempts(include_archive=True) if a.get("sheet") == sid]
        if recorded:
            raise CheckFailed("%d graded questions are already on file for %s; a sheet is graded once."
                              % (len(recorded), sid))
        spec = fio.read_json(subj.spec_path(sid), default=None)
        if not isinstance(spec, dict):
            raise UsageError("No sealed spec for %s at %s; build the sheet with: indelible.py sheet new"
                             % (sid, subj.rel(subj.spec_path(sid))))

        stype = sheet.get("type") or spec.get("type")
        instrument = schema.instrument_for_type(stype)
        measured = schema.measures(stype)
        prov = "measured" if measured else "practice"
        is_cold_sheet = stype == "cold"
        topic_layers = dict((t["id"], t.get("layer")) for t in subj.topics())
        ask_index = {}
        for it in spec.get("items") or []:
            for a in it.get("asks") or []:
                if a.get("id"):
                    ask_index[a["id"]] = (it, a)
        key = read_key(subj, sid)
        origins = [str(ask_index[g["ask"]][0].get("origin") or "") for g in grades["asks"] if g["ask"] in ask_index]
        needs_time = is_cold_sheet or any(COLD_ORIGIN_RE.match(o) or ORIGIN_ERROR_RE.match(o) for o in origins)
        sit_at, sat_fields, sit_end = sitting_time(ws, sheet, grades, now, needs_time=needs_time)
        exposures = subj.load_exposures()
        topics_state = subj.load_topics_state()
        deadline = subj.target_date()
        lock = subj.read_session_lock() or {}

        # ---- pass 1: check every question and build the rows (nothing written yet)
        bad, leaks = [], []
        # The closing Least-sure line: items named, "none" written, or left blank. A blank is
        # recorded as blank, never as "sure of everything": the unnamed-wrong share leaves it out.
        has_line = spec.get("least_sure") is True
        ls_line = grades.get("least_sure_line")
        if has_line and ls_line is None:
            if any(g.get("least_sure") is True for g in grades["asks"]):
                ls_line = "named"
            else:
                bad.append("%s ends with the Least-sure line: give least_sure_line \"none\" (the learner wrote "
                           "none) or \"blank\" (left empty)" % sid)
        elif not has_line and ls_line is not None:
            bad.append("%s has no Least-sure line: leave least_sure_line out" % sid)
        attempts, pending_errors, no_kind, notes = [], [], [], []
        shaky_items = {}      # (item n, topic) -> the one shaky mistake for its named right answers
        reserve = {}          # E-id -> [verdicts] for re-served mistakes
        reserve_dirty = set()  # E-ids with a contaminated question: not counted
        cold_topics = []
        practised_cold = []    # cold: items on a practice sheet: they serve no recheck
        contaminated_topics = []
        interval_cache = {}
        taken_ids = []
        for g in grades["asks"]:
            aid = g["ask"]
            if aid not in ask_index:
                bad.append("question %r is not on sheet %s" % (aid, sid))
                continue
            item, ask = ask_index[aid]
            topic = ask.get("topic") or item.get("topic")
            layer = ask.get("layer") or item.get("layer") or topic_layers.get(topic)
            verdict = g["verdict"]
            least_sure = bool(g.get("least_sure", False))
            check = g.get("check")
            if check is None:
                if verdict in ("skip", "dont_know") or not ask.get("check"):
                    check = "n/a"
                else:
                    bad.append("%s: give check (filled, missing, caught, failed, head or n/a)" % aid)
                    continue
            elif check != "n/a" and not ask.get("check"):
                # No check line was printed (probe, words, theory ...): a `missing`
                # here would count against check coverage for a check never asked for.
                bad.append("%s: this question had no check line; give check n/a (or leave it out)" % aid)
                continue
            origin = str(item.get("origin") or "new")
            kind = g.get("kind")
            mode = g.get("mode")
            account = g.get("account")
            error_id = None

            m_err = ORIGIN_ERROR_RE.match(origin)
            m_cold = COLD_ORIGIN_RE.match(origin)
            if m_cold:
                found = cold_topics if measured else practised_cold
                if m_cold.group(1) not in found:
                    found.append(m_cold.group(1))

            if topic not in interval_cache:
                ih = learning.hours_since_exposure(topic, exposures, sit_at) if topic else None
                interval_cache[topic] = round(ih, 1) if ih is not None else None
            warm = interval_cache[topic] is not None and interval_cache[topic] < learning.NO_EXPOSURE_H
            # Only a cold sheet's rows are marked contaminated (dropped from levels);
            # the 24-hour rule for the ladder holds on every sheet type below.
            dirty = bool(is_cold_sheet and warm)
            if dirty and topic not in contaminated_topics:
                contaminated_topics.append(topic)

            if m_err:
                error_id = m_err.group(2)
                reserve.setdefault(error_id, []).append(verdict)
                if warm:
                    reserve_dirty.add(error_id)
                if kind:
                    notes.append("%s re-served %s, so no new mistake was opened for it." % (aid, error_id))
            elif kind:
                if verdict == "skip":
                    notes.append("%s was left blank: blanks open no mistake." % aid)
                elif verdict == "right" and kind != "shaky":
                    bad.append("%s is right: only kind shaky applies to a right answer" % aid)
                else:
                    if not mode:
                        bad.append("%s: a mistake needs a mode (a taxonomy code, e.g. V or C)" % aid)
                    if not account:
                        if verdict in ("wrong", "half"):
                            bad.append("%s: a mistake needs the learner's account (or \"no account\")" % aid)
                        else:
                            account = "no account"
                    belief = g.get("belief")
                    if kind == "belief" and not belief:
                        bad.append("%s: kind belief needs a belief line (the wrong idea, never the answer)" % aid)
                    if belief and leaks_answer(belief, key):
                        leaks.append(aid)
                    entries = {aid: key[aid]} if aid in key else {}
                    pending_errors.append({
                        "ask": aid, "asks": [aid], "item": item.get("n"), "topic": topic, "kind": kind,
                        "mode": mode, "belief": belief, "account": account, "least_sure": least_sure,
                        "entries": entries,
                    })
            elif verdict == "right" and least_sure and args.shaky:
                # One shaky mistake per named item (and topic), not one per question: its right
                # answers come back together at +3 days, and count toward the level once they
                # come back right (learning.first_reserve_passed).
                pe = shaky_items.get((item.get("n"), topic))
                if pe is None:
                    pe = {"ask": aid, "asks": [], "item": item.get("n"), "topic": topic, "kind": "shaky",
                          "mode": mode or LEAST_SURE_MODE, "belief": g.get("belief"),
                          "account": account or "named on the Least-sure line", "least_sure": True,
                          "entries": {}}
                    shaky_items[(item.get("n"), topic)] = pe
                    pending_errors.append(pe)
                pe["asks"].append(aid)
                if aid in key:
                    pe["entries"][aid] = key[aid]
            elif verdict in MISS_VERDICTS:
                no_kind.append(aid)

            row = {
                "v": 1, "sheet": sid, "item": item.get("n"), "ask": aid, "topic": topic, "layer": layer,
                "instrument": instrument, "cold": is_cold_sheet, "interval_h": interval_cache[topic],
                "verdict": verdict, "score": _num_score(verdict), "check": check, "least_sure": least_sure,
                "mode": mode, "account": account, "error_id": error_id,
                "at": dates.fmt_iso(sit_at), "prov": prov, "origin": origin, "sheet_type": stype,
                "taught_by": (topics_state.get(topic) or {}).get("taught_by"),
                "graded_at": dates.fmt_iso(now),
            }
            if has_line and ls_line is not None:
                row["least_sure_line"] = ls_line
            if dirty:
                row["contaminated"] = True
            if lock.get("session_id"):
                row["session"] = lock["session_id"]
            attempts.append(row)

        if practised_cold:
            notes.append("%s: a 2-day recheck item on a %s sheet is practice, so it serves no recheck; the "
                         "booked recheck stays open." % (", ".join(practised_cold), stype))
        # A question with no entry is simply not recorded. That is right for a block cut
        # for time, a question not counted, one withdrawn or an untaught case on a recheck,
        # never for a page missed when transcribing; a note, not a refusal, since leaving one
        # out is often deliberate.
        graded = set(g["ask"] for g in grades["asks"])
        left_out = [aid for aid in ask_index if aid not in graded]
        if left_out:
            notes.append("no entry for %s in the grades file, so %s not recorded. Leaving a question out is "
                         "right only in the cases session-grade.md §8 lists; one left out by mistake can't be "
                         "added now: tell the learner and log a defect."
                         % (", ".join(left_out), "it was" if len(left_out) == 1 else "they were"))
        if leaks:
            raise CheckFailed("Not recorded: the belief line of %s contains an accepted answer from the key. "
                              "Describe the wrong idea without the answer." % ", ".join(leaks))
        if bad:
            raise UsageError("Not recorded; fix the grades file:\n  " + "\n  ".join(bad))
        if not attempts:
            raise UsageError("The grades file lists no questions.")

        # ---- pass 2: write
        errors = subj.load_errors()
        active_idx = dict((e.get("id"), i) for i, e in enumerate(errors))
        archived = {}
        for e in subj.load_errors(include_archive=True):
            if e.get("id") not in active_idx:
                archived[e.get("id")] = e

        ladder_lines = []
        for eid, verdicts in reserve.items():
            move = "pass" if all(v == "right" for v in verdicts) else "fail"
            fn = learning.pass_ if move == "pass" else learning.fail
            if stype not in LADDER_TYPES:
                notes.append("%s was practised on a %s sheet (with the fix in view): no ladder move. Its "
                             "recheck comes cold on a later sheet." % (eid, stype))
                continue
            if eid in reserve_dirty:
                notes.append("%s: not counted (its topic was seen in the 24 h before the sitting): no ladder "
                             "move." % eid)
                continue
            if eid in active_idx and errors[active_idx[eid]].get("status") == "untreated":
                ladder_lines.append("%s not moved: the wrong idea is not fixed yet (run: error repair %s %s)"
                                    % (eid, subj.id, eid))
                continue
            if eid in active_idx:
                i = active_idx[eid]
                errors[i] = fn(errors[i], today, deadline=deadline, today=today)
                ladder_lines.append("%s %s, %s" % (eid, "passed" if move == "pass" else "missed",
                                                    error_status_phrase(errors[i])))
            elif eid in archived:
                if move == "fail":
                    back = fn(archived[eid], today, deadline=deadline, today=today)
                    errors.append(back)
                    active_idx[eid] = len(errors) - 1
                    ladder_lines.append("%s missed its sentinel serve: back from the archive, %s"
                                        % (eid, error_status_phrase(back)))
                else:
                    ladder_lines.append("%s passed its sentinel serve (stays retired in the archive)" % eid)
            else:
                notes.append("%s is not on file: its questions were recorded, but no ladder move was made." % eid)

        created = []
        no_key = []
        for pe in pending_errors:
            eid = subj.next_error_id(taken=taken_ids)
            taken_ids.append(eid)
            # A mistake covering several questions of its item names the item only.
            one = pe["ask"] if len(pe["asks"]) == 1 else None
            row = new_error(eid, pe["topic"], pe["kind"], pe["mode"], pe["belief"], pe["account"], today,
                            deadline=deadline, today=today, sheet=sid, item=pe["item"], ask=one,
                            named_least_sure=pe["least_sure"], prov=prov)
            row["answer_ref"] = seal_error_key(subj, eid, pe["entries"])
            if not pe["entries"]:
                no_key.extend(pe["asks"])
            errors.append(row)
            created.append(row)
            for a in attempts:
                if a["ask"] in pe["asks"]:
                    a["error_id"] = eid
        for row in created:
            problems = schema.validate_error(row)
            if problems:
                raise DataError("Internal: a mistake row failed validation: " + "; ".join(problems))
        if created or ladder_lines:
            subj.save_errors(errors)

        for a in attempts:
            problems = schema.validate_attempt(a)
            if problems:
                raise DataError("Internal: an attempt row failed validation: " + "; ".join(problems))
            subj.append_attempt(a)

        sitting = dict(sheet.get("sat") or {})
        for k, v in sat_fields.items():
            if not sitting.get(k) and v:
                sitting[k] = v
        sheet["sat"] = sitting
        sheet["status"] = "graded"
        sheet["graded_at"] = dates.fmt_iso(now)
        subj.upsert_sheet(sheet)

        # A practice sheet is a warm exposure, timed when it was sat (not when it
        # is marked). A measuring sheet is none: feedback given afterwards is
        # logged by Claude with session expose.
        graded_topics = []
        if not measured:
            for a in attempts:
                if a["topic"] and a["topic"] not in graded_topics:
                    graded_topics.append(a["topic"])
            for t in graded_topics:
                subj.append_exposure({"v": 1, "topic": t, "at": dates.fmt_iso(sit_end), "kind": "drill"})

        served = [t for t in cold_topics if t not in contaminated_topics]
        # A cold pass counts toward a level only with MIN_COLD_ASKS counted questions on the
        # topic (learning.py). A sitting with fewer uses nothing up: its booking stays open and
        # last_cold stays as it was, so a 2-day recheck is still one in its window. Words
        # sheets don't feed levels, so they keep closing their booking.
        thin = []
        if instrument != "words":
            for t in served:
                n_counted = len([a for a in attempts if a["topic"] == t and learning.counts_toward_level(a)])
                if n_counted < learning.MIN_COLD_ASKS:
                    # Right answers named on the Least-sure line, with a shaky mistake opened for
                    # them: they count once it comes back right, at this sitting.
                    pending = len([a for a in attempts if a["topic"] == t and a["least_sure"]
                                   and a["verdict"] == "right" and a.get("error_id")
                                   and not learning.REASKED_RE.match(a["origin"])])
                    thin.append((t, n_counted, learning.needs_window(t, topics_state.get(t), exposures), pending))
            served = [t for t in served if t not in [x[0] for x in thin]]
        closed = close_cold_obligations(ws, subj.id, served, sit_at=sit_at, sheet_block=sheet.get("block"))

        # Which sittings count as cold passes is decided only by the level rules
        # (learning.compute_levels_from, from attempts.jsonl); level_basis names it.
        state = json.loads(json.dumps(topics_state))
        for t in served:
            state.setdefault(t, {})["last_cold"] = dates.fmt_iso(sit_at)
        old, levels, merged = recompute_levels(subj, topics_state=state, errors=errors)
        # A re-serve that comes back right lets the right answers named on the Least-sure line
        # that opened it count, at their own sitting (learning.first_reserve_passed). That can make
        # an earlier recheck the pass that raises its topic to 3: it served the topic, so set
        # last_cold to it and close the booking it served, or the brief would still offer it.
        confirmed = []
        for t, lv in sorted(levels.items()):
            fp = dates.try_parse_iso(lv.get("first_pass"))
            if (fp is None or fp >= sit_at or learning.level_rank(lv.get("level")) < 3
                    or learning.level_rank((topics_state.get(t) or {}).get("level")) >= 3):
                continue
            row = merged.setdefault(t, {})
            last = dates.try_parse_iso(row.get("last_cold"))
            if last is None or last < fp:
                row["last_cold"] = dates.fmt_iso(fp)
            closed += close_cold_obligations(ws, subj.id, [t], sit_at=fp)
            confirmed.append((t, fp))
        subj.save_topics_state(merged)
        changes = learning.level_changes(topics_state, levels)

        # The drill exposure moves a 2-day recheck still to come, as session expose does:
        # the window runs from the last warm exposure (CONTRACT 6.4), the sitting or a later
        # one already logged. The move itself is quiet; a placed recheck it leaves outside
        # the window, or within 24 h of the sitting, gets its WARN.
        moved_lines = []
        if graded_topics:
            logged = subj.load_exposures()
            for t in graded_topics:
                at = max(sit_end, learning.last_exposure(t, logged) or sit_end)
                rebooked = rebook_first_recheck(ws, subj, t, at)
                moved_lines += [ln for ln in exposure_lines(ws, subj, t, sit_end, rebooked) if ln.startswith("WARN")]

        # A 2-day recheck sat outside its window is a late recheck: the level
        # rules ignore it for level 3, but it still uses up the serve.
        late, again = [], []
        if is_cold_sheet:
            lo, hi = subj.cold_window()
            for t in served:
                ih = interval_cache.get(t)
                if ih is None or lo <= ih <= hi or not learning.needs_window(t, topics_state.get(t), exposures):
                    continue
                if learning.level_rank((levels.get(t) or {}).get("level")) >= 3:
                    continue  # the pass confirmed a 3p level, which needs no window
                late.append((t, ih))
            # A topic this recheck left below 3 comes back as a 2-day recheck after its next
            # warm exposure (learning.needs_rerecheck). One held below 3 only by a wrong idea
            # is released by its repair instead.
            for t in served:
                lv = levels.get(t) or {}
                if t in [x[0] for x in late] or lv.get("held") or learning.level_rank(lv.get("level")) >= 3:
                    continue
                if learning.has_first_serve_basis(t, exposures, topics_state.get(t)):
                    again.append((t, bool(learning.untreated_on(t, errors))))

    # ---- report (never anything from the key)
    n = len(attempts)
    pts = sum(a["score"] for a in attempts)
    label = "[measured n=%d]" % n if measured else "[practice]"
    out("%s graded: %s/%d (%d%%) %s" % (sid, fmt_num(pts), n, int(round(100.0 * pts / n)), label))
    if ls_line == "blank":
        out("Least-sure line: left blank")
    elif has_line:
        wrong = [a for a in attempts if a["verdict"] == "wrong"]
        unnamed = [a for a in wrong if not a["least_sure"]]
        out("Wrong answers not on the Least-sure line: %d of %d" % (len(unnamed), len(wrong)))
    with_lines = [a for a in attempts if a["check"] in learning.CHECK_LINE_VALUES]
    if with_lines:
        covered = len([a for a in with_lines if a["check"] in learning.WRITTEN_CHECKS])
        caught = len([a for a in with_lines if a["check"] == "caught"])
        line = "Check lines written: %d of %d; caught a mistake: %d" % (covered, len(with_lines), caught)
        failed = [a for a in with_lines if a["check"] == "failed"]
        if failed:
            # A check that failed on a right answer points at the check, its tolerance or the key.
            right = len([a for a in failed if a["verdict"] == "right"])
            line += "; failed, answer kept: %d%s" % (len(failed), " (%d of them right)" % right if right else "")
        head = [a for a in with_lines if a["check"] == "head"]
        if head:
            # A check done in the head is the learner's word, and no line is on the page to coach.
            missed = len([a for a in head if a["verdict"] in learning.CHECK_MISS_VERDICTS])
            line += "; checked in the head [self-report]: %d, %d missed" % (len(head), missed)
        out(line)
    if created:
        parts = []
        for e in created:
            if e["status"] == "untreated":
                parts.append("%s (%s, needs repair)" % (e["id"], e["kind"]))
            else:
                parts.append("%s (%s, due %s)" % (e["id"], e["kind"], e.get("next_due")))
        out("Mistakes opened: " + ", ".join(parts))
    else:
        out("Mistakes opened: none")
    if ladder_lines:
        out("Ladder: " + "; ".join(ladder_lines))
    if no_kind:
        out("Misses with no kind (no mistake opened): " + ", ".join(no_kind))
    if no_key:
        out("No key entry for %s: those mistakes have no answer on file." % ", ".join(no_key))
    out("Levels: " + (fmt_changes(changes, subj) if changes else "no change"))
    if closed:
        out("2-day recheck done: " + ", ".join("%s (%s)" % (t, b) for t, b in closed))
    if contaminated_topics:
        dirty = [a["ask"] for a in attempts if a.get("contaminated")]
        out("Not counted (seen too recently, in the 24 h before the sitting): %s on %s. Its 2-day recheck "
            "stays open." % (", ".join(dirty), ", ".join(contaminated_topics)))
    for line in moved_lines:
        out(line)
    for t, fp in confirmed:
        out("%s: its recheck of %s counts now that the right answers named on its Least-sure line came back "
            "right." % (t, fmt_when(fp.astimezone(now.tzinfo), now)))
    for t, n_counted, window_serve, pending in thin:
        why = "%s: %d counted question%s; a cold pass needs at least %d, so this sitting can't raise mastery" % (
            t, n_counted, "" if n_counted == 1 else "s", learning.MIN_COLD_ASKS)
        if pending and n_counted + pending >= learning.MIN_COLD_ASKS:
            why += " unless the %d right answer%s named on the Least-sure line come%s back right at +3 days" % (
                pending, "" if pending == 1 else "s", "s" if pending == 1 else "")
        if window_serve:
            closes = learning.window_closes(t, now, exposures, subj.cold_window())
            if closes is not None and closes > now:
                why += (". Its 2-day recheck stays open: serve it again, with at least %d questions, before %s"
                        % (learning.MIN_COLD_ASKS, fmt_when(closes.astimezone(now.tzinfo), now)))
            else:
                why += ". Its window has passed: it is a late recheck (plan.md §7)"
        out(why + ".")
    for t, fix_first in again:
        if fix_first:
            out("%s is below 3 after this recheck: it comes back as a 2-day recheck %s–%s h after its fix sheet "
                "(error repair logs it)." % (t, fmt_num(lo), fmt_num(hi)))
        else:
            out("%s is below 3 after this recheck: log the feedback on it (session expose %s %s --kind review), "
                "and it comes back as a 2-day recheck %s–%s h later." % (t, subj.id, t, fmt_num(lo), fmt_num(hi)))
    for t, ih in late:
        out("Not counted toward level 3: %s was sat at %s h, outside its %s–%s h window. Treat it as a late "
            "recheck [measured] and book a fresh one from now (plan.md §7)." % (t, fmt_num(ih), fmt_num(lo),
                                                                               fmt_num(hi)))
    for note in notes:
        out("Note: " + note)
    return 0
