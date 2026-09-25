"""Stats, the weekly review and compaction (CONTRACT sections 6.6 and 7.7).

    stats <subject> [--since DATE] [--until DATE] [--json]
    review week [subject|all] [--week YYYY-Www]
    compact <subject> [--dry-run]

``stats`` prints each metric per instrument, with its label: numbers from
different instruments are never pooled. "Careless per 10" counts only asks on
topics that were at level 3 or above before the sitting; that level is
recomputed from the attempts that came before the sitting.

``review week`` prints at most 15 lines and writes ``reviews/YYYY-Www.md``
(at most 60 lines). With no ``--week`` it reviews the week just ended (the
current week when run on a Sunday).

``compact`` never deletes learner data: it moves retired mistakes older than
7 days to ``archive/errors-YYYY-MM.jsonl`` and graded questions from earlier
months to ``archive/attempts-YYYY-MM.jsonl``, keeps ``.bak`` copies, and
refuses unless the set of mistake ids across the active and archive files is
the same before and after. It also clears Claude's own scratch files in
``<subject>/.indelible/tmp`` older than 7 days (specs, grades files; never
learner data), and reports how many files in ``inbox/`` are already filed
as evidence, so the learner can be asked whether to delete them.

Execution has one definition everywhere (stats and review): blocks done out
of the blocks whose time has passed, never counting blocks still ahead. A
block missed and then rebooked counts as missed.
"""

import json
import re
from datetime import date, timedelta

from lib import CheckFailed, UsageError
import hashlib
import time

from lib import dates, learning, schema
from lib import io as fio
from lib import ws as wsmod
from lib.cmd_learning import add_parser_once, fmt_level, fmt_num, out, require_writable

MEASURED = tuple(schema.MEASURING_TYPES)
WEEK_RE = re.compile(r"^(\d{4})-W(\d{1,2})$")
PRINT_MAX = 15
FILE_MAX = 60
RETIRED_KEEP_DAYS = 7
TMP_KEEP_DAYS = 7
OPEN_ERROR = ("spacing", "reopened")


# ==========================================================================
# Registration
# ==========================================================================

def register(subparsers):
    p = add_parser_once(subparsers, "stats", help="the learning metrics, per instrument")
    if p is not None:
        p.add_argument("subject", nargs="?", default=None)
        p.add_argument("--since", default=None, metavar="DATE", help="only questions answered on or after DATE")
        p.add_argument("--until", default=None, metavar="DATE", help="only questions answered on or before DATE")
        p.add_argument("--json", action="store_true")
        p.set_defaults(func=cmd_stats)

    p = add_parser_once(subparsers, "review", help="the weekly review")
    if p is not None:
        sp = p.add_subparsers(dest="review_cmd", metavar="<week>")
        w = sp.add_parser("week", help="execution, learning and hygiene for one week (at most 15 lines)")
        w.add_argument("subject", nargs="?", default="all", help="a subject id, or all (the default)")
        w.add_argument("--week", default=None, metavar="YYYY-Www",
                       help="default: the week just ended (this week when run on a Sunday)")
        w.set_defaults(func=cmd_review_week)

    p = add_parser_once(subparsers, "compact", help="archive retired mistakes and old graded questions")
    if p is not None:
        p.add_argument("subject", nargs="?", default=None)
        p.add_argument("--dry-run", action="store_true", help="show what would move; write nothing")
        p.set_defaults(func=cmd_compact)


# ==========================================================================
# Pure helpers
# ==========================================================================

def instrument_of(a):
    inst = a.get("instrument")
    if a.get("cold") is True and inst in (None, "", "cold"):
        return "cold"
    return inst or "practice"


def label_of(inst):
    return "measured" if inst in MEASURED else "practice"


def _timed(attempts):
    rows = []
    for a in attempts or []:
        t = dates.try_parse_iso(a.get("at"))
        rows.append((t, a))
    return rows


def levels_before_fn(history, subject_cfg, errors=None):
    """A callable(attempt) -> the topic's level before that attempt's sitting.

    A sitting is one sheet; it starts at the earliest ``at`` of its questions.
    Levels are recomputed from the questions answered strictly before it.
    """
    timed = _timed(history)
    starts = {}
    for t, a in timed:
        if t is None:
            continue
        s = a.get("sheet") or "?"
        if s not in starts or t < starts[s]:
            starts[s] = t
    cache = {}

    def fn(a):
        s = a.get("sheet") or "?"
        if s not in cache:
            t0 = starts.get(s)
            prior = [b for t, b in timed if t is not None and t0 is not None and t < t0]
            cache[s] = learning.compute_levels_from(prior, subject_cfg, errors=errors)
        return (cache[s].get(a.get("topic")) or {}).get("level", 0)

    return fn


def instrument_metrics(attempts, level_fn):
    groups = {}
    for a in attempts or []:
        groups.setdefault(instrument_of(a), []).append(a)
    result = {}
    for inst in sorted(groups):
        rows = groups[inst]
        result[inst] = {
            "label": label_of(inst),
            "accuracy": learning.accuracy(rows),
            "careless_per_10": learning.careless_per_10(rows, level_fn),
            "unnamed_wrong": learning.unnamed_wrong_pct(rows),
            "least_sure_hit": learning.least_sure_hit_rate(rows),
            "check_coverage": learning.check_coverage(rows),
            "check_catches": learning.check_catches(rows),
        }
    return result


def retention_split(attempts, topics_state=None):
    """48 h retention overall, by how the topic was taught, and by topic; 7 d overall."""
    state = topics_state or {}
    cold = [a for a in attempts or [] if instrument_of(a) == "cold"]
    by_tb, by_topic = {}, {}
    for a in cold:
        tb = a.get("taught_by") or (state.get(a.get("topic")) or {}).get("taught_by") or "not recorded"
        by_tb.setdefault(tb, []).append(a)
        by_topic.setdefault(a.get("topic") or "?", []).append(a)
    split_tb = {}
    for k in sorted(by_tb):
        r = learning.retention_48h(by_tb[k])
        if r["n"]:
            split_tb[k] = r
    split_topic = {}
    for k in sorted(by_topic):
        r = learning.retention_48h(by_topic[k])
        if r["n"]:
            split_topic[k] = r
    return {
        "retention_48h": {"overall": learning.retention_48h(cold), "by_taught_by": split_tb,
                          "by_topic": split_topic},
        "retention_7d": {"overall": learning.retention_7d(cold)},
    }


def pct(r):
    if r is None or r.get("value") is None:
        return "no data"
    return "%d%% (%s/%d)" % (int(round(100.0 * r["value"])), fmt_num(r["num"]), r["n"])


def per10(r):
    if r is None or r.get("value") is None:
        return "no questions on level-3+ topics"
    return "%.1f (%s in %d questions on level-3+ topics)" % (r["value"], fmt_num(r["num"]), r["n"])


def of(r):
    if r is None or r.get("value") is None:
        return "no data"
    return "%s of %d" % (fmt_num(r["num"]), r["n"])


def _in_range(t, lo, hi):
    return t is not None and (lo is None or t >= lo) and (hi is None or t < hi)


def subject_blocks(ws, sid):
    return [b for b in ws.load_blocks() if b.get("subject") == sid]


# ==========================================================================
# stats
# ==========================================================================

def compute_stats(ws, subj, since=None, until=None, now=None):
    now = now or ws.now()
    tz = ws.tzinfo()
    lo = dates.at_time(since, "00:00", tz) if since else None
    hi = dates.at_time(dates.to_date(until) + timedelta(days=1), "00:00", tz) if until else None
    history = subj.load_attempts(include_archive=True)
    rows = [a for t, a in _timed(history) if (lo is None and hi is None) or _in_range(t, lo, hi)]
    cfg = subj.load()
    level_fn = levels_before_fn(history, cfg)
    state = subj.load_topics_state()
    result = {
        "subject": subj.id,
        "since": dates.fmt_date(since) if since else None,
        "until": dates.fmt_date(until) if until else None,
        "asks": len(rows),
        "instruments": instrument_metrics(rows, level_fn),
    }
    result.update(retention_split(rows, state))
    sessions = subj.load_sessions(include_archive=True)
    blocks = subject_blocks(ws, subj.id)
    if lo is not None or hi is not None:
        sessions = [s for s in sessions if _in_range(_session_time(s), lo, hi)]
        blocks = [b for b in blocks if _in_range(dates.try_parse_iso(b.get("start")), lo, hi)]
    ex = learning.execution(blocks, sessions, until=now)
    if ws.schedule_mode() != "scheduled":
        ex["blocks"] = None
    else:
        ex["missed"] = len([b for b in _past_blocks(blocks, now) if _was_missed(b)])
    result["execution"] = ex
    return result


def _past_blocks(blocks, now):
    """Blocks whose time has passed (the execution denominator; buffers and cancelled ones left out)."""
    out = []
    for b in blocks:
        if b.get("status") == "cancelled" or not b.get("start") or b.get("kind") == "buffer":
            continue
        end = dates.try_parse_iso(b.get("end") or b.get("start"))
        if end is not None and end <= now:
            out.append(b)
    return out


def _was_missed(b):
    return b.get("status") in ("missed", "missed?") or bool(b.get("misses"))


def stats_lines(subj, st):
    span = "all graded questions"
    if st["since"] or st["until"]:
        span = "questions from %s to %s" % (st["since"] or "the start", st["until"] or "now")
    lines = ["%s (%s) · %s · %d questions · one line per instrument, never pooled"
             % (subj.title(), subj.id, span, st["asks"])]
    if not st["instruments"]:
        lines.append("No graded questions yet.")
    for inst, m in st["instruments"].items():
        n = m["accuracy"]["n"]
        tag = "[measured n=%d]" % n if m["label"] == "measured" else "[practice n=%d]" % n
        parts = ["accuracy %s" % pct(m["accuracy"]),
                 "careless per 10: %s" % per10(m["careless_per_10"]),
                 "unnamed-wrong %s" % pct(m["unnamed_wrong"]),
                 "least-sure wrong %s" % pct(m["least_sure_hit"]),
                 "check coverage %s" % pct(m["check_coverage"]),
                 "check catches %d" % m["check_catches"]]
        lines.append("%s %s: %s" % (inst, tag, " · ".join(parts)))
    r48 = st["retention_48h"]
    line = "retention 48 h [measured]: %s" % pct(r48["overall"])
    if r48["by_taught_by"]:
        line += " · by teaching: " + ", ".join("%s %s" % (k, pct(v)) for k, v in r48["by_taught_by"].items())
    if r48["by_topic"]:
        line += " · by topic: " + ", ".join("%s %s" % (k, pct(v)) for k, v in r48["by_topic"].items())
    lines.append(line)
    lines.append("retention 7 d [measured]: %s" % pct(st["retention_7d"]["overall"]))
    ex = st["execution"]
    parts = []
    if ex.get("blocks") is not None:
        parts.append(("blocks done %s past" % of(ex["blocks"])) if ex["blocks"]["n"] else "no past blocks")
        if ex.get("missed"):
            parts.append("missed %d" % ex["missed"])
    if ex["minutes"]["n"]:
        parts.append("minutes %s actual of %s planned" % (fmt_num(ex["minutes"]["num"]), fmt_num(ex["minutes"]["n"])))
    parts.append("overruns %d (+%s min)" % (ex["overruns"], fmt_num(ex["overrun_min"])))
    lines.append("execution: " + " · ".join(parts))
    return lines


def _jsonable(obj):
    return json.loads(json.dumps(obj, default=str))


def cmd_stats(args):
    ws = wsmod.from_args(args)
    subj = ws.resolve_subject(args.subject)
    try:
        since = dates.to_date(args.since) if args.since else None
        until = dates.to_date(args.until) if args.until else None
    except ValueError as exc:
        raise UsageError("--since/--until: %s" % exc)
    st = compute_stats(ws, subj, since, until)
    if args.json:
        out(json.dumps(_jsonable(st), ensure_ascii=False, indent=2))
        return 0
    for line in stats_lines(subj, st):
        out(line)
    return 0


# ==========================================================================
# review week
# ==========================================================================

def parse_week(text):
    m = WEEK_RE.match((text or "").strip())
    if not m:
        raise UsageError("--week must look like 2026-W42, got %r" % text)
    try:
        return date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)
    except ValueError:
        raise UsageError("%s is not a valid ISO week." % text)


def default_week_start(today):
    monday = dates.week_start(today)
    return monday if today.weekday() == 6 else monday - timedelta(days=7)


def _session_time(s):
    for v in ((s.get("actual") or {}).get("start"), (s.get("planned") or {}).get("start"),
              (s.get("closed") or {}).get("at")):
        t = dates.try_parse_iso(v)
        if t is not None:
            return t
    return None


def _retired_on(e):
    days = []
    for p in e.get("passes") or []:
        try:
            days.append(dates.to_date(p.get("date") if isinstance(p, dict) else p))
        except (ValueError, TypeError, AttributeError):
            continue
    if days:
        return max(days)
    try:
        return dates.to_date(e.get("opened")) if e.get("opened") else None
    except ValueError:
        return None


def _date_in(value, first, last):
    try:
        d = dates.to_date(value) if value else None
    except (ValueError, TypeError):
        return False
    return d is not None and first <= d <= last


def subject_week(ws, subj, lo, hi, first, last, now):
    """Numbers for one subject over [lo, hi)."""
    today = now.date()
    cfg = subj.load()
    history = subj.load_attempts(include_archive=True)
    timed = _timed(history)
    week = [a for t, a in timed if _in_range(t, lo, hi)]
    errors_now = subj.load_errors()
    before = learning.compute_levels_from([a for t, a in timed if t is not None and t < lo], cfg)
    after = learning.compute_levels_from([a for t, a in timed if t is not None and t < hi], cfg,
                                         errors=errors_now if hi > now else None)
    changes = [(tid, (before.get(tid) or {}).get("level", 0), lv["level"]) for tid, lv in after.items()
               if str((before.get(tid) or {}).get("level", 0)) != str(lv["level"])]
    sessions = [s for s in subj.load_sessions(include_archive=True) if _in_range(_session_time(s), lo, hi)]
    planned_min = sum(float((s.get("planned") or {}).get("min") or 0) for s in sessions)
    actual_min = sum(float((s.get("actual") or {}).get("elapsed_min") or 0) for s in sessions)
    overruns = [float(s.get("overrun_min") or 0) for s in sessions if float(s.get("overrun_min") or 0) > 0]
    same_day = len([s for s in sessions if (s.get("closed") or {}).get("status") == "same-day"])
    all_blocks = subject_blocks(ws, subj.id)
    blocks = []
    for b in all_blocks:
        t = dates.try_parse_iso(b.get("start"))
        if not _in_range(t, lo, hi) or b.get("kind") == "buffer" or b.get("status") == "cancelled":
            continue
        blocks.append(b)
    # One definition with stats: done out of the blocks whose time has passed.
    past = _past_blocks(blocks, now)
    ahead = len(blocks) - len(past)
    done = len([b for b in past if b.get("status") == "done"])
    missed_ids = set()
    for b in past:
        if b.get("status") in ("missed", "missed?"):
            missed_ids.add(b.get("id"))
        elif b.get("status") in ("planned", "synced"):
            missed_ids.add(b.get("id"))  # past its end with nothing recorded: missed? (unconfirmed)
    rebooked = set()
    for b in all_blocks:
        for m in b.get("misses") or []:
            slot = dates.try_parse_iso((m or {}).get("slot"))
            if _in_range(slot, lo, hi):
                missed_ids.add(b.get("id"))  # missed in this week, even if rebooked into another
                if b.get("status") not in ("missed", "missed?"):
                    rebooked.add(b.get("id"))
    missed = len(missed_ids)
    moved = len([b for b in blocks if (b.get("status") == "moved" or b.get("moved_from"))
                 and b.get("id") not in missed_ids])
    all_errors = subj.load_errors(include_archive=True)
    seen, errs = set(), []
    for e in reversed(all_errors):  # later rows (active file) win
        if e.get("id") in seen:
            continue
        seen.add(e.get("id"))
        errs.append(e)
    opened = len([e for e in errs if _date_in(e.get("opened"), first, last)])
    retired = len([e for e in errs if e.get("status") == "retired" and _retired_on(e) is not None
                   and first <= _retired_on(e) <= last])
    repaired = len([e for e in errs if _date_in(e.get("repair_at"), first, last)])
    overdue = len([e for e in subj.load_errors() if e.get("status") in OPEN_ERROR
                   and _date_in(e.get("next_due"), date.min, today - timedelta(days=1))])
    level_fn = levels_before_fn(history, cfg)
    return {
        "id": subj.id, "title": subj.title(),
        "sessions": len(sessions), "planned_min": planned_min, "actual_min": actual_min,
        "overruns": len(overruns), "overrun_min": sum(overruns), "same_day": same_day,
        "blocks": len(past), "ahead": ahead, "done": done, "moved": moved, "missed": missed,
        "rebooked": len(rebooked),
        "scheduled": ws.schedule_mode() == "scheduled",
        "asks": len(week),
        "r48": learning.retention_48h([a for a in week if instrument_of(a) == "cold"]),
        "r7": learning.retention_7d([a for a in week if instrument_of(a) == "cold"]),
        "metrics": instrument_metrics(week, level_fn),
        "opened": opened, "retired": retired, "repaired": repaired, "overdue": overdue,
        "changes": changes,
        "topic_names": dict((t["id"], t.get("name") or "") for t in subj.topics()),
    }


def hygiene(ws, subjects, now, plain, lo=None, hi=None):
    """Overdue to-dos, sheets issued but not taken, defect categories repeated within the
    reviewed week [lo, hi), safeguards due."""
    ids = [s.id for s in subjects]
    today = now.date()
    rows = ws.load_ledger()

    def mine(r):
        return r.get("subject") in ids or r.get("subject") in (None, "", "all")

    items = []
    owed = []
    for r in ws.open_ledger_items(kind="owed", rows=rows):
        due = dates.try_parse_iso(r.get("due"))
        if mine(r) and due is not None and due < now:
            owed.append(r)
    if owed:
        parts = []
        for r in owed[:3]:
            what = (r.get("what") or "")[:50]
            due = dates.try_parse_iso(r.get("due"))
            text = '"%s" (due %s)' % (what, due.strftime("%a %d %b") if due else "?")
            parts.append(text if plain else "%s %s" % (r.get("id"), text))
        more = " +%d more" % (len(owed) - 3) if len(owed) > 3 else ""
        items.append(("To do, overdue: %d · %s%s" % (len(owed), "; ".join(parts), more)))
    unsat = []
    for s in subjects:
        for sh in s.load_sheets():
            if sh.get("status") == "issued":
                unsat.append(sh.get("id"))
    if unsat:
        items.append("Issued, not taken yet: " + ", ".join(unsat[:6]) + (" +%d more" % (len(unsat) - 6)
                                                                         if len(unsat) > 6 else ""))
    cats = {}
    for r in rows:
        if r.get("kind") == "defect" and mine(r):
            if lo is not None and not _in_range(dates.try_parse_iso(r.get("at")), lo, hi):
                continue
            c = cats.setdefault(r.get("category") or "?", {"n": 0, "fix": None})
            c["n"] += 1
            c["fix"] = r.get("fix_type")
    repeated = [(k, v) for k, v in sorted(cats.items()) if v["n"] >= 2]
    if repeated:
        items.append("Repeated my-mistake categories%s: " % (" this week" if lo is not None else "") + ", ".join(
            "%s x%d (latest fix: %s)" % (k, v["n"], v["fix"] or "?") for k, v in repeated))
    guards = []
    for r in ws.open_ledger_items(kind="decision", rows=rows):
        sg = r.get("safeguard") or {}
        if not mine(r) or not sg.get("check_on"):
            continue
        try:
            due = dates.to_date(sg["check_on"])
        except ValueError:
            continue
        if due <= today:
            text = '"%s" (check on %s)' % ((r.get("summary") or "")[:50], dates.fmt_date(due))
            guards.append(text if plain else "%s %s" % (r.get("id"), text))
    if guards:
        items.append("Safeguards past their check date: " + "; ".join(guards[:3]))
    return items


def _subject_lines(w):
    """(line 1 execution, line 2 retention and mistakes, line 3 metrics)."""
    parts = ["%d session%s" % (w["sessions"], "" if w["sessions"] == 1 else "s")]
    if w["sessions"]:
        parts[0] += ", %s/%s min" % (fmt_num(w["actual_min"]), fmt_num(w["planned_min"]))
        parts.append("overruns %d (+%s min)" % (w["overruns"], fmt_num(w["overrun_min"])))
        parts.append("closed same day %d/%d" % (w["same_day"], w["sessions"]))
    if w["scheduled"]:
        parts.append("blocks %d/%d done, %d moved, %d missed%s%s" % (
            w["done"], w["blocks"], w["moved"], w["missed"],
            " (%d rebooked)" % w["rebooked"] if w.get("rebooked") else "",
            ", %d still ahead" % w["ahead"] if w.get("ahead") else ""))
    l1 = "%s: %s" % (w["title"], " · ".join(parts))
    l2 = "  2-day recheck: %s [measured] · 7-day: %s [measured] · mistakes %d new, %d fixed, %d retired, %d overdue" % (
        pct(w["r48"]), pct(w["r7"]), w["opened"], w["repaired"], w["retired"], w["overdue"])
    if w["changes"]:
        l2 += " · levels " + ", ".join("%s %s→%s" % (t, fmt_level(a), fmt_level(b)) for t, a, b in w["changes"])
    bits = []
    for inst, m in w["metrics"].items():
        tag = "[%s]" % ("measured" if m["label"] == "measured" else "practice")
        seg = "%s %s: careless/10 %s · unnamed-wrong %s · checks %s, %d caught" % (
            inst, tag, "-" if m["careless_per_10"]["value"] is None else "%.1f" % m["careless_per_10"]["value"],
            pct(m["unnamed_wrong"]), pct(m["check_coverage"]), m["check_catches"])
        bits.append(seg)
    l3 = "  " + (" | ".join(bits) if bits else "no graded questions this week")
    return l1, l2, l3


def _file_lines(week_label, first, last, now, subject_weeks, hyg):
    lines = ["<!-- generated by indelible review week; the next run replaces it -->",
             "# Weekly review %s (%s to %s)" % (week_label, first.strftime("%a %d %b %Y"), last.strftime("%a %d %b %Y")),
             "",
             "Generated %s. Labels: [measured] = rechecks and measurements; [practice] = drills. "
             "Instruments are never pooled." % dates.fmt_iso(now)]
    for w in subject_weeks:
        lines += ["", "## %s (%s)" % (w["title"], w["id"]), "", "Execution:"]
        lines.append("- Sessions %d · minutes %s actual / %s planned · overruns %d (+%s min) · closed same day %d/%d"
                     % (w["sessions"], fmt_num(w["actual_min"]), fmt_num(w["planned_min"]), w["overruns"],
                        fmt_num(w["overrun_min"]), w["same_day"], w["sessions"]))
        if w["scheduled"]:
            lines.append("- Blocks past %d · %d done · %d moved · %d missed or unconfirmed%s%s"
                         % (w["blocks"], w["done"], w["moved"], w["missed"],
                            " (%d rebooked)" % w["rebooked"] if w.get("rebooked") else "",
                            " · %d still ahead" % w["ahead"] if w.get("ahead") else ""))
        lines += ["", "Learning:"]
        lines.append("- 2-day recheck (36-72 h): %s [measured]" % pct(w["r48"]))
        lines.append("- 7-day recheck (144-216 h): %s [measured]" % pct(w["r7"]))
        lines.append("- Mistakes: %d new, %d fixed, %d retired, %d overdue now"
                     % (w["opened"], w["repaired"], w["retired"], w["overdue"]))
        if w["changes"]:
            lines.append("- Level changes: " + ", ".join(
                "%s %s %s → %s" % (t, w["topic_names"].get(t, ""), fmt_level(a), fmt_level(b))
                for t, a, b in w["changes"]))
        else:
            lines.append("- Level changes: none")
        for inst, m in w["metrics"].items():
            tag = "measured" if m["label"] == "measured" else "practice"
            lines.append("- %s [%s n=%d]: accuracy %s · careless per 10 %s · unnamed-wrong %s · check coverage %s · "
                         "check catches %d" % (inst, tag, m["accuracy"]["n"], pct(m["accuracy"]),
                                                per10(m["careless_per_10"]), pct(m["unnamed_wrong"]),
                                                pct(m["check_coverage"]), m["check_catches"]))
    lines += ["", "## Hygiene", ""]
    lines += ["- " + h for h in hyg] if hyg else ["- Nothing overdue."]
    if len(lines) > FILE_MAX:
        lines = lines[:FILE_MAX - 1] + ["- (cut at %d lines)" % FILE_MAX]
    return lines


def _print_lines(header, subject_weeks, hyg, file_rel):
    per = [_subject_lines(w) for w in subject_weeks]
    tail = hyg if hyg else ["Hygiene: nothing overdue"]
    for mode in ("full", "joined", "short"):
        body = []
        for l1, l2, l3 in per:
            if mode == "full":
                body += [l1, l2, l3]
            elif mode == "joined":
                body += [l1, l2 + " ·" + l3[1:]]
            else:
                body += [l1]
        lines = [header] + body + tail
        if len(lines) <= PRINT_MAX:
            return lines
    lines = [header] + body + tail
    return lines[:PRINT_MAX - 1] + ["(%d more lines in %s)" % (len(lines) - PRINT_MAX + 1, file_rel)]


def cmd_review_week(args):
    ws = wsmod.from_args(args)
    now = ws.now()
    today = now.date()
    if args.subject in (None, "", "all"):
        subjects = ws.subjects("live")
        if not subjects:
            raise UsageError("No live subjects to review.")
    else:
        subjects = [ws.subject(args.subject)]
    monday = parse_week(args.week) if args.week else default_week_start(today)
    first, last = monday, monday + timedelta(days=6)
    week_label = dates.iso_week(monday)
    tz = ws.tzinfo()
    lo = dates.at_time(monday, "00:00", tz)
    hi = dates.at_time(monday + timedelta(days=7), "00:00", tz)
    plain = ((ws.load_config().get("learner") or {}).get("vocab") or "plain") == "plain"
    weeks = [subject_week(ws, s, lo, hi, first, last, now) for s in subjects]
    hyg = hygiene(ws, subjects, now, plain, lo=lo, hi=hi)
    path = ws.reviews_dir / ("%s.md" % week_label)
    file_rel = ws.rel(path)
    with ws.lock():
        fio.write_text(path, "\n".join(_file_lines(week_label, first, last, now, weeks, hyg)) + "\n")
    header = "Week %s (%s to %s) · written to %s" % (
        week_label, first.strftime("%a %d %b"), last.strftime("%a %d %b"), file_rel)
    for line in _print_lines(header, weeks, hyg, file_rel):
        out(line)
    return 0


# ==========================================================================
# compact
# ==========================================================================

def _row_key(e):
    return json.dumps(dict((k, v) for k, v in e.items() if k not in ("archived_at", "outcome")),
                      sort_keys=True, ensure_ascii=False)


def _att_key(a):
    return json.dumps(a, sort_keys=True, ensure_ascii=False)


def _outcome(e, day):
    passes = len(e.get("passes") or [])
    fails = len(e.get("fails") or [])
    return "retired %s after %d pass%s and %d miss%s" % (
        dates.fmt_date(day), passes, "" if passes == 1 else "es", fails, "" if fails == 1 else "es")


def plan_compaction(active_errors, error_archives, attempts, attempt_archives, today, now_iso):
    """Work out the moves (pure). Returns a dict with the new file contents and the parity sets.

    ``error_archives`` and ``attempt_archives`` map a file name to its rows.
    Raises CheckFailed if the mistake ids (or the graded questions) would not
    match before and after.
    """
    cur_month = today.strftime("%Y-%m")
    before_ids = set(e.get("id") for e in active_errors if e.get("id"))
    for rows in error_archives.values():
        before_ids |= set(e.get("id") for e in rows if e.get("id"))
    before_att = set(_att_key(a) for a in attempts)
    for rows in attempt_archives.values():
        before_att |= set(_att_key(a) for a in rows)

    keep, moved = [], []
    new_err = dict((k, list(v)) for k, v in error_archives.items())
    touched_err = []
    for e in active_errors:
        day = _retired_on(e) if e.get("status") == "retired" else None
        if day is None or (today - day).days <= RETIRED_KEEP_DAYS:
            keep.append(e)
            continue
        name = "errors-%s.jsonl" % day.strftime("%Y-%m")
        rows = new_err.setdefault(name, [])
        if _row_key(e) not in set(_row_key(r) for r in rows):
            row = dict(e)
            row["outcome"] = _outcome(e, day)
            row["archived_at"] = now_iso
            rows.append(row)
        if name not in touched_err:
            touched_err.append(name)
        moved.append((e.get("id"), name))

    keep_att, rotated = [], {}
    new_att = dict((k, list(v)) for k, v in attempt_archives.items())
    for a in attempts:
        t = dates.try_parse_iso(a.get("at"))
        month = t.strftime("%Y-%m") if t is not None else None
        if month is None or month >= cur_month:
            keep_att.append(a)
            continue
        name = "attempts-%s.jsonl" % month
        rows = new_att.setdefault(name, [])
        rotated.setdefault(name, 0)
        existing = [_att_key(r) for r in rows]
        k = _att_key(a)
        if k in existing:
            rotated[name] += 1  # already archived by an earlier, interrupted run
        else:
            rows.append(a)
            rotated[name] += 1

    after_ids = set(e.get("id") for e in keep if e.get("id"))
    for rows in new_err.values():
        after_ids |= set(e.get("id") for e in rows if e.get("id"))
    after_att = set(_att_key(a) for a in keep_att)
    for rows in new_att.values():
        after_att |= set(_att_key(a) for a in rows)
    if before_ids != after_ids:
        lost = sorted(before_ids - after_ids)
        extra = sorted(after_ids - before_ids)
        raise CheckFailed("Compaction refused: mistake id parity failed (missing %s; unexpected %s). "
                          "Nothing was written." % (", ".join(lost) or "none", ", ".join(extra) or "none"))
    if before_att != after_att:
        raise CheckFailed("Compaction refused: graded questions would not match before and after. "
                          "Nothing was written.")
    return {
        "keep_errors": keep, "moved_errors": moved,
        "error_files": dict((k, new_err[k]) for k in touched_err),
        "keep_attempts": keep_att, "rotated": rotated,
        "attempt_files": dict((k, new_att[k]) for k in rotated),
        "ids": before_ids, "att": before_att,
    }


def _read_archives(ws, subj, prefix):
    found = {}
    if subj.archive_dir.exists():
        for p in sorted(subj.archive_dir.glob("%s-*.jsonl" % prefix)):
            found[p.name] = ws.read_jsonl(p)
    return found


def _old_tmp_files(subj, now_epoch):
    """Claude's scratch files in <subject>/.indelible/tmp older than TMP_KEEP_DAYS."""
    out = []
    if not subj.tmp_dir.is_dir():
        return out
    for p in sorted(subj.tmp_dir.iterdir()):
        try:
            if p.is_file() and now_epoch - p.stat().st_mtime > TMP_KEEP_DAYS * 86400:
                out.append(p)
        except OSError:
            continue
    return out


def _sha_file(path):
    h = hashlib.sha256()
    with open(str(path), "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def inbox_filed(ws, subjects):
    """(files in inbox/, how many of them are already filed as evidence, by content)."""
    if not ws.inbox_dir.is_dir():
        return 0, 0
    filed = set()
    for s in subjects:
        for r in s.load_scan_index():
            if r.get("sha256"):
                filed.add(r["sha256"])
    total = hits = 0
    for p in ws.inbox_dir.iterdir():
        if not p.is_file() or p.name.startswith("."):
            continue
        total += 1
        try:
            if _sha_file(p) in filed:
                hits += 1
        except OSError:
            continue
    return total, hits


def cmd_compact(args):
    ws = wsmod.from_args(args)
    subj = ws.resolve_subject(args.subject)
    if not args.dry_run:
        require_writable(ws, subj)
    now = ws.now()
    today = now.date()
    with ws.lock():
        active = subj.load_errors()
        err_arch = _read_archives(ws, subj, "errors")
        attempts = ws.read_jsonl(subj.attempts_path)
        att_arch = _read_archives(ws, subj, "attempts")
        plan = plan_compaction(active, err_arch, attempts, att_arch, today, dates.fmt_iso(now))
        n_err = len(plan["moved_errors"])
        n_att = sum(plan["rotated"].values())
        if not args.dry_run and (n_err or n_att):
            fio.ensure_dir(subj.archive_dir)
            for name, rows in plan["error_files"].items():
                fio.write_jsonl(subj.archive_dir / name, rows)
            for name, rows in plan["attempt_files"].items():
                fio.write_jsonl(subj.archive_dir / name, rows)
            if n_err:
                subj.save_errors(plan["keep_errors"])
            if n_att:
                fio.write_jsonl(subj.attempts_path, plan["keep_attempts"])
            # Read back from disk: the parity must still hold.
            ids_now = set(e.get("id") for e in subj.load_errors(include_archive=True) if e.get("id"))
            att_now = set(_att_key(a) for a in subj.load_attempts(include_archive=True))
            if ids_now != plan["ids"] or att_now != plan["att"]:
                raise CheckFailed("Compaction wrote files but the read-back does not match (mistake ids or graded "
                                  "questions). The previous versions are kept as .bak beside each file; restore "
                                  "them before anything else runs.")
        stale = _old_tmp_files(subj, time.time())
        cleared = 0
        if not args.dry_run:
            for f in stale:
                try:
                    f.unlink()
                    cleared += 1
                except OSError:
                    pass
        inbox_total, inbox_done = inbox_filed(ws, [subj])
    verb = "would move" if args.dry_run else "moved"
    parts = []
    if n_err:
        files = sorted(set(name for _, name in plan["moved_errors"]))
        parts.append("%s %d retired mistake%s to %s" % (verb, n_err, "" if n_err == 1 else "s",
                                                       ", ".join("archive/" + f for f in files)))
    if n_att:
        parts.append("%s %d graded question%s to %s" % (verb, n_att, "" if n_att == 1 else "s",
                                                      ", ".join("archive/" + f for f in sorted(plan["rotated"]))))
    if not parts:
        parts.append("nothing to move")
    parts.append("ID parity OK (%d mistake id%s)" % (len(plan["ids"]), "" if len(plan["ids"]) == 1 else "s"))
    if not args.dry_run and (n_err or n_att):
        parts.append(".bak copies kept")
    if stale:
        parts.append("%s %d scratch file%s older than %d days in .indelible/tmp" % (
            "would clear" if args.dry_run else "cleared", len(stale) if args.dry_run else cleared,
            "" if len(stale) == 1 else "s", TMP_KEEP_DAYS))
    out("compact %s%s: %s" % (subj.id, " (dry run)" if args.dry_run else "", " · ".join(parts)))
    if inbox_done:
        out("inbox/ holds %d file%s, %d already filed as evidence: ask the learner before deleting them "
            "(scripts never delete learner files)." % (inbox_total, "" if inbox_total == 1 else "s", inbox_done))
    return 0
