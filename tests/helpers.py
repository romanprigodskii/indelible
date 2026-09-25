"""Shared test helpers.

    SKILL_DIR   the skill folder (skills/indelible)
    CLI         path to scripts/indelible.py
    make_ws(tmpdir, persona='A', subject=True) -> Path
    run(args, ws=None, now='2026-10-12T09:00+01:00', stdin=None, env=None) -> CompletedProcess

``run`` starts the CLI with ``sys.executable`` in a neutral working folder,
with HOME (and USERPROFILE) pointed at a private sandbox so that no test reads
or writes the real ``~/.indelible``. Pass absolute paths in ``args``.

Personas are the synthetic learners A-D:
    A  ielts    exam      IELTS Academic 7.0 by 2026-12-12, Lisbon, 60 min x 4 days
    B  spanish  language  Spanish for a trip in 5 months, 20-minute daily sessions
    C  stats    course    University statistics final in 3 weeks, 120 min daily
    D  rust     code      Rust as a hobby, no date, on-demand ("whenever")
"""

import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_DIR = TESTS_DIR.parent
SKILL_DIR = REPO_DIR / "skills" / "indelible"
CLI = SKILL_DIR / "scripts" / "indelible.py"
DEFAULT_NOW = "2026-10-12T09:00+01:00"

if str(CLI.parent) not in sys.path:
    sys.path.insert(0, str(CLI.parent))

# Tests never launch a real browser: with HOME pointed at a sandbox, Chrome on
# macOS cannot find the login keychain and shows a "Keychain Not Found" dialog on
# every run. Opt in with INDELIBLE_TEST_BROWSER=1 (inherited by CLI subprocesses).
if not os.environ.get("INDELIBLE_TEST_BROWSER"):
    os.environ["INDELIBLE_NO_BROWSER"] = "1"

_SANDBOX = []


def sandbox_dir():
    """A private folder used as HOME and as the working folder for CLI runs."""
    if not _SANDBOX:
        d = Path(tempfile.mkdtemp(prefix="indelible-test-home-"))
        _SANDBOX.append(d)
        atexit.register(shutil.rmtree, str(d), True)
    return _SANDBOX[0]


def run(args, ws=None, now=DEFAULT_NOW, stdin=None, env=None):
    """Run the CLI. ``env`` entries are added to (or, with value None, removed from) the environment."""
    cmd = [sys.executable, str(CLI)]
    if ws is not None:
        cmd += ["--workspace", str(ws)]
    cmd += [str(a) for a in args]
    home = sandbox_dir()
    e = dict(os.environ)
    e.pop("INDELIBLE_WORKSPACE", None)
    e.update({
        "INDELIBLE_NOW": now,
        "HOME": str(home),
        "USERPROFILE": str(home),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    for k, v in (env or {}).items():
        if v is None:
            e.pop(k, None)
        else:
            e[k] = str(v)
    return subprocess.run(
        cmd, input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=e, cwd=str(home), timeout=180,
    )


PERSONAS = {
    "A": {
        "subject": "ielts", "title": "IELTS Academic", "profile": "exam",
        "timezone": "Europe/Lisbon",
        "root": {
            "learner.l1": "pt",
            "calendar.provider": "google",
            "time.rest_day": "Sun",
            "time.windows": [{"days": ["Mon", "Tue", "Thu"], "from": "07:00", "to": "08:15"},
                             {"days": ["Sat"], "from": "10:00", "to": "12:00"}],
        },
        "data": {
            "target": {"goal": "IELTS Academic 7.0", "why": "master's offer",
                       "success": "7.0 overall, no band under 6.5", "date": "2026-12-12", "floor": "6.5"},
            "format": {"minutes": 165, "answer_form": "short", "tools": "none", "time_of_day": "09:00"},
            "topics": [
                {"id": "T01", "name": "Matching headings", "layer": "reading"},
                {"id": "T02", "name": "True, false or not given", "layer": "reading"},
                {"id": "T03", "name": "Task 1 overview", "layer": "production"},
                {"id": "T04", "name": "Paraphrase", "layer": "verbal", "confusable_with": ["T01"]},
            ],
        },
    },
    "B": {
        "subject": "spanish", "title": "Spanish for a trip", "profile": "language",
        "timezone": "Europe/Madrid",
        "root": {
            "learner.l1": "en",
            "session.length_min": 20, "session.max_min": 30, "session.days_per_week": 7,
            "time.weekly_target_min": 140, "time.weekly_ceiling_min": 196,
        },
        "data": {
            "target": {"goal": "Order a meal, ask directions, 3 minutes of small talk",
                       "why": "a trip in five months", "success": "3 minutes of small talk without switching language",
                       "date": "2027-03-12"},
            "format": {"answer_form": "typed", "tools": "none"},
            "topics": [
                {"id": "T01", "name": "Present tense of regular verbs", "layer": "procedural"},
                {"id": "T02", "name": "Ordering in a restaurant", "layer": "production"},
                {"id": "T03", "name": "Asking for directions", "layer": "verbal"},
            ],
        },
    },
    "C": {
        "subject": "stats", "title": "Statistics final", "profile": "course",
        "timezone": "America/New_York",
        "root": {
            "calendar.provider": "ics",
            "session.length_min": 120, "session.max_min": 150, "session.days_per_week": 7,
            "time.weekly_target_min": 840, "time.weekly_ceiling_min": 1176,
        },
        "data": {
            "target": {"goal": "Pass the statistics final", "why": "course requirement",
                       "success": "70% or more on the final", "date": "2026-11-02"},
            "format": {"minutes": 120, "answer_form": "short", "tools": "calculator", "reference_sheet": True},
            "topics": [
                {"id": "T01", "name": "Hypothesis tests", "layer": "conceptual"},
                {"id": "T02", "name": "Confidence intervals", "layer": "procedural", "confusable_with": ["T01"]},
                {"id": "T03", "name": "Linear regression", "layer": "procedural"},
            ],
        },
    },
    "D": {
        "subject": "rust", "title": "Rust", "profile": "code",
        "timezone": "Europe/Berlin",
        "root": {
            "time.schedule": "on_demand",
            "calendar.provider": "none",
        },
        "data": {
            "target": {"goal": "A CLI tool that parses a CSV, with tests", "why": "hobby",
                       "success": "the tool runs on a real file and its tests pass", "date": None},
            "format": {"answer_form": "code", "tools": "compiler"},
            "topics": [
                {"id": "T01", "name": "Ownership and borrowing", "layer": "code"},
                {"id": "T02", "name": "Error handling with Result", "layer": "code"},
            ],
        },
    },
}


def _set_dotted(data, dotted, value):
    node = data
    parts = dotted.split(".")
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = value


def make_ws(tmpdir, persona="A", subject=True):
    """Create a workspace for a synthetic persona (A-D) and return its root Path.

    Runs ``init`` and, when ``subject`` is true, ``subject add`` through the CLI;
    persona settings in indelible.json are written directly with lib.io.
    """
    persona = persona.upper()
    p = PERSONAS[persona]
    tmpdir = Path(os.path.abspath(str(tmpdir)))
    ws = tmpdir / ("ws-" + persona.lower())
    r = run(["init", ws, "--timezone", p["timezone"]])
    if r.returncode != 0:
        raise AssertionError("init failed (%s): %s %s" % (r.returncode, r.stdout, r.stderr))

    from lib import io as fio
    cfg_path = ws / "indelible.json"
    cfg = fio.read_json(cfg_path)
    for dotted, value in p["root"].items():
        _set_dotted(cfg, dotted, value)
    fio.write_json(cfg_path, cfg)

    if subject:
        src = tmpdir / ("persona-%s-subject.json" % persona.lower())
        src.write_text(json.dumps(p["data"], ensure_ascii=False), encoding="utf-8")
        r = run(["subject", "add", p["subject"], "--title", p["title"], "--profile", p["profile"],
                 "--from", src], ws=ws)
        if r.returncode != 0:
            raise AssertionError("subject add failed (%s): %s %s" % (r.returncode, r.stdout, r.stderr))
    return ws
