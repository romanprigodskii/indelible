"""Sheets, keys and evidence (CONTRACT section 7.4).

    sheet new    <subject> <id> --spec PATH --answers PATH [--replace] [--block ID]
    sheet lint   <subject> <id> [--budget-min N] [--block ID] [--at ISO] [--json]
    sheet build  <subject> <id> [--format pdf|html|md] [--date YYYY-MM-DD]
    sheet issue  <subject> <id> [--block ID]
    sheet sat    <subject> <id> [--start HH:MM] [--stop HH:MM] [--date YYYY-MM-DD]
    sheet void   <subject> <id> --reason TEXT
    sheet show   [subject] [--status S] [--json]
    scan ingest  <subject> <id> [PATHS...] [--typed FILE] [--transcript -] [--dir PROJECT] [--date YYYY-MM-DD]
    key open     <subject> <id>

Keys and accepted answers are never printed, except by ``key open``, which
works only once evidence of the attempt is filed.
Status flow: built -> linted -> rendered -> issued -> sat -> graded (or void).
A sealed instrument (issued or later) is never edited.

A sheet built ahead for a block is linked to it early (``sheet new`` or
``sheet lint`` with ``--block``): lint then sizes it against that block (L5)
and judges a recheck at the block's start (L7). ``sheet issue`` checks both
again, so a sheet over its block's budget, or a recheck that is no longer
eligible, is never issued.

Every date and time here comes from the workspace clock (its time zone), the
same clock as ``session open`` and ``session close``.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from lib import CheckFailed, UsageError, dates, learning, lint, render, schema
from lib import io as fio
from lib import ws as wsmod

EDITABLE = ("built", "linted", "rendered")
SEALED = ("issued", "sat", "graded", "void")
KEY_OPTIONAL_TYPES = ("theory", "external", "example", "triage")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif", ".tif", ".tiff")
HEIC_EXTS = (".heic", ".heif")
CONVERT_TIMEOUT_S = 60
BUDGET_EXEMPT = lint.BUDGET_EXEMPT
PROJECT_SKIP_DIRS = {".git", ".hg", ".svn", "target", "node_modules", "__pycache__", ".venv", "venv",
                     ".idea", ".vscode", "dist", "build", ".mypy_cache", ".pytest_cache", ".tox"}
PROJECT_MAX_FILES = 400
PROJECT_MAX_FILE_BYTES = 1024 * 1024


def _out(line=""):
    sys.stdout.write(line + "\n")


# ==========================================================================
# Registration
# ==========================================================================

def register(subparsers):
    p = subparsers.add_parser("sheet", help="seal, check, render, issue and track sheets")
    sp = p.add_subparsers(dest="sheet_cmd", metavar="<action>")

    a = sp.add_parser("new", help="validate a builder's spec, seal its key (mode 600) and delete the answers file")
    a.add_argument("subject")
    a.add_argument("id")
    a.add_argument("--spec", required=True, metavar="PATH", help="the visible sheet spec (JSON)")
    a.add_argument("--answers", required=True, metavar="PATH", help="the answers file; deleted once sealed")
    a.add_argument("--replace", action="store_true", help="rebuild a sheet that is not issued yet")
    a.add_argument("--block", default=None, metavar="ID",
                   help="the block it is built for (lint sizes and times it against that block)")
    a.set_defaults(func=cmd_new)

    a = sp.add_parser("lint", help="run the sheet checker (L1-L9, W1-W2)")
    a.add_argument("subject")
    a.add_argument("id")
    a.add_argument("--budget-min", type=float, default=None, metavar="N",
                   help="minutes available (default: 0.8 x the linked block, else of the default session)")
    a.add_argument("--block", default=None, metavar="ID",
                   help="link the block it will be sat in: L5 uses its minutes, L7 judges at its start")
    a.add_argument("--at", default=None, metavar="ISO", help="judge L7 (cold validity) at this time instead")
    a.add_argument("--json", action="store_true")
    a.set_defaults(func=cmd_lint)

    a = sp.add_parser("build", help="render a linted sheet (typst, then Chrome/Edge PDF, then HTML, then Markdown)")
    a.add_argument("subject")
    a.add_argument("id")
    a.add_argument("--format", choices=list(render.FORMATS), default=None)
    a.add_argument("--date", default=None, metavar="YYYY-MM-DD", help="the date printed on the sheet")
    a.set_defaults(func=cmd_build)

    a = sp.add_parser("issue", help="hand a rendered sheet to the learner")
    a.add_argument("subject")
    a.add_argument("id")
    a.add_argument("--block", default=None, metavar="ID")
    a.set_defaults(func=cmd_issue)

    a = sp.add_parser("sat", help="record the sitting: date, start and stop times")
    a.add_argument("subject")
    a.add_argument("id")
    a.add_argument("--start", default=None, metavar="HH:MM")
    a.add_argument("--stop", default=None, metavar="HH:MM")
    a.add_argument("--date", default=None, metavar="YYYY-MM-DD")
    a.set_defaults(func=cmd_sat)

    a = sp.add_parser("void", help="drop a sheet (its record stays)")
    a.add_argument("subject")
    a.add_argument("id")
    a.add_argument("--reason", required=True)
    a.set_defaults(func=cmd_void)

    a = sp.add_parser("show", help="list the sheets")
    a.add_argument("subject", nargs="?", default=None)
    a.add_argument("--status", choices=schema.SHEET_STATUSES, default=None)
    a.add_argument("--json", action="store_true")
    a.set_defaults(func=cmd_show)

    p = subparsers.add_parser("scan", help="file evidence of an attempt (photos, PDFs, typed answers, transcripts)")
    sp = p.add_subparsers(dest="scan_cmd", metavar="<action>")
    a = sp.add_parser("ingest", help="copy evidence into scans/ (or answers/) and link it to the sheet")
    a.add_argument("subject")
    a.add_argument("id")
    a.add_argument("paths", nargs="*", metavar="PATH")
    a.add_argument("--typed", default=None, metavar="FILE", help="typed answers (a file, or - for stdin)")
    a.add_argument("--transcript", default=None, metavar="-",
                   help="Claude's transcript of a photo pasted into chat (- for stdin, or a file)")
    a.add_argument("--dir", dest="project", default=None, metavar="PROJECT",
                   help="a code project: its files are copied, with their folder layout, to answers/<id>/")
    a.add_argument("--date", default=None, metavar="YYYY-MM-DD", help="the date the sheet was taken")
    a.set_defaults(func=cmd_scan_ingest)

    p = subparsers.add_parser("key", help="open a sealed key (only after the attempt is filed)")
    sp = p.add_subparsers(dest="key_cmd", metavar="<action>")
    a = sp.add_parser("open", help="print the key; refused until evidence of the attempt is filed")
    a.add_argument("subject")
    a.add_argument("id")
    a.set_defaults(func=cmd_key_open)


# ==========================================================================
# Helpers
# ==========================================================================

def _now_iso(ws):
    return dates.fmt_iso(ws.now())


def _plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def _block_for(ws, subj, block_id):
    """The block row for ``--block``, checked to exist and to belong to the subject."""
    b = ws.get_block(block_id)
    if b is None:
        raise UsageError("Unknown block %s. Run: indelible.py plan list" % block_id)
    if b.get("subject") not in (None, subj.id):
        raise UsageError("Block %s belongs to %s, not %s" % (block_id, b.get("subject"), subj.id))
    return b


def _num(x):
    return render._num(x)


def _open(args):
    ws = wsmod.from_args(args)
    subj = ws.resolve_subject(getattr(args, "subject", None))
    return ws, subj


def _check_id(sheet_id):
    if not schema.is_sheet_id(sheet_id):
        raise UsageError("A sheet id must match [a-z0-9][a-z0-9-]{1,60}: %r" % sheet_id)


def _find(rows, sheet_id):
    for i, r in enumerate(rows):
        if r.get("id") == sheet_id:
            return i, r
    return None, None


def _require_row(subj, sheet_id):
    _check_id(sheet_id)
    rows = subj.load_sheets()
    i, row = _find(rows, sheet_id)
    if row is None:
        raise UsageError("No sheet '%s' in %s. Run: indelible.py sheet show %s" % (sheet_id, subj.id, subj.id))
    return rows, i, row


def _save_row(subj, rows, i, row):
    rows[i] = row
    subj.save_sheets(rows)


def _load_spec(subj, sheet_id):
    spec = fio.read_json(subj.spec_path(sheet_id))
    if not isinstance(spec, dict):
        raise UsageError("The sealed spec for %s is missing: %s" % (sheet_id, subj.rel(subj.spec_path(sheet_id))))
    return spec


def _read_input_json(path, what):
    path = Path(path).expanduser()
    if not path.is_file():
        raise UsageError("The %s file does not exist: %s" % (what, path))
    return fio.read_json(path)


def _parse_date(value, flag="--date"):
    if value is None:
        return None
    if not dates.is_date(value):
        raise UsageError("%s must be YYYY-MM-DD (got %r)" % (flag, value))
    return dates.to_date(value)


def _sha256(path):
    h = hashlib.sha256()
    with open(str(path), "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _ask_ids(spec):
    return [a.get("id") for it in (spec.get("items") or []) if isinstance(it, dict)
            for a in (it.get("asks") or []) if isinstance(a, dict)]


def _topics_in(spec):
    """Topics of the items, and of any question that carries its own topic (e.g. one test group)."""
    out = []
    for it in spec.get("items") or []:
        if not isinstance(it, dict):
            continue
        if it.get("topic") and it["topic"] not in out:
            out.append(it["topic"])
        for a in it.get("asks") or []:
            if isinstance(a, dict) and a.get("topic") and a["topic"] not in out:
                out.append(a["topic"])
    return out


def _subject_rel(subj, path):
    try:
        return Path(path).resolve().relative_to(subj.root.resolve()).as_posix()
    except ValueError:
        return subj.rel(path)


def _secure_keys_dir(subj):
    fio.ensure_dir(subj.keys_dir)
    try:
        os.chmod(str(subj.keys_dir), 0o700)
    except OSError:
        pass


# ==========================================================================
# sheet new
# ==========================================================================

def _spec_problems(spec, answers, subj, sheet_id):
    probs = list(schema.validate_sheetspec(spec))
    if isinstance(spec, dict):
        if spec.get("id") != sheet_id:
            probs.append("spec.id is %r but the sheet id is %r" % (spec.get("id"), sheet_id))
        if spec.get("subject") != subj.id:
            probs.append("spec.subject is %r but the subject is %r" % (spec.get("subject"), subj.id))
        known = set(subj.topic_ids())
        unknown = [t for t in _topics_in(spec) if t not in known]
        if unknown:
            probs.append("unknown topic%s %s (add with: indelible.py topic add)"
                         % ("s" if len(unknown) > 1 else "", ", ".join(unknown)))
    probs += schema.validate_answers(answers)
    if isinstance(spec, dict) and isinstance(answers, dict):
        ids = [a for a in _ask_ids(spec) if a]
        extra = [k for k in answers if k not in ids]
        if extra:
            probs.append("the answers file has entries for questions not on the sheet: %s" % ", ".join(map(str, extra[:8])))
        if spec.get("type") not in KEY_OPTIONAL_TYPES:
            missing = [a for a in ids if a not in answers]
            if missing:
                probs.append("no key entry for question%s %s" % ("s" if len(missing) > 1 else "", ", ".join(missing[:8])))
    return probs


def _refuse_existing(rows, sheet_id, replace):
    """(index, row) of an existing sheet that may be rebuilt; raises if it may not."""
    i, old = _find(rows, sheet_id)
    if old is not None:
        st = old.get("status")
        if st in SEALED:
            raise CheckFailed("%s is %s: a sealed instrument is never edited after issue. "
                              "Build a new sheet with a new id." % (sheet_id, st))
        if not replace:
            raise CheckFailed("%s already exists (status %s). Pass --replace to rebuild it before issue."
                              % (sheet_id, st))
    return i, old


def _normalised_spec(spec, subj):
    """The spec as sealed: each item's layer filled from its topic when missing."""
    out = json.loads(json.dumps(spec))
    layers = dict((t["id"], t.get("layer")) for t in subj.topics())
    for it in out.get("items") or []:
        if isinstance(it, dict) and not it.get("layer") and layers.get(it.get("topic")):
            it["layer"] = layers[it["topic"]]
    return out


def cmd_new(args):
    ws, subj = _open(args)
    sheet_id = args.id
    _check_id(sheet_id)
    _refuse_existing(subj.load_sheets(), sheet_id, args.replace)
    spec = _read_input_json(args.spec, "spec")
    answers = _read_input_json(args.answers, "answers")
    probs = _spec_problems(spec, answers, subj, sheet_id)
    if probs:
        raise CheckFailed("sheet new refused for %s:\n  - %s" % (sheet_id, "\n  - ".join(probs)))

    ans_path = Path(args.answers).expanduser()
    spec_path = Path(args.spec).expanduser()
    if args.block:
        _block_for(ws, subj, args.block)
    with ws.lock():
        rows = subj.load_sheets()
        i, old = _refuse_existing(rows, sheet_id, args.replace)
        for d in (subj.specs_dir, subj.tmp_dir, subj.data_dir):
            fio.ensure_dir(d)
        _secure_keys_dir(subj)
        sealed = _normalised_spec(spec, subj)
        fio.write_json(subj.spec_path(sheet_id), sealed)
        key_path = subj.key_path(sheet_id)
        fio.write_json(key_path, answers, mode=0o600)
        try:
            os.chmod(str(key_path), 0o600)
        except OSError:
            pass
        sha = _sha256(key_path)
        n_asks = len(_ask_ids(sealed))
        row = {
            "v": 1, "id": sheet_id, "subject": subj.id, "type": sealed.get("type"),
            "measures": schema.measures(sealed.get("type")), "topics": _topics_in(sealed),
            "asks": n_asks, "est_min": sealed.get("est_min"), "status": "built",
            "created": (old or {}).get("created") or _now_iso(ws), "lint": None, "files": [],
            "key_sha": sha, "issued_at": None, "sat": {"start": None, "stop": None, "date": None},
            "evidence": [], "graded_at": None, "opens_unsat": 0,
            "block": args.block or (old or {}).get("block"),
        }
        if old is not None:
            rows[i] = row
        else:
            rows.append(row)
        subj.save_sheets(rows)
        # The builder writes its answers file into <subject>/.indelible/tmp/, and only a
        # file there is deleted once the key is sealed: the scripts never delete a file
        # outside the workspace.
        if _inside_dir(ans_path, subj.tmp_dir):
            try:
                ans_path.unlink()
            except OSError as exc:
                sys.stderr.write("indelible: could not delete the answers file %s (%s); delete it now\n"
                                 % (ans_path, type(exc).__name__))
        else:
            sys.stderr.write("indelible: the key is sealed, but the answers file %s is outside %s, so it "
                             "was left where it is. It holds the answers: delete it without opening it, "
                             "and write the next one inside %s\n"
                             % (ans_path, ws.rel(subj.tmp_dir), ws.rel(subj.tmp_dir)))
        # The builder's scratch copy of the spec is sealed now; it is not kept in tmp.
        if _inside_dir(spec_path, subj.tmp_dir):
            try:
                spec_path.unlink()
            except OSError:
                pass
    _out("%s built: %s, ~%s min, key sealed sha256:%s" % (sheet_id, _plural(n_asks, "question"),
                                                           _num(sealed.get("est_min")), sha[:12]))
    return 0


def _inside_dir(path, folder):
    try:
        Path(path).resolve().relative_to(Path(folder).resolve())
        return True
    except (ValueError, OSError):
        return False


# ==========================================================================
# sheet lint
# ==========================================================================

def cmd_lint(args):
    ws, subj = _open(args)
    at = None
    if args.at:
        try:
            at = dates.parse_iso(args.at, tz=ws.tzinfo())
        except ValueError:
            raise UsageError("--at must be an ISO time like 2026-10-14T07:00+01:00 (got %r)" % args.at)
    with ws.lock():
        rows, i, row = _require_row(subj, args.id)
        if args.block:
            _block_for(ws, subj, args.block)
        spec = _load_spec(subj, args.id)
        results = lint.run(ws, subj, spec, row, budget_min=args.budget_min, block=args.block, at=at)
        ok = lint.passed(results)
        st = row.get("status")
        note = None
        if st in EDITABLE:
            if args.block:
                row["block"] = args.block
            row["lint"] = "PASS" if ok else "FAIL"
            if ok and st == "built":
                row["status"] = "linted"
            elif not ok and st in ("linted", "rendered"):
                row["status"] = "built"
            _save_row(subj, rows, i, row)
        else:
            note = "(%s is %s: the record is unchanged)" % (args.id, st)
    fails = [r["rule"] for r in results if r["status"] == "FAIL"]
    warns = [r["rule"] for r in results if r["status"] == "WARN"]
    if args.json:
        _out(json.dumps({"sheet": args.id, "result": "PASS" if ok else "FAIL", "rules": results},
                        ensure_ascii=False, indent=2))
        return 0 if ok else 1
    for r in results:
        _out(lint.format_line(r))
    if ok:
        _out("lint PASS: %s (%d warning%s)" % (args.id, len(warns), "" if len(warns) == 1 else "s"))
    else:
        _out("lint FAIL: %s (%s)" % (args.id, ", ".join(fails)))
    if note:
        _out(note)
    return 0 if ok else 1


# ==========================================================================
# sheet build
# ==========================================================================

def _sheet_date(ws, subj, row, spec, arg):
    """The date printed on the sheet: --date, else the linked block's day, else
    spec.date, else today when a session is open (the sheet is sat now), else
    None: a sheet built ahead with no block prints a blank date line."""
    d = _parse_date(arg)
    if d:
        return d
    bid = row.get("block") or spec.get("block")
    if bid:
        b = ws.get_block(bid)
        if b and b.get("start"):
            try:
                return dates.parse_iso(b["start"]).astimezone(ws.tzinfo()).date()
            except ValueError:
                pass
    if isinstance(spec.get("date"), str) and dates.is_date(spec["date"]):
        return dates.to_date(spec["date"])
    if subj.read_session_lock() is not None:
        return ws.today()
    return None


def cmd_build(args):
    ws, subj = _open(args)
    with ws.lock():
        rows, i, row = _require_row(subj, args.id)
        st = row.get("status")
        if st in SEALED:
            files = ", ".join(row.get("files") or []) or "none on record"
            raise CheckFailed("%s is %s: a sealed sheet is not rebuilt. Its files: %s" % (args.id, st, files))
        if row.get("lint") != "PASS":
            raise CheckFailed("%s has not passed lint (lint: %s). Run: indelible.py sheet lint %s %s"
                              % (args.id, row.get("lint") or "not run", subj.id, args.id))
        spec = _load_spec(subj, args.id)
        day = _sheet_date(ws, subj, row, spec, args.date)
        cfg = ws.load_config()
        preferred = (cfg.get("render") or {}).get("backend")
        subj_fmt = subj.load().get("format") or {}
        tools = spec.get("tools") or subj_fmt.get("tools") or "none"
        lang = (cfg.get("learner") or {}).get("instruction_lang") or "en"
        res = render.render_sheet(spec, subj.sheet_month_dir(day or ws.today()), args.id, fmt=args.format,
                                  preferred=preferred, date=day if day is not None else False, tools=tools,
                                  lang=lang, profile=subj.load().get("profile"))
        row["files"] = [_subject_rel(subj, f) for f in res["files"]]
        row["status"] = "rendered"
        _save_row(subj, rows, i, row)
    primary = Path(res["files"][0])
    _out(str(primary))
    fell_back = args.format == "pdf" or (args.format is None and res["notes"])
    if fell_back and res["backend"] not in render.PDF_BACKENDS:
        why = "; ".join(res["notes"]) or "no PDF renderer"
        _out("note: no PDF (%s). The learner can open the %s file and print it."
             % (why, "HTML" if res["backend"] == "html" else "Markdown"))
    return 0


# ==========================================================================
# sheet issue / sat / void / show
# ==========================================================================

def cmd_issue(args):
    ws, subj = _open(args)
    with ws.lock():
        rows, i, row = _require_row(subj, args.id)
        st = row.get("status")
        if st in SEALED:
            raise CheckFailed("%s is already %s." % (args.id, st))
        if st != "rendered":
            raise CheckFailed("%s is %s, not rendered yet. Run: indelible.py sheet build %s %s"
                              % (args.id, st, subj.id, args.id))
        if row.get("lint") != "PASS":
            raise CheckFailed("%s has not passed lint; it cannot be issued." % args.id)
        block_id = args.block or row.get("block")
        if block_id:
            _block_for(ws, subj, block_id)
        spec = _load_spec(subj, args.id)
        _issue_checks(ws, subj, spec, row, block_id)
        if args.block:
            row["block"] = args.block
        row["status"] = "issued"
        row["issued_at"] = _now_iso(ws)
        _save_row(subj, rows, i, row)
    _out("%s issued%s" % (args.id, (" for block %s" % block_id) if block_id else ""))
    return 0


def _issue_checks(ws, subj, spec, row, block_id):
    """Law 4 and Law 3 at the moment of issue: never over the block's budget, never
    a recheck that is not eligible at the time it will be sat. Refuses (exit 1)."""
    probs = []
    if block_id and spec.get("type") not in BUDGET_EXEMPT:
        budget, basis = lint.budget_for(ws, subj, spec, row, block=block_id)
        try:
            est = float(spec.get("est_min"))
        except (TypeError, ValueError):
            est = None
        if budget is not None and est is not None and est > budget + 1e-9:
            probs.append("~%s min is over the budget of %s min (%s): cut questions and rebuild it"
                         % (_num(est), _num(round(budget, 1)), basis))
    if spec.get("type") == "cold":
        results = lint.run(ws, subj, spec, row, block=block_id)
        for r in results:
            if r["rule"] == "L7" and r["status"] == "FAIL":
                probs.append("the recheck is not valid when it will be sat: " + r["detail"])
    if probs:
        raise CheckFailed("Refused: %s was not issued.\n  %s" % (spec.get("id") or row.get("id"), "\n  ".join(probs)))


def cmd_sat(args):
    ws, subj = _open(args)
    for flag, v in (("--start", args.start), ("--stop", args.stop)):
        if v is not None and not dates.is_hhmm(v):
            raise UsageError("%s must be HH:MM (got %r)" % (flag, v))
    day = _parse_date(args.date)
    with ws.lock():
        rows, i, row = _require_row(subj, args.id)
        st = row.get("status")
        if st not in ("issued", "sat"):
            if st in ("graded", "void"):
                raise CheckFailed("%s is %s; its sitting cannot change." % (args.id, st))
            raise CheckFailed("%s is %s, not issued. Run: indelible.py sheet issue %s %s"
                              % (args.id, st, subj.id, args.id))
        sitting = dict(row.get("sat") or {})
        if args.start is not None:
            sitting["start"] = dates.parse_hhmm(args.start).strftime("%H:%M")
        if args.stop is not None:
            sitting["stop"] = dates.parse_hhmm(args.stop).strftime("%H:%M")
        if day is not None:
            sitting["date"] = day.isoformat()
        elif not sitting.get("date"):
            sitting["date"] = ws.today().isoformat()
        for k in ("start", "stop", "date"):
            sitting.setdefault(k, None)
        row["sat"] = sitting
        row["status"] = "sat"
        _save_row(subj, rows, i, row)
    span = ""
    if sitting.get("start") or sitting.get("stop"):
        span = " (%s–%s)" % (sitting.get("start") or "?", sitting.get("stop") or "?")
    _out("%s taken on %s%s" % (args.id, sitting["date"], span))
    for line in _contamination_notes(ws, subj, row, sitting):
        _out(line)
    return 0


def _contamination_notes(ws, subj, row, sitting):
    """A recheck sat within 24 h of an exposure to one of its topics: say so at once
    (grade record will record those questions as not counted)."""
    if row.get("type") != "cold" or not sitting.get("date"):
        return []
    try:
        at = dates.at_time(sitting["date"], sitting.get("start") or sitting.get("stop") or "12:00", ws.tzinfo())
        spec = _load_spec(subj, row.get("id"))
    except (ValueError, UsageError):
        return []
    exposures = subj.load_exposures()
    out, seen = [], set()
    for it in spec.get("items") or []:
        t = it.get("topic") if isinstance(it, dict) else None
        if not t or t in seen:
            continue
        seen.add(t)
        h = learning.hours_since_exposure(t, exposures, at)
        if h is not None and h < learning.NO_EXPOSURE_H:
            out.append("WARN: %s was seen %.0f h before this sitting: its questions will be recorded as not "
                       "counted (seen too recently)." % (t, h))
    return out


def cmd_void(args):
    ws, subj = _open(args)
    reason = " ".join((args.reason or "").split())
    if not reason:
        raise UsageError("--reason must not be empty")
    with ws.lock():
        rows, i, row = _require_row(subj, args.id)
        st = row.get("status")
        if st == "void":
            raise CheckFailed("%s is already void." % args.id)
        if st == "graded":
            raise CheckFailed("%s is graded; its results stand and it cannot be voided." % args.id)
        row["status"] = "void"
        row["void"] = {"reason": reason[:300], "at": _now_iso(ws), "was": st}
        _save_row(subj, rows, i, row)
    _out("%s void (was %s): %s" % (args.id, st, reason[:300]))
    return 0


def cmd_show(args):
    ws, subj = _open(args)
    rows = subj.load_sheets()
    if args.status:
        rows = [r for r in rows if r.get("status") == args.status]
    if args.json:
        _out(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        _out("No sheets%s in %s." % ((" with status %s" % args.status) if args.status else "", subj.id))
        return 0
    for r in rows:
        extra = []
        if r.get("issued_at"):
            extra.append("issued %s" % str(r["issued_at"])[:10])
        sitting = r.get("sat") or {}
        if sitting.get("date"):
            extra.append("taken %s" % sitting["date"])
        if r.get("evidence"):
            extra.append("evidence %d" % len(r["evidence"]))
        if r.get("block"):
            extra.append("block %s" % r["block"])
        _out("%-32s %-11s %-9s %3s q  ~%s min  lint %s%s" % (
            r.get("id"), r.get("type"), r.get("status"), r.get("asks", "?"), _num(r.get("est_min")),
            r.get("lint") or "-", ("  " + " · ".join(extra)) if extra else ""))
    return 0


# ==========================================================================
# scan ingest
# ==========================================================================

def _taken(folder, stem):
    return any(p.stem == stem for p in folder.iterdir()) if folder.exists() else False


def _numbering_started(folder, base):
    prefix = base + "-p"
    return any(p.stem.startswith(prefix) for p in folder.iterdir()) if folder.exists() else False


def _free_stem(folder, base, numbered, start=1):
    """``base`` if free and not numbered, else ``base-pN`` with the first free N."""
    if not numbered and not _taken(folder, base) and not _numbering_started(folder, base):
        return base, start
    k = start
    while _taken(folder, "%s-p%d" % (base, k)):
        k += 1
    return "%s-p%d" % (base, k), k + 1


def convert_heic(src, dest):
    """HEIC/HEIF -> JPEG with sips (macOS) or heif-convert. Returns (ok, tool)."""
    src, dest = Path(src), Path(dest)
    cmds = []
    sips = shutil.which("sips")
    if sips:
        cmds.append(("sips", [sips, "-s", "format", "jpeg", str(src), "--out", str(dest)]))
    hc = shutil.which("heif-convert")
    if hc:
        cmds.append(("heif-convert", [hc, str(src), str(dest)]))
    for name, cmd in cmds:
        try:
            r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               stdin=subprocess.DEVNULL, timeout=CONVERT_TIMEOUT_S)
        except (OSError, subprocess.SubprocessError):
            continue
        if r.returncode == 0 and dest.is_file() and dest.stat().st_size > 0:
            return True, name
        try:
            dest.unlink()
        except OSError:
            pass
    return False, None


def read_stdin_text():
    """stdin as text, always decoded as UTF-8 (a BOM is dropped), whatever the locale says."""
    buf = getattr(sys.stdin, "buffer", None)
    if buf is None:
        return sys.stdin.read()
    return buf.read().decode("utf-8-sig", errors="replace")


def _read_source(value, what):
    if value == "-":
        text = read_stdin_text()
    else:
        p = Path(value).expanduser()
        if not p.is_file():
            raise UsageError("The %s file does not exist: %s" % (what, p))
        text = fio.read_text(p) or ""
    if not text.strip():
        raise UsageError("The %s is empty." % what)
    return text.replace("\r\n", "\n")


def _project_files(root):
    """(relative path, source path) of a code project's files, skipping build output and hidden folders."""
    root = Path(root)
    found, skipped = [], 0
    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = sorted(d for d in dirnames if d not in PROJECT_SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            src = Path(dirpath) / name
            try:
                if not src.is_file() or src.is_symlink() or src.stat().st_size > PROJECT_MAX_FILE_BYTES:
                    skipped += 1
                    continue
            except OSError:
                skipped += 1
                continue
            found.append((src.relative_to(root).as_posix(), src))
            if len(found) > PROJECT_MAX_FILES:
                raise UsageError("%s has more than %d files; point --dir at the project folder itself"
                                 % (root, PROJECT_MAX_FILES))
    return found, skipped


def cmd_scan_ingest(args):
    ws, subj = _open(args)
    if not args.paths and args.typed is None and args.transcript is None and args.project is None:
        raise UsageError("Give the evidence: photo or PDF paths, --typed FILE, --transcript -, or --dir PROJECT")
    project = None
    if args.project is not None:
        project = Path(args.project).expanduser()
        if not project.is_dir():
            raise UsageError("--dir needs a folder: %s" % args.project)
        project = project.resolve()
        if _inside_dir(project, ws.root):
            raise UsageError("--dir points inside the study workspace; give the learner's own project folder")
    sources = []
    for raw in args.paths:
        p = Path(raw).expanduser()
        if not p.is_file():
            raise UsageError("No such file: %s" % raw)
        sources.append(p.resolve())
    typed_text = _read_source(args.typed, "typed answers") if args.typed is not None else None
    transcript = _read_source(args.transcript, "transcript") if args.transcript is not None else None
    arg_day = _parse_date(args.date)

    notes = []
    with ws.lock():
        rows, i, row = _require_row(subj, args.id)
        st = row.get("status")
        if st not in ("issued", "sat", "graded"):
            raise CheckFailed("%s is %s: evidence is filed only for a sheet that has been issued. %s"
                              % (args.id, st, "Run: indelible.py sheet issue %s %s" % (subj.id, args.id)
                                 if st in EDITABLE else ""))
        sitting = dict(row.get("sat") or {})
        day = arg_day or (dates.to_date(sitting["date"]) if sitting.get("date") and dates.is_date(sitting["date"]) else ws.today())
        base = "%s-%s-answers" % (day.isoformat(), args.id)
        scans = fio.ensure_dir(subj.scans_dir)
        now = _now_iso(ws)
        entries = []
        numbered = len(sources) > 1
        k = 1
        for src in sources:
            ext = src.suffix.lower() or ".bin"
            stem, k = _free_stem(scans, base, numbered, k)
            dest = scans / (stem + ext)
            shutil.copy2(str(src), str(dest))
            entry = {"kind": "scan", "file": _subject_rel(subj, dest), "original": None}
            if ext in HEIC_EXTS:
                jpg = scans / (stem + ".jpg")
                ok, tool = convert_heic(dest, jpg)
                if ok:
                    entry = {"kind": "scan", "file": _subject_rel(subj, jpg), "original": _subject_rel(subj, dest)}
                else:
                    notes.append("could not convert %s to JPEG (no sips or heif-convert); the original is filed. "
                                  "Ask the learner to set the camera to Most Compatible or share as JPEG."
                                  % src.name)
            elif ext not in IMAGE_EXTS + (".pdf", ".txt", ".md"):
                entry["kind"] = "file"
            entry["sha256"] = _sha256(subj.root / entry["file"])
            entries.append(entry)
        if typed_text is not None:
            dest = subj.typed_answers_path(args.id)
            fio.write_text(dest, typed_text)
            entries.append({"kind": "typed", "file": _subject_rel(subj, dest), "original": None,
                            "sha256": _sha256(dest)})
        if transcript is not None:
            stem, k = _free_stem(scans, base, False, k)
            dest = scans / (stem + ".txt")
            fio.write_text(dest, transcript, backup=False)
            entries.append({"kind": "chat-image+transcript", "file": _subject_rel(subj, dest), "original": None,
                            "sha256": _sha256(dest)})
        if project is not None:
            files, skipped = _project_files(project)
            if not files:
                raise UsageError("No files to copy in %s" % project)
            snap = subj.answers_dir / args.id
            n = 1
            while snap.exists():
                n += 1
                snap = subj.answers_dir / ("%s-%d" % (args.id, n))
            h = hashlib.sha256()
            for rel, src in files:
                dest = snap / rel
                fio.ensure_dir(dest.parent)
                shutil.copy2(str(src), str(dest))
                h.update(rel.encode("utf-8") + b"\0")
                h.update(_sha256(dest).encode("ascii"))
            entries.append({"kind": "project", "file": _subject_rel(subj, snap) + "/", "original": None,
                            "sha256": h.hexdigest(), "source": str(project), "files": len(files)})
            if skipped:
                notes.append("skipped %d file%s in %s (hidden, over 1 MB, or links)"
                             % (skipped, "" if skipped == 1 else "s", project))
        for e in entries:
            idx = {"v": 1, "at": now, "sheet": args.id, "date": day.isoformat(),
                   "kind": e["kind"], "file": e["file"], "original": e["original"], "sha256": e["sha256"]}
            if e.get("source"):
                idx["source"], idx["files"] = e["source"], e["files"]
            subj.append_scan_index(idx)
        evidence = list(row.get("evidence") or [])
        for e in entries:
            ev = {"kind": e["kind"], "file": e["file"], "at": now}
            if e["original"]:
                ev["original"] = e["original"]
            if e.get("source"):
                ev["source"], ev["files"] = e["source"], e["files"]
            evidence.append(ev)
        row["evidence"] = evidence
        marked = False
        if st == "issued":
            row["status"] = "sat"
            if not sitting.get("date"):
                sitting["date"] = day.isoformat()
            for key in ("start", "stop", "date"):
                sitting.setdefault(key, None)
            row["sat"] = sitting
            marked = True
        _save_row(subj, rows, i, row)
    _out("Filed %d evidence file%s for %s: %s" % (len(entries), "" if len(entries) == 1 else "s", args.id,
                                                  ", ".join(e["file"] for e in entries)))
    if marked:
        _out("%s marked as taken (%s)" % (args.id, row["sat"]["date"]))
    for n in notes:
        _out("note: " + n)
    return 0


# ==========================================================================
# key open
# ==========================================================================

def cmd_key_open(args):
    ws, subj = _open(args)
    with ws.lock():
        rows, i, row = _require_row(subj, args.id)
        st = row.get("status")
        evidence = row.get("evidence") or []
        if st not in ("sat", "graded") or not evidence:
            raise CheckFailed(
                "Refused: the key for %s opens only after the attempt is filed (status %s, evidence %d). "
                "File it first: indelible.py scan ingest %s %s <photos> (or --typed FILE, or --transcript -)"
                % (args.id, st, len(evidence), subj.id, args.id))
        key_path = subj.key_path(args.id)
        if not key_path.is_file():
            raise CheckFailed("No sealed key on file for %s." % args.id)
        key = fio.read_json(key_path)
        subj.append_key_opened({"v": 1, "at": _now_iso(ws), "sheet": args.id})
    _out(json.dumps(key, ensure_ascii=False, indent=2))
    return 0
