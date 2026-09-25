"""Setup commands: doctor, init, subject add|list, set, schema.

    doctor [--json] [--quick]
    init <path> [--pointer] [--timezone TZ]
    subject add <id> --title T --profile P [--from subject.json] [--state S]
    subject list
    set <root|subject-id> <dotted.path> <json-value> [--dry-run] [--force]
    schema [<record>] [--json]
"""

import contextlib
import copy
import io as stdio
import json
import math
import os
import platform
import shutil
import string
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from lib import CheckFailed, IndelibleError, UsageError, SKILL_DIR, SCHEMA_VERSION
from lib import dates, schema
from lib import io as fio
from lib import ws as wsmod

CLOUD_MARKERS = ["OneDrive", "iCloud", "Mobile Documents", "Dropbox", "CloudStorage", "Google Drive"]
LATEX_ENGINES = ("tectonic", "xelatex", "lualatex")
RENDER_TIMEOUT_S = 60
# The same as lib.render.BROWSER_OFFLINE_FLAGS (this fallback must not import render):
# a headless test print makes no network connections.
BROWSER_OFFLINE_FLAGS = (
    "--disable-background-networking", "--disable-component-update", "--disable-sync",
    "--disable-default-apps", "--no-pings", "--metrics-recording-only",
    "--proxy-server=127.0.0.1:9", "--host-resolver-rules=MAP * ~NOTFOUND",
)


def register(subparsers):
    p = subparsers.add_parser("doctor", help="check Python, the workspace, the time zone and the sheet renderers")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--quick", action="store_true",
                   help="presence checks only: no test compile or test print, nothing recorded")
    p.set_defaults(func=cmd_doctor)

    p = subparsers.add_parser("init", help="create a workspace folder")
    p.add_argument("path", help="where the workspace goes (outside the skill folder)")
    p.add_argument("--pointer", action="store_true", help="remember it in ~/.indelible/workspace")
    p.add_argument("--timezone", default=None, help="IANA time zone, e.g. Europe/Lisbon (default: detected)")
    p.set_defaults(func=cmd_init)

    p = subparsers.add_parser("subject", help="add or list subjects")
    sp = p.add_subparsers(dest="subject_cmd", metavar="<add|list>")
    a = sp.add_parser("add", help="create a subject folder and register it")
    a.add_argument("id", help="subject id, e.g. ielts (lowercase letters, digits, hyphens)")
    a.add_argument("--title", default=None, help="display title")
    a.add_argument("--profile", default=None, choices=schema.PROFILES)
    a.add_argument("--from", dest="from_path", default=None, metavar="SUBJECT_JSON",
                   help="take subject.json values from this file")
    a.add_argument("--state", default="live", choices=schema.SUBJECT_STATES)
    a.set_defaults(func=cmd_subject_add)
    ls = sp.add_parser("list", help="list the subjects")
    ls.add_argument("--json", action="store_true")
    ls.set_defaults(func=cmd_subject_list)

    p = subparsers.add_parser("set", help="change one value in indelible.json or a subject.json (validated)")
    p.add_argument("target", help="root (indelible.json) or a subject id (its subject.json)")
    p.add_argument("path", help="dotted path, e.g. session.length_min or topics.T01.layer")
    p.add_argument("value", help="a JSON value, e.g. 45, '\"on_demand\"', '[44,72]'")
    p.add_argument("--dry-run", action="store_true", help="show the change without writing")
    p.add_argument("--force", action="store_true", help="allow unknown or read-only paths")
    p.set_defaults(func=cmd_set)

    p = subparsers.add_parser("schema", help="print a record's example and field notes")
    p.add_argument("record", nargs="?", default=None, help="|".join(schema.RECORD_NAMES))
    p.add_argument("--json", action="store_true", help="print only the example JSON")
    p.set_defaults(func=cmd_schema)


# ==========================================================================
# Shared helpers
# ==========================================================================

def _out(text=""):
    sys.stdout.write(text + "\n")


def deep_merge(base, over):
    """Merge ``over`` into a copy of ``base``: dicts recurse, everything else replaces."""
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def default_ceiling(target_min):
    return int(math.floor(1.4 * float(target_min) + 0.5))


def detect_iana_tz():
    """Best guess at the system's IANA time zone name, or None."""
    tz = os.environ.get("TZ", "").lstrip(":")
    if tz and schema.TZ_RE.match(tz):
        return tz
    try:
        link = os.readlink("/etc/localtime")
        if "zoneinfo/" in link:
            name = link.split("zoneinfo/", 1)[1]
            if schema.TZ_RE.match(name):
                return name
    except (OSError, AttributeError, NotImplementedError):
        pass
    try:
        text = fio.read_text("/etc/timezone")
        if text and schema.TZ_RE.match(text.strip()):
            return text.strip()
    except OSError:
        pass
    return None


def cloud_marker(path):
    s = str(path).lower()
    for m in CLOUD_MARKERS:
        if m.lower() in s:
            return m
    return None


def _inside(path, parent):
    try:
        Path(path).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False


def _render_after_change(args, ws):
    """Refresh generated files after a subject change. Returns a one-line note or None.

    If ``render`` is available it regenerates the views and CLAUDE.md sections;
    before render has ever run, the root CLAUDE.md subject list is updated here.
    """
    if not ws.render_state_path.exists():
        with ws.lock():
            wsmod.update_root_claude_md(ws)
    parser = getattr(args, "_parser", None)
    if parser is None:
        return None
    try:
        import argparse
        choices = []
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                choices = list(action.choices)
        if "render" not in choices:
            return None
        out, err = stdio.StringIO(), stdio.StringIO()
        rc = 0
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                sub = parser.parse_args(["--workspace", str(ws.root), "render", "all"])
                sub._parser = parser
                func = getattr(sub, "func", None) or getattr(sub, "handler", None)
                rc = func(sub) if func else 2
            except SystemExit as exc:
                rc = exc.code if isinstance(exc.code, int) else 2
            except IndelibleError as exc:
                rc = exc.exit_code
                err.write(str(exc))
        if rc is None or rc is True:
            rc = 0
        elif rc is False:
            rc = 1
        if rc == 0:
            return "Views rendered."
        msg = (err.getvalue().strip() or out.getvalue().strip()).split("\n")[0][:160]
        return "Views not refreshed (render said: %s). Run: indelible.py render" % (msg or "exit %s" % rc)
    except Exception as exc:
        return "Views not refreshed (%s). Run: indelible.py render" % (exc,)


# ==========================================================================
# doctor
# ==========================================================================

def _chrome_candidates():
    if os.environ.get("INDELIBLE_NO_BROWSER"):
        return []
    names = []
    home = Path(os.path.expanduser("~"))
    if sys.platform == "darwin":
        for app, exe in (("Google Chrome", "Google Chrome"), ("Chromium", "Chromium"),
                         ("Microsoft Edge", "Microsoft Edge"), ("Google Chrome Canary", "Google Chrome Canary")):
            for base in (Path("/Applications"), home / "Applications"):
                names.append(str(base / (app + ".app") / "Contents" / "MacOS" / exe))
    if os.name == "nt":
        for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base:
                names.append(str(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"))
                names.append(str(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"))
                names.append(str(Path(base) / "Chromium" / "Application" / "chrome.exe"))
    for exe in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                "microsoft-edge", "microsoft-edge-stable", "msedge", "chrome"):
        found = shutil.which(exe)
        if found:
            names.append(found)
    out = []
    for n in names:
        if n not in out and Path(n).is_file():
            out.append(n)
    return out


def _test_typst(exe):
    tmp = tempfile.mkdtemp(prefix="indelible-doctor-")
    try:
        src, pdf = Path(tmp) / "test.typ", Path(tmp) / "test.pdf"
        fio.write_text(src, "#set page(width: 8cm, height: 4cm)\n= indelible\nTest page: x² ≤ 3.\n", backup=False)
        subprocess.run([exe, "compile", str(src), str(pdf)], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=RENDER_TIMEOUT_S)
        ok = pdf.exists() and pdf.stat().st_size > 0
        return ok, "test compile passed" if ok else "test compile failed"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, "test compile failed (%s)" % type(exc).__name__
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _pdf_complete(pdf):
    try:
        with open(str(pdf), "rb") as fh:
            head = fh.read(5)
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 1024))
            tail = fh.read()
        return head.startswith(b"%PDF") and b"%%EOF" in tail
    except OSError:
        return False


def _run_until_pdf(cmd, pdf, timeout):
    """Run a headless browser until the PDF is complete, then stop it.

    Some Chrome builds write the PDF and then keep running (updater or crash
    reporter threads), so waiting for the process to exit is not enough.
    """
    import time as _time
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    deadline = _time.time() + timeout
    ok = False
    try:
        while _time.time() < deadline:
            if pdf.exists() and _pdf_complete(pdf):
                ok = True
                break
            if proc.poll() is not None:
                ok = pdf.exists() and _pdf_complete(pdf)
                break
            _time.sleep(0.2)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(5)
                except subprocess.TimeoutExpired:
                    pass
    return ok


def _test_chrome(exe):
    tmp = tempfile.mkdtemp(prefix="indelible-doctor-")
    try:
        page, pdf = Path(tmp) / "test.html", Path(tmp) / "test.pdf"
        fio.write_text(page, "<!doctype html><meta charset=\"utf-8\"><title>t</title>"
                             "<p>indelible test page: x² ≤ 3</p>", backup=False)
        cmd = [exe, "--headless", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
               "--use-mock-keychain", "--password-store=basic",
               "--disable-extensions"] + list(BROWSER_OFFLINE_FLAGS) + [
               "--user-data-dir=" + str(Path(tmp) / "profile"), "--no-pdf-header-footer",
               "--print-to-pdf=" + str(pdf), page.as_uri()]
        ok = _run_until_pdf(cmd, pdf, RENDER_TIMEOUT_S)
        return ok, "test print passed" if ok else "test print failed"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, "test print failed (%s)" % type(exc).__name__
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def fallback_backends(quick=False):
    """Renderer checks used when lib.render is not available."""
    rows = []
    typst = shutil.which("typst")
    if typst:
        ok, detail = (True, "found (not test-compiled)") if quick else _test_typst(typst)
        rows.append({"name": "typst", "found": True, "ok": ok, "detail": detail, "path": typst})
    else:
        rows.append({"name": "typst", "found": False, "ok": False, "detail": "not found", "path": None})
    for eng in LATEX_ENGINES:
        path = shutil.which(eng)
        rows.append({"name": eng, "found": bool(path), "ok": False,
                     "detail": "found; LaTeX sheets arrive in v0.2" if path else "not found", "path": path})
    chromes = _chrome_candidates()
    if chromes:
        exe = chromes[0]
        ok, detail = (True, "found (not test-printed)") if quick else _test_chrome(exe)
        rows.append({"name": "chrome", "found": True, "ok": ok, "detail": detail, "path": exe})
    else:
        rows.append({"name": "chrome", "found": False, "ok": False,
                     "detail": "no Chrome, Chromium or Edge found", "path": None})
    rows.append({"name": "html", "found": True, "ok": True, "detail": "always available (print from a browser)", "path": None})
    rows.append({"name": "md", "found": True, "ok": True, "detail": "always available", "path": None})
    return rows


def _normalise_backends(raw):
    rows = []
    if isinstance(raw, dict):
        raw = [dict(v, name=k) if isinstance(v, dict) else {"name": k, "ok": bool(v)} for k, v in raw.items()]
    for item in raw or []:
        if isinstance(item, str):
            rows.append({"name": item, "found": True, "ok": True, "detail": "ok", "path": None})
        elif isinstance(item, dict):
            name = item.get("name") or item.get("backend") or "?"
            ok = item.get("ok", item.get("works", item.get("available", item.get("verified", False))))
            rows.append({"name": name, "found": item.get("found", bool(ok)), "ok": bool(ok),
                         "detail": item.get("detail") or item.get("reason") or ("ok" if ok else "not available"),
                         "path": item.get("path")})
        elif isinstance(item, (list, tuple)) and item:
            rows.append({"name": str(item[0]), "found": True, "ok": bool(item[1]) if len(item) > 1 else True,
                         "detail": str(item[2]) if len(item) > 2 else "", "path": None})
    return rows


def detect_renderers(quick=False):
    """(rows, source). Prefers lib.render.detect_backends(); falls back to PATH checks."""
    try:
        from lib import render  # written by the sheet agent; may be absent
        fn = getattr(render, "detect_backends")
    except Exception:
        fn = None
    if fn is not None:
        try:
            try:
                raw = fn(quick=quick)
            except TypeError:
                raw = fn()
            rows = _normalise_backends(raw)
            if rows:
                return rows, "render"
        except Exception:
            pass
    return fallback_backends(quick), "doctor"


def first_working_backend(rows):
    for r in rows:
        if r.get("ok") and r.get("name") not in LATEX_ENGINES:
            return r["name"]
    return None


def _ws_writable(ws):
    try:
        fio.ensure_dir(ws.state_dir)
        fd, tmp = tempfile.mkstemp(prefix=".doctor-", dir=str(ws.state_dir))
        os.close(fd)
        os.unlink(tmp)
        return True
    except OSError:
        return False


def cmd_doctor(args):
    warnings = []
    ver = platform.python_version()
    py_ok = sys.version_info >= (3, 9)
    if not py_ok:
        warnings.append("Python %s is too old: indelible needs 3.9 or newer" % ver)

    root, source, detail = wsmod.discover(getattr(args, "workspace", None))
    ws = wsmod.Workspace(root) if root else None
    ws_info = {"found": bool(ws), "path": str(ws.root) if ws else None, "source": source,
               "writable": None, "cloud_sync": None, "data_version": None}
    cfg = {}
    if ws:
        ws_info["writable"] = _ws_writable(ws)
        if not ws_info["writable"]:
            warnings.append("the workspace is not writable: %s" % ws.root)
        marker = cloud_marker(ws.root)
        ws_info["cloud_sync"] = marker
        if marker:
            warnings.append("the workspace is inside a cloud-synced folder (%s); sync can hold files open "
                            "and create conflicted copies" % marker)
        try:
            cfg = ws.load_config()
            ws_info["data_version"] = cfg.get("v")
            if isinstance(cfg.get("v"), int) and cfg["v"] > SCHEMA_VERSION:
                warnings.append("the workspace data (v%s) is newer than this skill (v%s); update the skill "
                                "before writing" % (cfg["v"], SCHEMA_VERSION))
            probs = schema.validate_config(cfg)
            if probs:
                warnings.append("indelible.json: " + probs[0] + (" (+%d more)" % (len(probs) - 1) if len(probs) > 1 else ""))
        except IndelibleError as exc:
            warnings.append(str(exc))
    elif detail:
        warnings.append(detail)

    # The computer's zone is compared with the workspace zone at the real instant,
    # never at the test clock (INDELIBLE_NOW), so both offsets describe one moment.
    real_now = datetime.now().astimezone()
    tz_info = {"system_offset": dates.fmt_offset(real_now), "system_name": detect_iana_tz(),
               "workspace": cfg.get("timezone") if cfg else None, "workspace_offset": None,
               "workspace_loaded": None}
    if tz_info["workspace"]:
        problem = dates.zone_problem(tz_info["workspace"])
        tz_info["workspace_loaded"] = problem is None
        if problem:
            warnings.append(problem)
        else:
            try:
                from zoneinfo import ZoneInfo
                tz_info["workspace_offset"] = dates.fmt_offset(real_now.astimezone(ZoneInfo(tz_info["workspace"])))
                if tz_info["workspace_offset"] != tz_info["system_offset"]:
                    warnings.append("this computer is on UTC%s but the workspace time zone %s is UTC%s now: "
                                    "times are shown in the workspace zone"
                                    % (tz_info["system_offset"], tz_info["workspace"], tz_info["workspace_offset"]))
            except Exception:
                tz_info["workspace_offset"] = None
    elif ws:
        warnings.append("no time zone recorded; run: indelible.py set root timezone '\"Area/City\"'")

    rows, source_r = detect_renderers(quick=args.quick)
    backend = first_working_backend(rows)
    recorded = False
    if ws and backend and not args.quick and ws_info["writable"]:
        try:
            with ws.lock():
                cfg = ws.load_config(reload=True)
                cfg.setdefault("render", {})
                cfg["render"]["backend"] = backend
                cfg["render"]["verified_at"] = dates.fmt_iso(dates.now())
                ws.save_config(cfg)
                recorded = True
        except IndelibleError as exc:
            warnings.append("could not record the renderer: %s" % exc)

    report = {
        "python": ver, "python_ok": py_ok, "platform": sys.platform, "workspace": ws_info,
        "timezone": tz_info, "renderers": rows, "renderer_source": source_r, "backend": backend,
        "backend_recorded": recorded, "quick": bool(args.quick), "warnings": warnings,
    }
    if args.json:
        _out(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    _out("indelible doctor")
    _out("  Python      %s (%s)" % (ver, "ok" if py_ok else "too old: needs 3.9+"))
    if ws:
        _out("  Workspace   %s (%s)" % (ws.root, "writable" if ws_info["writable"] else "NOT writable"))
        _out("  Cloud sync  %s" % (ws_info["cloud_sync"] or "none detected"))
    else:
        _out("  Workspace   none found (run: indelible.py init <path>)")
    tz_line = "system UTC%s" % tz_info["system_offset"]
    if tz_info["system_name"]:
        tz_line += " (%s)" % tz_info["system_name"]
    if tz_info["workspace"]:
        tz_line += " · workspace %s" % tz_info["workspace"]
    _out("  Time zone   " + tz_line)
    _out("  Renderers")
    width = max(len(r["name"]) for r in rows) if rows else 6
    for r in rows:
        state = "ok" if r["ok"] else ("found" if r.get("found") else "no")
        extra = r.get("detail") or ""
        if r.get("path") and r["ok"]:
            extra += " (%s)" % r["path"]
        _out("    %s  %s%s" % (r["name"].ljust(width), state, (": " + extra) if extra else ""))
    if backend:
        if recorded:
            _out("  Sheets      %s (recorded in indelible.json)" % backend)
        elif args.quick:
            _out("  Sheets      %s (quick check: nothing recorded)" % backend)
        else:
            _out("  Sheets      %s" % backend)
    for w in warnings:
        _out("WARN " + w)
    return 0


# ==========================================================================
# init
# ==========================================================================

def root_claude_text():
    """The root CLAUDE.md with the skill's real script path in place of the ``<skill>`` placeholder,
    so a Claude that opens the workspace without the skill loaded can still run the brief."""
    text = wsmod.asset_text("root-CLAUDE.md")
    script = (SKILL_DIR / "scripts" / "indelible.py").as_posix()
    if any(c.isspace() for c in script):
        script = '"%s"' % script
    return text.replace("<skill>/scripts/indelible.py", script)


def cmd_init(args):
    path = Path(args.path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    if _inside(path, SKILL_DIR):
        raise CheckFailed("Refused: the workspace must live outside the skill folder (%s). "
                          "Learner data never goes inside the skill." % SKILL_DIR)
    if (path / wsmod.CONFIG_NAME).exists():
        raise CheckFailed("Refused: a workspace already exists at %s (indelible.json found). "
                          "Nothing was changed." % path)
    if path.exists() and not path.is_dir():
        raise UsageError("%s exists and is not a folder" % path)
    tz = args.timezone or detect_iana_tz()
    if args.timezone and not schema.TZ_RE.match(args.timezone):
        raise UsageError("--timezone must be an IANA name such as Europe/Lisbon (got %r)" % args.timezone)

    fio.ensure_dir(path)
    ws = wsmod.Workspace(path)
    kept_claude = False
    with ws.lock():
        ws.ensure_tree()
        cfg = wsmod.default_config()
        cfg["timezone"] = tz
        fio.write_json(ws.config_path, cfg, backup=False)
        if ws.claude_md.exists():
            kept_claude = True
        else:
            fio.write_text(ws.claude_md, root_claude_text(), backup=False)
        gi = ws.root / ".gitignore"
        if not gi.exists():
            fio.write_text(gi, wsmod.asset_text("gitignore"), backup=False)
        fio.touch(ws.ledger_path)
        fio.touch(ws.blocks_path)

    if args.pointer:
        pf = wsmod.pointer_file()
        fio.write_text(pf, str(ws.root) + "\n", backup=False)

    _out("Workspace created: %s" % ws.root)
    _out("  indelible.json, CLAUDE.md, ledger.jsonl, plan/, views/, reviews/, inbox/, .indelible/")
    if kept_claude:
        _out("  Kept your existing CLAUDE.md unchanged. Add this line to it: "
             "\"This folder is an indelible study workspace: use the indelible skill and run its brief first.\"")
    if tz:
        _out("  Time zone: %s" % tz)
    else:
        _out("  Time zone: not detected; set it with: indelible.py set root timezone '\"Area/City\"'")
    if args.pointer:
        _out("  Pointer saved: %s" % wsmod.pointer_file())
    marker = cloud_marker(ws.root)
    if marker:
        _out("WARN the workspace is inside a cloud-synced folder (%s)." % marker)
    _out("Next: indelible.py subject add <id> --title \"<title>\" --profile <%s>" % "|".join(schema.PROFILES))
    return 0


# ==========================================================================
# subject add / list
# ==========================================================================

def _normalise_topics(topics):
    out = []
    for t in topics or []:
        if not isinstance(t, dict):
            out.append(t)
            continue
        t = dict(t)
        t.setdefault("weight", None)
        t.setdefault("floor", [])
        t.setdefault("confusable_with", [])
        t.setdefault("scope", "in")
        out.append(t)
    return out


def _subject_claude_md(data, today=None):
    tgt = data.get("target") or {}
    fmt = data.get("format") or {}
    parts = []
    if fmt.get("minutes"):
        parts.append("%s min" % fmt["minutes"])
    if fmt.get("answer_form"):
        parts.append("answers: %s" % fmt["answer_form"])
    if fmt.get("tools"):
        parts.append("tools: %s" % fmt["tools"])
    if fmt.get("time_of_day"):
        parts.append("at %s" % fmt["time_of_day"])
    date_s = tgt.get("date") or "no date"
    success = tgt.get("success") or "(not set)"
    if tgt.get("floor"):
        success += "; floor %s" % tgt["floor"]
    values = {
        "title": data.get("title") or data.get("id"),
        "id": data.get("id"),
        "goal": tgt.get("goal") or "(not set)",
        "date": date_s,
        "format": " · ".join(parts) if parts else "(not set)",
        "success": success,
        "scope": "(not set)",
        "today": dates.fmt_date(today or dates.today()),
    }
    return string.Template(wsmod.asset_text("subject-CLAUDE.md")).safe_substitute(values)


def cmd_subject_add(args):
    ws = wsmod.from_args(args)
    sid = args.id
    if not wsmod.SUBJECT_ID_RE.match(sid or ""):
        raise UsageError("Subject id %r must be lowercase letters, digits and hyphens, starting with a letter "
                         "(at most 32 characters), e.g. ielts or stats-final" % sid)
    if sid in wsmod.RESERVED_SUBJECT_IDS:
        raise UsageError("Subject id %r is reserved; pick another" % sid)
    if ws.subject_entry(sid) is not None:
        raise CheckFailed("Refused: subject '%s' already exists. Change it with: indelible.py set %s <path> <value>"
                          % (sid, sid))
    subj = wsmod.Subject(ws, sid, sid)
    if subj.json_path.exists():
        raise CheckFailed("Refused: %s already exists. Nothing was changed." % ws.rel(subj.json_path))

    data = wsmod.default_subject()
    if args.from_path:
        src_path = Path(args.from_path).expanduser()
        if not src_path.is_file():
            raise UsageError("--from file not found: %s" % src_path)
        src = fio.read_json(src_path)
        if not isinstance(src, dict):
            raise UsageError("--from must hold a JSON object like subject.json")
        data = deep_merge(data, src)
    data["v"] = 1
    data["id"] = sid
    if args.title:
        data["title"] = args.title
    if args.profile:
        data["profile"] = args.profile
    if not (data.get("title") or "").strip():
        raise UsageError("--title is required (or a title in the --from file)")
    if data.get("profile") not in schema.PROFILES:
        raise UsageError("--profile must be one of: %s" % ", ".join(schema.PROFILES))
    data["topics"] = _normalise_topics(data.get("topics"))
    problems = schema.validate_subject(data)
    if problems:
        raise CheckFailed("Refused: subject.json would be invalid:\n" + "\n".join("  - " + p for p in problems))

    with ws.lock():
        cfg = ws.load_config(reload=True)
        if any(isinstance(s, dict) and s.get("id") == sid for s in cfg.get("subjects") or []):
            raise CheckFailed("Refused: subject '%s' already exists." % sid)
        subj.ensure_tree()
        for p in (subj.sessions_path, subj.attempts_path, subj.exposures_path, subj.errors_path,
                  subj.sheets_path, subj.glossary_path, subj.scans_index_path):
            fio.touch(p)
        if not subj.topics_path.exists():
            subj.save_topics_state({})
        subj.save(data)
        if not subj.claude_md.exists():
            fio.write_text(subj.claude_md, _subject_claude_md(data, ws.today()), backup=False)
        entries = cfg.setdefault("subjects", [])
        prios = [s.get("priority") for s in entries if isinstance(s, dict) and isinstance(s.get("priority"), int)]
        live_before = [s for s in entries if isinstance(s, dict) and s.get("state", "live") == "live"]
        weekly = (cfg.get("time") or {}).get("weekly_target_min")
        entries.append({
            "id": sid, "dir": sid, "state": args.state,
            "priority": (max(prios) + 1) if prios else 1,
            "target_weekly_min": weekly if (not live_before and args.state == "live") else None,
            "min_weekly_min": None,
        })
        ws.save_config(cfg)

    note = _render_after_change(args, ws)
    tgt = data.get("target") or {}
    _out("Subject added: %s · %s · %s · %s" % (sid, data["title"], data["profile"], tgt.get("date") or "no date"))
    _out("  Folder: %s/ · topics: %d · state: %s" % (sid, len(data["topics"]), args.state))
    if note:
        _out("  " + note)
    if not data["topics"]:
        _out("Next: indelible.py topic add %s T01 --name \"<topic>\" --layer <%s>" % (sid, "|".join(schema.LAYERS)))
    return 0


def cmd_subject_list(args):
    ws = wsmod.from_args(args)
    rows = []
    for e in ws.subject_entries():
        sid = e["id"]
        title, profile, date_s = sid, "?", None
        try:
            cfg = wsmod.Subject(ws, sid, e.get("dir") or sid).load()
            title, profile = cfg.get("title") or sid, cfg.get("profile") or "?"
            date_s = (cfg.get("target") or {}).get("date")
        except IndelibleError:
            pass
        rows.append({"id": sid, "state": e.get("state", "live"), "title": title, "profile": profile,
                     "date": date_s, "priority": e.get("priority")})
    if getattr(args, "json", False):
        _out(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        _out("No subjects yet. Run: indelible.py subject add <id> --title \"<title>\" --profile <profile>")
        return 0
    for r in rows:
        _out("%s  %s  %s (%s)  %s" % (r["id"], r["state"], r["title"], r["profile"], r["date"] or "no date"))
    return 0


# ==========================================================================
# set
# ==========================================================================

_MISSING = object()


def _list_index(lst, part, path):
    if part in ("+", "-"):
        return part
    if part.lstrip("-").isdigit():
        i = int(part)
        if -len(lst) <= i < len(lst):
            return i % len(lst) if lst else i
        raise UsageError("%s: index %s is out of range (the list has %d entries)" % (path, part, len(lst)))
    for i, item in enumerate(lst):
        if isinstance(item, dict) and item.get("id") == part:
            return i
    raise UsageError("%s: no entry with id %r" % (path, part))


def _fmt(value):
    if value is _MISSING:
        return "(unset)"
    return json.dumps(value, ensure_ascii=False)


def _apply(data, parts, value, spec_root, force):
    """Set ``value`` at ``parts`` inside ``data`` (in place). Returns the old value."""
    node = data
    walked = []
    for part in parts[:-1]:
        walked.append(part)
        here = ".".join(walked)
        if isinstance(node, dict):
            if part not in node or node[part] is None:
                sub = schema.spec_at(spec_root, walked)
                if sub is None and not force:
                    raise CheckFailed("Refused: unknown path '%s'." % here)
                if sub is not None and sub["t"] == "list":
                    node[part] = []
                else:
                    node[part] = {}
            node = node[part]
        elif isinstance(node, list):
            idx = _list_index(node, part, here)
            if idx in ("+", "-"):
                raise UsageError("%s: '+' can only be the last part of the path" % here)
            node = node[idx]
        else:
            raise UsageError("%s is a %s, not an object or list" % (here, type(node).__name__))
    last = parts[-1]
    if isinstance(node, dict):
        old = node.get(last, _MISSING)
        node[last] = value
        return old
    if isinstance(node, list):
        idx = _list_index(node, last, ".".join(parts))
        if idx == "+":
            node.append(value)
            return _MISSING
        if idx == "-":
            raise UsageError("use an index or an id to replace a list entry")
        old = node[idx]
        node[idx] = value
        return old
    raise UsageError("%s is not an object or a list" % ".".join(parts[:-1]))


def _get(data, parts):
    node = data
    for part in parts:
        if isinstance(node, dict):
            if part not in node:
                return _MISSING
            node = node[part]
        elif isinstance(node, list):
            try:
                idx = _list_index(node, part, ".".join(parts))
            except UsageError:
                return _MISSING
            if idx in ("+", "-"):
                return _MISSING
            node = node[idx]
        else:
            return _MISSING
    return node


def cmd_set(args):
    ws = wsmod.from_args(args)
    if args.target == "root":
        label, spec_root, validator = "indelible.json", schema.INDELIBLE_SPEC, schema.validate_config
        subj = None
    else:
        subj = ws.subject(args.target)
        label, spec_root, validator = "%s/subject.json" % subj.dirname, schema.SUBJECT_SPEC, schema.validate_subject
    parts = [p for p in args.path.strip().split(".") if p != ""]
    if not parts:
        raise UsageError("give a dotted path, e.g. session.length_min")

    spec = schema.spec_at(spec_root, parts)
    if spec is None and not args.force:
        raise CheckFailed("Refused: unknown path '%s' in %s. Check the name with: indelible.py schema %s "
                          "(or pass --force)." % (args.path, label, "indelible" if subj is None else "subject"))
    if spec is not None and spec.get("ro") and not args.force:
        raise CheckFailed("Refused: %s in %s is fixed once created." % (args.path, label))
    try:
        value = schema.normalise_value(spec, schema.coerce_cli_value(spec, args.value))
    except ValueError as exc:
        raise UsageError(str(exc))
    if spec is not None:
        probs = schema.check_value(spec, value, args.path)
        if probs:
            raise CheckFailed("Refused: " + "; ".join(probs))
    if subj is not None and parts[-1:] == ["topics"] and isinstance(value, list):
        value = _normalise_topics(value)

    ctx = ws.lock() if not args.dry_run else contextlib.nullcontext()
    with ctx:
        data = copy.deepcopy(ws.load_config(reload=True) if subj is None else subj.load(reload=True))
        problems_before = set(validator(data))
        new = copy.deepcopy(data)
        old = _apply(new, parts, value, spec_root, args.force)
        also = []
        if subj is None:
            also = _derive_root(data, new, args.path)
        problems_after = [p for p in validator(new) if p not in problems_before]
        if problems_after and not args.force:
            raise CheckFailed("Refused: " + "; ".join(problems_after))
        _out("%s %s: %s -> %s" % (label, args.path, _fmt(old), _fmt(value)))
        for path, a, b in also:
            _out("%s %s: %s -> %s (derived)" % (label, path, _fmt(a), _fmt(b)))
        if args.dry_run:
            _out("(dry run: nothing written)")
            return 0
        if subj is None:
            ws.save_config(new)
        else:
            subj.save(new)

    if subj is None and parts[0] == "subjects":
        note = _render_after_change(args, ws)
        if note:
            _out(note)
    return 0


def _derive_root(old, new, path):
    """Keep derived weekly numbers in step when the learner changes an input."""
    changes = []
    ot, nt = old.get("time") or {}, new.setdefault("time", {})
    os_, ns = old.get("session") or {}, new.get("session") or {}
    if path in ("session.length_min", "session.days_per_week"):
        try:
            old_derived = int(os_["length_min"]) * int(os_["days_per_week"])
            new_derived = int(ns["length_min"]) * int(ns["days_per_week"])
        except (KeyError, TypeError, ValueError):
            old_derived = new_derived = None
        if old_derived is not None and ot.get("weekly_target_min") == old_derived and new_derived != old_derived:
            nt["weekly_target_min"] = new_derived
            changes.append(("time.weekly_target_min", old_derived, new_derived))
    if nt.get("weekly_target_min") != ot.get("weekly_target_min") and isinstance(nt.get("weekly_target_min"), int):
        oc = ot.get("weekly_ceiling_min")
        if isinstance(ot.get("weekly_target_min"), int) and oc == default_ceiling(ot["weekly_target_min"]) \
                and path != "time.weekly_ceiling_min":
            nc = default_ceiling(nt["weekly_target_min"])
            if nc != oc:
                nt["weekly_ceiling_min"] = nc
                changes.append(("time.weekly_ceiling_min", oc, nc))
    return changes


# ==========================================================================
# schema
# ==========================================================================

ALIASES = {
    "config": "indelible", "root": "indelible", "subjects": "subject", "topic": "topics",
    "sheets": "sheet", "attempts": "attempt", "errors": "error", "sessions": "session",
    "exposures": "exposure", "blocks": "block", "obligation": "block", "spec": "sheetspec",
    "key": "answers", "grade": "grades", "session.lock": "lock", "session-lock": "lock",
}


def cmd_schema(args):
    if not args.record:
        _out("Records: " + " | ".join(schema.RECORD_NAMES))
        _out("Run: indelible.py schema <record>")
        return 0
    name = ALIASES.get(args.record, args.record)
    if name not in schema.RECORDS:
        raise UsageError("Unknown record %r. One of: %s" % (args.record, ", ".join(schema.RECORD_NAMES)))
    if args.json:
        _out(json.dumps(schema.example(name), ensure_ascii=False, indent=2))
    else:
        _out(schema.describe(name))
    return 0
