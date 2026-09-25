"""Grading (CONTRACT section 7.5).

    grade record <subject> <sheet-id> --from grades.json [--shaky]

What it does, in order:
  1. Checks the sheet: evidence must be on file, and the status must be
     taken (an ``issued`` sheet with evidence counts as taken). A sheet
     is graded once; a verdict is never amended afterwards.
  2. Checks the grades file against the sealed spec: every graded question
     exists, a miss that opens a mistake has a mode (and an account), and a
     belief line never contains an accepted answer from the key.
  3. Appends one attempt per question. Topic and layer come from the spec
     (a question may carry its own ``topic``, e.g. one hidden-test group of a
     code task), the instrument from the sheet type, ``cold`` is true on cold
     sheets, and ``interval_h`` is the time from the topic's last warm
     exposure to the sitting. On a cold sheet, a question whose topic was seen
     in the 24 h before the sitting is marked ``contaminated``: recorded, but
     not counted (seen too recently).
  4. Moves re-served mistakes (origin ``error:`` or ``sentinel:``) on the
     ladder: all questions right -> pass, anything else -> fail. Only a
     measuring serve moves the ladder: a cold, mixed or measuring sheet, not
     contaminated. A repair, theory, example or drills sheet never does, and
     an untreated wrong idea is never moved (repair it first).
  5. Opens a mistake for each wrong, half or "don't know" question with a
     ``kind`` (and, with ``--shaky``, for right answers on the Least-sure
     line). The question's key entry is copied, unread, to
     ``.indelible/keys/errors/<E-id>.json``.
  6. Closes the 2-day recheck block this sheet served (the sheet's linked
     block, else the open recheck whose window or time holds the sitting);
     later rechecks stay open. A practice sheet logs a ``drill`` exposure per
     topic, timed at the sitting; a measuring sheet logs none (feedback given
     afterwards is logged with ``session expose``). Then the sheet is marked
     graded and the levels are recomputed.

Output: the score with its label, the unnamed-wrong count, check lines, the
mistakes opened (ids only), ladder moves, level changes and the rechecks
closed. Nothing from the key is ever printed.
"""

import json
import re
from datetime import timedelta

from lib import CheckFailed, DataError, UsageError
from lib import dates, learning, schema
from lib import io as fio
from lib import ws as wsmod
from lib.cmd_brief import block_topics
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
LEAST_SURE_MODE = "least-sure"
# Sheet types whose error:/sentinel: questions move the ladder (a measuring serve).
LADDER_TYPES = ("cold", "mixed") + tuple(schema.MEASURING_TYPES)
SERVED_SLACK_H = 2.0      # a sitting this close to a recheck block's time or window serves it


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


def sitting_time(ws, sheet, grades, now):
    """(aware datetime of the sitting, sitting fields, end of the sitting) from the grades file, then the sheet row."""
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
    if at is None:
        at = now if day == now.date() else dates.at_time(day, "12:00", tz)
    if at > dates.plus(now, minutes=FUTURE_SLACK_MIN):
        raise UsageError("The sitting time %s is later than now (%s)." % (dates.fmt_iso(at), dates.fmt_iso(now)))
    end = stop_dt or at
    return at, {"start": start, "stop": stop, "date": dates.fmt_date(day)}, end


def cold_topics_of(block):
    """Every topic of a block's ``cold:T04,T01`` content (the same parse as brief and plan)."""
    return block_topics(block)


def _serves(block, sit_at, tz):
    """True if a sitting at ``sit_at`` serves this recheck block (its time or window, with slack)."""
    slack = SERVED_SLACK_H
    s, e = dates.try_parse_iso(block.get("start")), dates.try_parse_iso(block.get("end"))
    if s is not None:
        e = e or s
        return dates.plus(s, hours=-slack) <= sit_at <= dates.plus(e, hours=slack)
    w = block.get("window") if isinstance(block.get("window"), dict) else {}
    f, t = dates.try_parse_iso(w.get("from")), dates.try_parse_iso(w.get("to"))
    if f is None or t is None:
        return False
    return dates.plus(f, hours=-slack) <= sit_at <= dates.plus(t, hours=slack)


def close_cold_obligations(ws, subject_id, topics, sit_at=None, sheet_block=None):
    """Mark done the recheck block this sitting served. Returns [(topic, block id)].

    The served block is the sheet's linked block when it is an open recheck
    holding one of ``topics``; otherwise every open recheck block of those
    topics whose time (or, for an obligation, whose window) holds the sitting,
    within SERVED_SLACK_H hours. Later rechecks, booked for another day, stay
    open.
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
        sit_at, sat_fields, sit_end = sitting_time(ws, sheet, grades, now)
        exposures = subj.load_exposures()
        topics_state = subj.load_topics_state()
        deadline = subj.target_date()
        lock = subj.read_session_lock() or {}

        # ---- pass 1: check every question and build the rows (nothing written yet)
        bad, leaks = [], []
        attempts, pending_errors, no_kind, notes = [], [], [], []
        reserve = {}          # E-id -> [verdicts] for re-served mistakes
        reserve_dirty = set()  # E-ids with a contaminated question: not counted
        cold_topics = []
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
                    bad.append("%s: give check (filled, missing, caught or n/a)" % aid)
                    continue
            origin = str(item.get("origin") or "new")
            kind = g.get("kind")
            mode = g.get("mode")
            account = g.get("account")
            error_id = None

            m_err = ORIGIN_ERROR_RE.match(origin)
            m_cold = COLD_ORIGIN_RE.match(origin)
            if m_cold and m_cold.group(1) not in cold_topics:
                cold_topics.append(m_cold.group(1))

            if topic not in interval_cache:
                ih = learning.hours_since_exposure(topic, exposures, sit_at) if topic else None
                interval_cache[topic] = round(ih, 1) if ih is not None else None
            dirty = bool(is_cold_sheet and interval_cache[topic] is not None
                         and interval_cache[topic] < learning.NO_EXPOSURE_H)
            if dirty and topic not in contaminated_topics:
                contaminated_topics.append(topic)

            if m_err:
                error_id = m_err.group(2)
                reserve.setdefault(error_id, []).append(verdict)
                if dirty:
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
                        "ask": aid, "item": item.get("n"), "topic": topic, "kind": kind, "mode": mode,
                        "belief": belief, "account": account, "least_sure": least_sure, "entries": entries,
                    })
            elif verdict == "right" and least_sure and args.shaky:
                entries = {aid: key[aid]} if aid in key else {}
                pending_errors.append({
                    "ask": aid, "item": item.get("n"), "topic": topic, "kind": "shaky",
                    "mode": mode or LEAST_SURE_MODE, "belief": g.get("belief"),
                    "account": account or "named on the Least-sure line", "least_sure": True,
                    "entries": entries,
                })
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
            if dirty:
                row["contaminated"] = True
            if lock.get("session_id"):
                row["session"] = lock["session_id"]
            attempts.append(row)

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
            row = new_error(eid, pe["topic"], pe["kind"], pe["mode"], pe["belief"], pe["account"], today,
                            deadline=deadline, today=today, sheet=sid, item=pe["item"], ask=pe["ask"],
                            named_least_sure=pe["least_sure"], prov=prov)
            row["answer_ref"] = seal_error_key(subj, eid, pe["entries"])
            if not pe["entries"]:
                no_key.append(pe["ask"])
            errors.append(row)
            created.append(row)
            for a in attempts:
                if a["ask"] == pe["ask"]:
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
        if not measured:
            graded_topics = []
            for a in attempts:
                if a["topic"] and a["topic"] not in graded_topics:
                    graded_topics.append(a["topic"])
            for t in graded_topics:
                subj.append_exposure({"v": 1, "topic": t, "at": dates.fmt_iso(sit_end), "kind": "drill"})

        served = [t for t in cold_topics if t not in contaminated_topics]
        closed = close_cold_obligations(ws, subj.id, served, sit_at=sit_at, sheet_block=sheet.get("block"))

        state = json.loads(json.dumps(topics_state))
        for t in served:
            rows = [a for a in attempts if a["topic"] == t and learning.counts_toward_level(a)]
            st = state.setdefault(t, {})
            st["last_cold"] = dates.fmt_iso(sit_at)
            if rows:
                pts = sum(a["score"] for a in rows)
                if pts / float(len(rows)) >= learning.PASS_PCT:
                    passes = st.setdefault("cold_passes", [])
                    passes.append({"at": dates.fmt_iso(sit_at), "sheet": sid,
                                   "score": "%s/%d" % (fmt_num(pts), len(rows))})
        old, levels, merged = recompute_levels(subj, topics_state=state, errors=errors)
        subj.save_topics_state(merged)
        changes = learning.level_changes(topics_state, levels)

    # ---- report (never anything from the key)
    n = len(attempts)
    pts = sum(a["score"] for a in attempts)
    label = "[measured n=%d]" % n if measured else "[practice]"
    out("%s graded: %s/%d (%d%%) %s" % (sid, fmt_num(pts), n, int(round(100.0 * pts / n)), label))
    wrong = [a for a in attempts if a["verdict"] == "wrong"]
    unnamed = [a for a in wrong if not a["least_sure"]]
    out("Wrong answers not on the Least-sure line: %d of %d" % (len(unnamed), len(wrong)))
    with_lines = [a for a in attempts if a["check"] in ("filled", "missing", "caught")]
    if with_lines:
        covered = len([a for a in with_lines if a["check"] in ("filled", "caught")])
        caught = len([a for a in with_lines if a["check"] == "caught"])
        out("Check lines written: %d of %d; caught a mistake: %d" % (covered, len(with_lines), caught))
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
    for note in notes:
        out("Note: " + note)
    return 0
