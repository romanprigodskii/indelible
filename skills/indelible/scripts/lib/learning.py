"""Learning logic shared by every command.

Everything above the "Loader helpers" line is a pure function: data in, data
out, no clock and no files. Times are ISO strings or datetimes; dates are
``YYYY-MM-DD`` strings or date objects.

Sections:
  1. Ladder (spacing of errors): add, repair, pass_, fail, deadline cap,
     short-runway retirement.
  2. Session budget: work minutes, question budget, close start, breaks.
  3. Cold eligibility: the 2-day recheck window (a first serve, or one again
     after a recheck left the topic below 3) and the 24-hour rule.
  4. Levels: compute_levels_from(attempts, subject, errors=None) -> {topic: {level, level_basis}}.
  5. Metrics: accuracy by instrument, careless per 10, unnamed-wrong %,
     least-sure hit rate, check coverage and catches, retention, execution.
  6. Loader helpers (I/O, clearly separated): compute_levels(subject_dir).
"""

import copy
import math
from datetime import timedelta

from lib import dates

# ==========================================================================
# 1. Ladder
# ==========================================================================

LADDER_DAYS = [1, 3, 7, 21]
LAST_RUNG = len(LADDER_DAYS) - 1
ERROR_KINDS = ("belief", "slip", "shaky")


def _d(value):
    return dates.to_date(value) if value is not None else None


def _dstr(value):
    return dates.fmt_date(value) if value is not None else None


def cap_due(next_due, deadline=None, today=None):
    """Apply the deadline cap to a due date.

    With a deadline: ``next_due = min(next_due, deadline - 2 days)``, but a cap
    never pulls the date before ``today + 1``; such a cap leaves it at today+1.
    Returns a date (or None when next_due is None).
    """
    if next_due is None:
        return None
    nd = _d(next_due)
    if deadline is None:
        return nd
    cap = _d(deadline) - timedelta(days=2)
    if nd <= cap:
        return nd
    floor = (_d(today) if today is not None else nd) + timedelta(days=1)
    return max(cap, floor)


def pass_days(e):
    """The distinct dates of an error's passes."""
    out = []
    for p in e.get("passes") or []:
        try:
            day = dates.fmt_date(p.get("date") if isinstance(p, dict) else p)
        except (ValueError, TypeError, AttributeError):
            continue
        if day not in out:
            out.append(day)
    return out


def last_miss_day(e):
    """The latest date in an error's fails (``YYYY-MM-DD``), or None."""
    out = None
    for f in e.get("fails") or []:
        try:
            day = dates.fmt_date(f.get("date") if isinstance(f, dict) else f)
        except (ValueError, TypeError, AttributeError):
            continue
        if out is None or day > out:
            out = day
    return out


def short_runway_retire_ok(e, d, deadline):
    """True if the error may retire early: +21 d from d is past the deadline
    and it has passes on at least 2 different days since its last miss (a pass
    from before the idea came back says nothing about it now)."""
    if deadline is None:
        return False
    if _d(d) + timedelta(days=LADDER_DAYS[LAST_RUNG]) <= _d(deadline):
        return False
    miss = last_miss_day(e)
    return len([p for p in pass_days(e) if miss is None or p > miss]) >= 2


def add(e, d, deadline=None, today=None):
    """A new error opened on date d. Returns a new dict.

    slip:   status=spacing, rung=0, next_due=d+1
    shaky:  status=spacing, rung=1, next_due=d+3
    belief: status=untreated, next_due=None (repair comes first)
    """
    e = copy.deepcopy(e)
    kind = e.get("kind")
    if kind not in ERROR_KINDS:
        raise ValueError("error kind must be one of %s, got %r" % (", ".join(ERROR_KINDS), kind))
    day = _d(d)
    today = today if today is not None else day
    e.setdefault("opened", _dstr(day))
    e.setdefault("passes", [])
    e.setdefault("fails", [])
    e.setdefault("repair_at", None)
    if kind == "slip":
        e["status"], e["rung"] = "spacing", 0
        e["next_due"] = _dstr(cap_due(day + timedelta(days=LADDER_DAYS[0]), deadline, today))
    elif kind == "shaky":
        e["status"], e["rung"] = "spacing", 1
        e["next_due"] = _dstr(cap_due(day + timedelta(days=LADDER_DAYS[1]), deadline, today))
    else:
        e["status"], e["rung"], e["next_due"] = "untreated", 0, None
    return e


add_error = add


def repair(e, at, deadline=None, today=None):
    """The belief was repaired at time ``at`` (a sheet or discussion).

    repair_at=at, status=spacing, rung=0, next_due = date(at) + 1, then the
    deadline cap. The repair is logged as an exposure, so the 24-hour rule
    keeps the mistake from coming back cold before at + 24 h.
    """
    e = copy.deepcopy(e)
    t = dates.parse_iso(at)
    due = t.date() + timedelta(days=1)
    today = today if today is not None else t.date()
    e["repair_at"] = dates.fmt_iso(t)
    e["status"] = "spacing"
    e["rung"] = 0
    e["next_due"] = _dstr(cap_due(due, deadline, today))
    return e


def pass_(e, d, deadline=None, today=None, short_runway=True):
    """A right answer on the error's re-serve on date d.

    Appends d to passes. At the last rung (3): retired. Otherwise rung += 1
    and next_due = d + LADDER_DAYS[rung], capped by the deadline. With a
    deadline, an error retires early when +21 d is past it and it has passes
    on at least 2 different days since its last miss.

    An untreated wrong idea is not on the ladder yet: a right answer before
    its repair (a repair drill done with the fix in view) is no pass, so the
    row comes back unchanged.
    """
    e = copy.deepcopy(e)
    if e.get("status") == "untreated":
        return e
    day = _d(d)
    today = today if today is not None else day
    e.setdefault("passes", [])
    e["passes"].append(_dstr(day))
    rung = int(e.get("rung") or 0)
    if rung >= LAST_RUNG or (short_runway and short_runway_retire_ok(e, day, deadline)):
        e["status"] = "retired"
        e["next_due"] = None
        return e
    rung += 1
    e["rung"] = rung
    if e.get("status") == "retired":
        e["status"] = "reopened"
    e["next_due"] = _dstr(cap_due(day + timedelta(days=LADDER_DAYS[rung]), deadline, today))
    return e


def fail(e, d, deadline=None, today=None):
    """A miss on the error's re-serve on date d.

    belief: status=untreated, rung=0, next_due=None (it needs repair again).
    slip/shaky: rung=0, next_due=d+1; status stays spacing (a retired item
    that fails its sentinel serve becomes reopened).
    """
    e = copy.deepcopy(e)
    day = _d(d)
    today = today if today is not None else day
    e.setdefault("fails", [])
    e["fails"].append(_dstr(day))
    e["rung"] = 0
    if e.get("kind") == "belief":
        e["status"] = "untreated"
        e["next_due"] = None
    else:
        e["status"] = "reopened" if e.get("status") == "retired" else (
            e.get("status") if e.get("status") in ("spacing", "reopened") else "spacing")
        e["next_due"] = _dstr(cap_due(day + timedelta(days=LADDER_DAYS[0]), deadline, today))
    return e


def is_due(e, d):
    """True if the error is on the ladder and due on or before date d."""
    if e.get("status") not in ("spacing", "reopened"):
        return False
    nd = e.get("next_due")
    return nd is not None and _d(nd) <= _d(d)


SENTINEL_DAYS = 28             # a retired mistake's one sentinel serve, after its last pass
SENTINEL_BEFORE_DATE_DAYS = 7  # ... or a week before the date, when that comes first


def sentinel_due(e, deadline=None):
    """The date a retired mistake's one sentinel serve falls due, or None.

    SENTINEL_DAYS after its last pass; with a deadline, a week before it when
    that comes first, but never before the day after the last pass, and never
    on or after the deadline.
    """
    if e.get("status") != "retired":
        return None
    days = pass_days(e)
    if not days:
        return None
    last = _d(max(days))
    due = last + timedelta(days=SENTINEL_DAYS)
    if deadline is not None:
        dl = _d(deadline)
        due = max(min(due, dl - timedelta(days=SENTINEL_BEFORE_DATE_DAYS)), last + timedelta(days=1))
        if due >= dl:
            return None
    return due


def sentinel_served(e, attempts):
    """True if a sentinel serve of the retired mistake ``e`` was graded on or after
    its last pass: on a mixed or measuring sheet, its topic not seen in the 24 h
    before (a warm serve moves nothing, so it does not count)."""
    days = pass_days(e)
    if not days:
        return False
    last, origin = max(days), "sentinel:%s" % e.get("id")
    for a in attempts or []:
        if a.get("origin") != origin or not (a.get("sheet_type") == "mixed" or a.get("prov") == "measured"):
            continue
        ih = a.get("interval_h")
        if isinstance(ih, (int, float)) and not isinstance(ih, bool) and ih < NO_EXPOSURE_H:
            continue
        at = dates.try_parse_iso(a.get("at"))
        if at is not None and dates.fmt_date(at) >= last:
            return True
    return False


# ==========================================================================
# 2. Session budget
# ==========================================================================

DEFAULT_PACE_S = {
    "procedural": 30, "conceptual": 90, "verbal": 75,
    "reading": 70, "production": 180, "code": 300,
}
LAYERS = tuple(DEFAULT_PACE_S)
GRADING_S_PER_ASK = 15
EXPECTED_MISS_RATE = 0.25
BUDGET_ITERATIONS = 3


def budget_band(planned_min):
    """(open, close, work fraction, uses breaks) for P minutes."""
    p = float(planned_min)
    if p <= 30:
        return 1, 2, 0.8, False
    if p <= 75:
        return 2, 5, 0.7, False
    return 3, 8, 0.6, True


def close_minutes(planned_min):
    """2 if P <= 30, 5 if P <= 75, otherwise 8."""
    return budget_band(planned_min)[1]


def break_count(planned_min, break_every_min=75):
    """ceil(P / 75) - 1 breaks when P > 75, else none."""
    if not budget_band(planned_min)[3]:
        return 0
    return max(0, int(math.ceil(float(planned_min) / float(break_every_min))) - 1)


def dominant_layer(subject):
    """The most common layer among the subject's in-scope topics."""
    counts, order = {}, []
    for t in (subject or {}).get("topics") or []:
        if not isinstance(t, dict) or t.get("scope") == "out":
            continue
        layer = t.get("layer")
        if layer not in DEFAULT_PACE_S:
            continue
        if layer not in counts:
            order.append(layer)
        counts[layer] = counts.get(layer, 0) + 1
    if counts:
        return max(order, key=lambda k: (counts[k], -order.index(k)))
    profile = (subject or {}).get("profile")
    return {"language": "verbal", "code": "code"}.get(profile, "conceptual")


def pace_for(layer, pace_s=None):
    pace = (pace_s or {}).get(layer) or DEFAULT_PACE_S.get(layer) or DEFAULT_PACE_S["conceptual"]
    return float(pace)


def session_budget(planned_min, layer="conceptual", pace_s=None, break_every_min=75, break_min=10):
    """The session budget for P planned minutes.

    grading_est = 15 s x asks / 60 + 0.25 x asks x 1 min
    work_min    = min(f x P, P - open - close - breaks - grading_est)
    asks_budget = floor(work_min x 60 / pace)   (3 iterations from f x P x 60 / pace)
    """
    P = float(planned_min)
    if P <= 0:
        raise ValueError("planned minutes must be positive")
    open_min, close_min, f, _ = budget_band(P)
    n_breaks = break_count(P, break_every_min)
    breaks_total = n_breaks * break_min
    pace = pace_for(layer, pace_s)
    guess = f * P * 60.0 / pace
    grading = work = 0.0
    for _ in range(BUDGET_ITERATIONS):
        grading = guess * GRADING_S_PER_ASK / 60.0 + EXPECTED_MISS_RATE * guess * 1.0
        work = max(0.0, min(f * P, P - open_min - close_min - breaks_total - grading))
        guess = work * 60.0 / pace
    asks = int(math.floor(guess + 1e-9))
    offsets = [break_every_min * k for k in range(1, n_breaks + 1)]
    return {
        "planned_min": P if P != int(P) else int(P),
        "open_min": open_min,
        "close_min": close_min,
        "work_fraction": f,
        "breaks": n_breaks,
        "break_min": break_min if n_breaks else 0,
        "break_total_min": breaks_total,
        "break_offsets_min": offsets,
        "grading_est_min": round(grading, 1),
        "work_min": round(work, 1),
        "asks_budget": asks,
        "layer": layer,
        "pace_s": pace if pace != int(pace) else int(pace),
        "close_start_offset_min": P - close_min if P != int(P) else int(P) - close_min,
    }


def close_start(start, planned_min):
    """planned_end - close_minutes, as an aware datetime (elapsed minutes)."""
    return dates.plus(start, minutes=float(planned_min) - close_minutes(planned_min))


def planned_end(start, planned_min):
    return dates.plus(start, minutes=float(planned_min))


# ==========================================================================
# 3. Cold eligibility
# ==========================================================================

WARM_KINDS = ("teach", "repair", "drill", "chat", "review")
DEFAULT_COLD_WINDOW_H = (44.0, 72.0)
NO_EXPOSURE_H = 24.0


def _window(window):
    if not window:
        return DEFAULT_COLD_WINDOW_H
    return float(window[0]), float(window[1])


def last_exposure(topic, exposures, before=None, kinds=WARM_KINDS):
    """Latest exposure time (datetime) of topic at or before ``before``."""
    limit = dates.parse_iso(before) if before is not None else None
    best = None
    for x in exposures or []:
        if x.get("topic") != topic or (kinds and x.get("kind") not in kinds):
            continue
        t = dates.try_parse_iso(x.get("at"))
        if t is None or (limit is not None and t > limit):
            continue
        if best is None or t > best:
            best = t
    return best


def hours_since_exposure(topic, exposures, t):
    last = last_exposure(topic, exposures, before=t)
    if last is None:
        return None
    return (dates.parse_iso(t) - last).total_seconds() / 3600.0


def untreated_on(topic, errors):
    return [e for e in errors or [] if e.get("topic") == topic and e.get("status") == "untreated"]


def cold_eligibility(topic, t, exposures, errors, window=None, first_serve=True):
    """Is ``topic`` cold-eligible at time t?

    1. (first serve after teaching) its last warm exposure is between
       window[0] and window[1] hours before t;
    2. no exposure in the 24 h before t;
    3. no error on the topic is untreated.

    Returns ``{"eligible": bool, "reason": str, "hours": float|None}``.
    """
    lo, hi = _window(window)
    hours = hours_since_exposure(topic, exposures, t)
    if untreated_on(topic, errors):
        return {"eligible": False, "reason": "an untreated mistake on this topic needs fixing first", "hours": hours}
    if hours is not None and hours < NO_EXPOSURE_H:
        return {"eligible": False, "reason": "seen %.0f h ago (less than 24 h)" % hours, "hours": hours}
    if first_serve:
        if hours is None:
            return {"eligible": False, "reason": "not taught yet (no exposure on record)", "hours": None}
        if hours < lo:
            return {"eligible": False, "reason": "seen %.0f h ago; the recheck window opens at %.0f h" % (hours, lo), "hours": hours}
        if hours > hi:
            return {"eligible": False, "reason": "seen %.0f h ago; the recheck window closed at %.0f h" % (hours, hi), "hours": hours}
    return {"eligible": True, "reason": "ok" if hours is None else "%.0f h since last exposure" % hours, "hours": hours}


def is_cold_eligible(topic, t, exposures, errors, window=None, first_serve=True):
    return cold_eligibility(topic, t, exposures, errors, window, first_serve)["eligible"]


def window_closes(topic, t, exposures, window=None):
    """When the first 2-day recheck window of ``topic`` closes, seen at time t.

    It is the last warm exposure at or before t, plus window[1] elapsed hours
    (the same rule as cold_eligibility and the level rules). None when the
    topic has no exposure on record.
    """
    last = last_exposure(topic, exposures, before=t)
    if last is None:
        return None
    return dates.plus(last, hours=_window(window)[1])


FIRST_SERVE_KINDS = ("teach", "review")


def has_first_serve_basis(topic, exposures, topic_state=None):
    """True if the topic can have a first 2-day recheck at all.

    It needs teaching on record: ``taught_at`` in topics.json, or a ``teach``
    exposure, or the ``review`` exposure that confirms a never-taught 3p topic
    (measure.md section 8). A topic that was only measured, or only drilled,
    is not recheck material.
    """
    if (topic_state or {}).get("taught_at"):
        return True
    for x in exposures or []:
        if x.get("topic") == topic and x.get("kind") in FIRST_SERVE_KINDS:
            return True
    return False


def is_first_serve(topic_state):
    """True if the topic has not been served cold since it was last taught."""
    st = topic_state or {}
    taught, last_cold = st.get("taught_at"), st.get("last_cold")
    if not last_cold:
        return True
    if not taught:
        return False
    a, b = dates.try_parse_iso(taught), dates.try_parse_iso(last_cold)
    return a is not None and b is not None and b < a


def needs_rerecheck(topic, topic_state, exposures):
    """True if a topic served cold is still below 3 and has had a warm exposure since.

    A recheck that leaves a topic below 3 (a miss, a score under 75%, a sitting
    outside its window) is not the end of it: its next warm exposure (the fix
    sheet, the feedback logged after marking, drills) opens a new 2-day window,
    and the topic comes back cold inside it, as a first serve does. A topic at 3
    or above never does: its later serves have no window.
    """
    st = topic_state or {}
    last_cold = dates.try_parse_iso(st.get("last_cold"))
    if last_cold is None or level_rank(st.get("level")) >= 3:
        return False
    last = last_exposure(topic, exposures)
    return last is not None and last > last_cold


def needs_window(topic, topic_state, exposures):
    """True if a cold serve of ``topic`` is a 2-day recheck, judged by its window:
    the first serve since it was taught (is_first_serve), or one again after a
    recheck that left it below 3 (needs_rerecheck)."""
    return is_first_serve(topic_state) or needs_rerecheck(topic, topic_state, exposures)


def error_reserve_eligibility(error, t, exposures, errors):
    """Error re-serve: rules 2 and 3 of cold eligibility plus next_due <= date(t)."""
    topic = error.get("topic")
    if error.get("status") == "untreated":
        return {"eligible": False, "reason": "needs repair before it can come back cold", "hours": None}
    if error.get("status") not in ("spacing", "reopened"):
        return {"eligible": False, "reason": "not on the ladder (status %s)" % error.get("status"), "hours": None}
    nd = error.get("next_due")
    if nd is None or _d(nd) > dates.parse_iso(t).date():
        return {"eligible": False, "reason": "not due until %s" % nd, "hours": None}
    res = cold_eligibility(topic, t, exposures, errors, first_serve=False)
    return res


def is_error_reserve_eligible(error, t, exposures, errors):
    return error_reserve_eligibility(error, t, exposures, errors)["eligible"]


# ==========================================================================
# 4. Levels
# ==========================================================================

VERDICT_SCORE = {"right": 1.0, "half": 0.5, "wrong": 0.0, "dont_know": 0.0, "skip": 0.0}
PRACTICE = "practice"
MEASURE_01 = ("diagnostic", "mock", "checkpoint", "probe")
MEASURE_3P = ("diagnostic", "mock", "checkpoint")
MEASURE_5 = ("mock", "checkpoint")
EPISODE_H = 72.0          # parts of one measurement taken within 72 h are pooled
CONFIRM_3P_DAYS = 14
LEVEL4_GAP_DAYS = 7
UPKEEP_DAYS = 21          # a topic at 4 or 5 comes back cold this long after its last pass
PASS_PCT = 0.75
FAIL_PCT = 0.50
MIN_3P_ASKS = 4
MIN_COLD_ASKS = 2         # a cold pass needs at least this many counted questions on the topic
LEVEL_ORDER = [0, 1, 2, "3p", 3, 4, 5]
# Sheets answered with the explanation in view: never evidence for a level.
IN_VIEW_TYPES = ("theory", "external", "example", "repair")


def level_rank(level):
    """Numeric rank for comparing levels: 3p sits between 2 and 3."""
    if level in ("3p", "3P"):
        return 2.5
    try:
        return float(level)
    except (TypeError, ValueError):
        return 0.0


def score_of(attempt):
    s = attempt.get("score")
    if isinstance(s, (int, float)) and not isinstance(s, bool):
        return float(s)
    return VERDICT_SCORE.get(attempt.get("verdict"), 0.0)


def _num(x):
    return ("%d" % x) if float(x) == int(x) else ("%.1f" % x)


def _frac(pts, n):
    return "%s/%d" % (_num(pts), n)


def _instrument(a):
    inst = a.get("instrument")
    if a.get("cold") is True and inst in (None, "", "cold"):
        return "cold"
    return inst or PRACTICE


def counts_toward_level(a):
    """Does this graded question count toward its topic's level?

    Not counted: a *right* answer the learner named on the Least-sure line
    (a wrong, half or "don't know" answer counts even when named: naming a
    miss never hides it); a question answered with the explanation in view
    (theory, external, example and repair sheets); a recheck question marked
    contaminated (the topic was seen in the 24 h before the sitting).
    """
    if a.get("least_sure") is True and a.get("verdict") == "right":
        return False
    if a.get("sheet_type") in IN_VIEW_TYPES:
        return False
    if a.get("contaminated") is True:
        return False
    return True


def _sittings(attempts):
    """Group counted asks into per-(topic, sheet) sittings."""
    groups = {}
    for a in attempts or []:
        if not counts_toward_level(a):
            continue
        topic = a.get("topic")
        if not topic:
            continue
        key = (topic, a.get("sheet") or "?")
        g = groups.get(key)
        at = dates.try_parse_iso(a.get("at"))
        if g is None:
            g = {"topic": topic, "sheet": key[1], "instrument": _instrument(a), "at": at,
                 "n": 0, "pts": 0.0, "interval_h": None}
            groups[key] = g
        g["n"] += 1
        g["pts"] += score_of(a)
        if at is not None and (g["at"] is None or at < g["at"]):
            g["at"] = at
        ih = a.get("interval_h")
        if isinstance(ih, (int, float)) and not isinstance(ih, bool):
            g["interval_h"] = float(ih) if g["interval_h"] is None else min(g["interval_h"], float(ih))
    by_topic = {}
    for g in groups.values():
        g["pct"] = g["pts"] / g["n"] if g["n"] else 0.0
        by_topic.setdefault(g["topic"], []).append(g)
    return by_topic


def _pool(sittings, end, kinds):
    """Pool the sittings of ``kinds`` within EPISODE_H hours up to ``end``."""
    pts = n = 0
    sheets = []
    for s in sittings:
        if s["instrument"] not in kinds or s["at"] is None:
            continue
        if end - timedelta(hours=EPISODE_H) <= s["at"] <= end:
            pts += s["pts"]
            n += s["n"]
            sheets.append(s["sheet"])
    return pts, n, sheets


def _levels_for_topic(sittings, window, untreated=None, least_sure_only=False):
    lo, hi = window
    timed = sorted([s for s in sittings if s["at"] is not None], key=lambda s: s["at"])
    # Practice is judged per day: build one pooled event per day.
    events, practice_days = [], {}
    for s in timed:
        if s["instrument"] == PRACTICE:
            day = s["at"].date()
            p = practice_days.setdefault(day, {"kind": "practice_day", "at": s["at"], "n": 0, "pts": 0.0, "sheets": []})
            p["n"] += s["n"]
            p["pts"] += s["pts"]
            p["sheets"].append(s["sheet"])
            if s["at"] > p["at"]:
                p["at"] = s["at"]
        else:
            events.append(dict(s, kind="sitting"))
    events.extend(practice_days.values())
    events.sort(key=lambda e: (e["at"], 0 if e["kind"] == "practice_day" else 1))

    st = {
        "practice": None,     # basis for level 2
        "measure": None,      # (pct, basis) of the latest measurement episode
        "m3p": None,          # (at, basis)
        "cold1": None,        # (at, basis) first qualifying cold pass -> 3
        "l4": None,           # (at, basis)
        "l5": None,           # basis
        "drop": None,         # basis for "back to 2 after a cold fail"
        "thin": None,         # the latest cold sitting with too few counted questions to count
        "last_pass": None,    # the latest cold pass, or mock or checkpoint pass, not warm
    }

    def current():
        if st["l5"]:
            return 5
        if st["l4"]:
            return 4
        if st["cold1"]:
            return 3
        if st["m3p"]:
            return "3p"
        if st["drop"] or st["practice"]:
            return 2
        if st["measure"] and st["measure"][0] >= 0.25:
            return 1
        return 0

    for ev in events:
        at = ev["at"]
        if ev["kind"] == "practice_day":
            if ev["n"] and ev["pts"] / ev["n"] >= PASS_PCT:
                sheets = ev["sheets"]
                name = sheets[0] + (" +%d" % (len(sheets) - 1) if len(sheets) > 1 else "")
                st["practice"] = "practice %s on %s (%s)" % (_frac(ev["pts"], ev["n"]), name, dates.fmt_date(at))
            continue
        inst = ev["instrument"]
        if inst in MEASURE_01:
            pts, n, sheets = _pool(timed, at, MEASURE_01)
            if n:
                basis = "%s %s on %s" % (inst, _frac(pts, n), ", ".join(sheets))
                if pts / n >= PASS_PCT and n < MIN_3P_ASKS:
                    basis += " (3p needs at least %d questions)" % MIN_3P_ASKS
                st["measure"] = (pts / n, basis)
            if inst in MEASURE_3P:
                pts3, n3, sheets3 = _pool(timed, at, MEASURE_3P)
                if n3 >= MIN_3P_ASKS and pts3 / n3 >= PASS_PCT:
                    st["m3p"] = (at, "%s %s on %s; a cold pass by %s makes it 3" % (
                        inst, _frac(pts3, n3), ", ".join(sheets3),
                        dates.fmt_date(at + timedelta(days=CONFIRM_3P_DAYS))))
                elif n3 and pts3 / n3 < PASS_PCT:
                    st["m3p"] = None  # a newer measurement no longer supports 3p
            if inst in MEASURE_5 and st["l4"] and at > st["l4"][0] and ev["n"] and ev["pct"] >= PASS_PCT:
                st["l5"] = "%s %s on %s after level 4" % (inst, _frac(ev["pts"], ev["n"]), ev["sheet"])
            if inst in MEASURE_5 and ev["n"] >= MIN_COLD_ASKS and ev["pct"] >= PASS_PCT:
                st["last_pass"] = at
            continue
        if inst != "cold":
            continue
        ih = ev["interval_h"]
        pct = ev["pct"]
        label = "cold %s on %s" % (_frac(ev["pts"], ev["n"]), ev["sheet"])
        if ih is not None:
            label += " at %.0f h" % ih
        if ev["n"] < MIN_COLD_ASKS:
            # Too few counted questions to pass or to fail: the sitting counts for nothing,
            # but level_basis says it was seen, rather than "no evidence yet".
            st["thin"] = "%s did not count (a recheck needs at least %d counted questions on the topic)" % (
                label, MIN_COLD_ASKS)
            continue
        st["thin"] = None
        if pct < FAIL_PCT:
            before = current()
            if level_rank(before) > 2:
                st.update({"m3p": None, "cold1": None, "l4": None, "l5": None})
                st["drop"] = "%s (%s) after level %s: back to 2" % (
                    label.replace("cold ", "cold fail ", 1), dates.fmt_date(at), before)
            continue
        if pct < PASS_PCT:
            continue
        not_warm = ih is None or ih >= NO_EXPOSURE_H
        in_window = ih is not None and lo <= ih <= hi and ih >= NO_EXPOSURE_H
        if not_warm:
            st["last_pass"] = at
        if st["cold1"] is None:
            if in_window:
                st["cold1"] = (at, label)
            elif st["m3p"] and not_warm and at - st["m3p"][0] <= timedelta(days=CONFIRM_3P_DAYS):
                st["cold1"] = (at, label + ", confirming 3p")
        elif st["l4"] is None:
            gap = at - st["cold1"][0]
            if not_warm and gap >= timedelta(days=LEVEL4_GAP_DAYS):
                st["l4"] = (at, "second %s, %d days after the first" % (label, gap.days))

    lvl = current()
    if lvl == 5:
        basis = st["l5"]
    elif lvl == 4:
        basis = st["l4"][1]
    elif lvl == 3:
        basis = st["cold1"][1]
    elif lvl == "3p":
        basis = st["m3p"][1]
    elif lvl == 2:
        basis = st["drop"] or st["practice"]
    elif lvl == 1:
        basis = "latest measurement: " + st["measure"][1]
    elif st["measure"]:
        basis = "latest measurement: " + st["measure"][1]
    elif least_sure_only:
        basis = "only least-sure questions so far (right answers named on the Least-sure line do not count)"
    elif st["thin"]:
        basis = st["thin"]
    else:
        basis = "no evidence yet"
    if st["thin"] and level_rank(lvl) < 3 and basis != st["thin"]:
        basis = "%s; %s" % (basis, st["thin"])
    out = {"level": lvl, "level_basis": basis, "held": False,
           "first_pass": dates.fmt_iso(st["cold1"][0]) if st["cold1"] else None,
           "last_pass": dates.fmt_iso(st["last_pass"]) if st["last_pass"] else None}
    if untreated and level_rank(lvl) >= 3:
        held = "3p" if st["m3p"] else 2
        out.update({"level": held, "held": True,
                    "level_basis": "%s; held at %s while a wrong idea is not fixed (%s)" % (
                        basis, held, ", ".join(untreated))})
    return out


def compute_levels_from(attempts, subject=None, topic_ids=None, errors=None):
    """Levels for every topic, from the attempt rows (pure).

    ``subject`` is the subject.json dict (for the cold window and topic list).
    ``errors`` (optional) are the subject's mistakes: a topic with an untreated
    wrong idea is held below 3 until the idea is repaired.
    Returns ``{topic: {"level": 0|1|2|"3p"|3|4|5, "level_basis": str, "held": bool,
    "first_pass": ISO|None, "last_pass": ISO|None}}``: ``held`` is true when that
    wrong idea alone keeps the topic below 3; ``first_pass`` is the cold pass that
    made it 3, ``last_pass`` its latest cold, mock or checkpoint pass (for
    later_recheck_due).
    """
    window = _window((subject or {}).get("cold_window_h"))
    ids = list(topic_ids or [])
    for t in (subject or {}).get("topics") or []:
        if isinstance(t, dict) and t.get("id") and t["id"] not in ids:
            ids.append(t["id"])
    by_topic = _sittings(attempts)
    named_only = set()
    for a in attempts or []:
        tid = a.get("topic")
        if tid and tid not in ids:
            ids.append(tid)
        if tid and a.get("least_sure") is True and a.get("verdict") == "right":
            named_only.add(tid)
    untreated = {}
    for e in errors or []:
        if e.get("status") == "untreated" and e.get("topic"):
            untreated.setdefault(e["topic"], []).append(e.get("id") or "?")
    out = {}
    for tid in ids:
        sittings = by_topic.get(tid, [])
        out[tid] = _levels_for_topic(sittings, window, untreated=untreated.get(tid),
                                     least_sure_only=(tid in named_only and not sittings))
    return out


def later_recheck_due(level, first_pass, last_pass, deadline=None):
    """When a topic's next cold serve after its 2-day recheck falls due:
    ``("level4", datetime)``, ``("upkeep", datetime)`` or None.

    At 3: its level-4 recheck, LEVEL4_GAP_DAYS after its first pass (the level
    rules need that gap). At 4 or 5: an upkeep recheck, UPKEEP_DAYS after its
    last pass; with a deadline, brought forward to 2 days before it, as the
    ladder is, but never to less than LEVEL4_GAP_DAYS after the last pass.
    None when it would fall on or after the deadline: nothing is kept up
    past the date.
    """
    rank = level_rank(level)
    dl = _d(deadline) if deadline is not None else None
    if rank == 3 and first_pass:
        kind, due = "level4", dates.parse_iso(first_pass) + timedelta(days=LEVEL4_GAP_DAYS)
    elif rank >= 4 and last_pass:
        last = dates.parse_iso(last_pass)
        kind, due = "upkeep", last + timedelta(days=UPKEEP_DAYS)
        if dl is not None:
            cap = dates.at_time(dl - timedelta(days=2), "00:00", last.tzinfo)
            if due > cap:
                if cap < last + timedelta(days=LEVEL4_GAP_DAYS):
                    return None
                due = cap
    else:
        return None
    if dl is not None and due.date() >= dl:
        return None
    return kind, due


TOPIC_STATE_DEFAULTS = {
    "level": 0, "level_basis": "no evidence yet", "taught_at": None, "taught_by": None,
    "last_cold": None, "explanation_on_file": False, "note": "",
}


def merge_levels(topics_state, levels):
    """topics.json with new levels merged in; other teaching facts are kept."""
    out = copy.deepcopy(topics_state or {})
    for tid, lv in levels.items():
        row = out.get(tid) or {}
        for k, v in TOPIC_STATE_DEFAULTS.items():
            row.setdefault(k, copy.deepcopy(v))
        row["level"] = lv["level"]
        row["level_basis"] = lv["level_basis"]
        out[tid] = row
    return out


def level_changes(old_state, new_levels):
    """[(topic, old_level, new_level)] for topics whose level changed."""
    out = []
    for tid, lv in new_levels.items():
        old = (old_state or {}).get(tid, {}).get("level", 0)
        if str(old) != str(lv["level"]):
            out.append((tid, old, lv["level"]))
    return out


# ==========================================================================
# 5. Metrics
# ==========================================================================

def _ratio(num, den):
    return {"value": (float(num) / den) if den else None, "num": num, "n": den}


def accuracy(attempts):
    """(right + 0.5 x half) / asks presented."""
    rows = list(attempts or [])
    return _ratio(sum(score_of(a) for a in rows), len(rows))


def accuracy_by_instrument(attempts):
    """{instrument: accuracy} - instruments are never pooled together."""
    groups = {}
    for a in attempts or []:
        groups.setdefault(a.get("instrument") or PRACTICE, []).append(a)
    return {k: accuracy(v) for k, v in sorted(groups.items())}


def careless_per_10(attempts, levels_before):
    """10 x misses with mode C / asks attempted on topics at level >= 3 before the sitting.

    ``levels_before`` maps topic -> level, or is a callable(attempt) -> level.
    """
    def lvl(a):
        if callable(levels_before):
            return levels_before(a)
        return (levels_before or {}).get(a.get("topic"), 0)

    attempted = [a for a in attempts or [] if a.get("verdict") in ("right", "half", "wrong")
                 and level_rank(lvl(a)) >= 3]
    careless = [a for a in attempted if a.get("verdict") in ("wrong", "half") and a.get("mode") == "C"]
    r = _ratio(len(careless), len(attempted))
    if r["value"] is not None:
        r["value"] *= 10
    return r


def unnamed_wrong_pct(attempts):
    """Wrong answers not on the Least-sure line / all wrong answers."""
    wrong = [a for a in attempts or [] if a.get("verdict") == "wrong"]
    return _ratio(len([a for a in wrong if not a.get("least_sure")]), len(wrong))


def least_sure_hit_rate(attempts):
    """Least-sure asks that were wrong / least-sure asks."""
    ls = [a for a in attempts or [] if a.get("least_sure")]
    return _ratio(len([a for a in ls if a.get("verdict") == "wrong"]), len(ls))


def check_coverage(attempts):
    """Asks with a check written (filled, caught or failed) / asks, on sheets that carry check lines."""
    rows = [a for a in attempts or [] if a.get("check") in ("filled", "missing", "caught", "failed")]
    return _ratio(len([a for a in rows if a.get("check") in ("filled", "caught", "failed")]), len(rows))


def check_catches(attempts):
    return len([a for a in attempts or [] if a.get("check") == "caught"])


def check_failed(attempts):
    """Checks that didn't hold with the answer kept (marked ✗): {"n", "right"}. Those on right
    answers are counted apart: they point at the check, its tolerance or the key, not the answer."""
    rows = [a for a in attempts or [] if a.get("check") == "failed"]
    return {"n": len(rows), "right": len([a for a in rows if a.get("verdict") == "right"])}


def retention(attempts, lo_h, hi_h):
    """right / presented on cold asks with interval_h in [lo_h, hi_h]."""
    rows = []
    for a in attempts or []:
        ih = a.get("interval_h")
        if _instrument(a) != "cold" or not isinstance(ih, (int, float)):
            continue
        if lo_h <= ih <= hi_h:
            rows.append(a)
    return _ratio(len([a for a in rows if a.get("verdict") == "right"]), len(rows))


def retention_48h(attempts):
    return retention(attempts, 36, 72)


def retention_7d(attempts):
    return retention(attempts, 144, 216)


def execution(blocks, sessions=None, until=None):
    """Blocks done / planned (past, not cancelled), minutes actual / planned, overruns."""
    limit = dates.parse_iso(until) if until is not None else None
    past = []
    for b in blocks or []:
        if b.get("status") == "cancelled" or not b.get("start") or b.get("kind") == "buffer":
            continue
        end = dates.try_parse_iso(b.get("end") or b.get("start"))
        if limit is not None and (end is None or end > limit):
            continue
        past.append(b)
    done = [b for b in past if b.get("status") == "done"]
    planned_min = actual_min = overrun_min = overruns = 0
    for s in sessions or []:
        planned_min += float((s.get("planned") or {}).get("min") or 0)
        actual_min += float((s.get("actual") or {}).get("elapsed_min") or 0)
        o = float(s.get("overrun_min") or 0)
        if o > 0:
            overruns += 1
            overrun_min += o
    return {
        "blocks": _ratio(len(done), len(past)),
        "minutes": _ratio(actual_min, planned_min),
        "overruns": overruns,
        "overrun_min": overrun_min,
    }


# ==========================================================================
# 6. Loader helpers (I/O). Everything above this line is pure.
# ==========================================================================

def load_subject_evidence(subject_dir):
    """(subject.json dict, attempts incl. archive, exposures) from a subject folder."""
    from pathlib import Path
    from lib import io as fio
    root = Path(subject_dir)
    subject = fio.read_json(root / "subject.json", default={}) or {}
    attempts = []
    for p in sorted((root / "archive").glob("attempts-*.jsonl")):
        attempts.extend(fio.read_jsonl(p))
    attempts.extend(fio.read_jsonl(root / "data" / "attempts.jsonl"))
    exposures = fio.read_jsonl(root / "data" / "exposures.jsonl")
    return subject, attempts, exposures


def compute_levels(subject_dir):
    """Levels for a subject folder: ``{topic: {"level", "level_basis"}}``."""
    from pathlib import Path
    from lib import io as fio
    subject, attempts, _ = load_subject_evidence(subject_dir)
    errors = fio.read_jsonl(Path(subject_dir) / "data" / "errors.jsonl")
    return compute_levels_from(attempts, subject, errors=errors)
