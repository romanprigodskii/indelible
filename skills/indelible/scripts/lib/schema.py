"""Record formats: examples, field notes, enums and light validators.

``indelible.py schema <record>`` prints ``describe(record)``. Claude runs it
instead of guessing a field name. Examples use the synthetic learner A
(IELTS Academic, first language Portuguese, Lisbon).

Validators return a list of problem strings (empty when fine); they check
shape and enums, not meaning. ``set`` uses the typed path specs
(``INDELIBLE_SPEC``, ``SUBJECT_SPEC``) to refuse unknown paths and bad values.
"""

import json
import re

from lib import dates

# ==========================================================================
# Enums
# ==========================================================================

SCHEDULES = ["scheduled", "on_demand"]
TONES = ["A", "B"]
VOCABS = ["plain", "technical"]
CHAT_MATH = ["unicode", "ascii"]
GLOSS = ["first_use", "always", "off"]
AGE_BANDS = ["under16", "16-17", "18+"]
MISSED_POLICIES = ["ask", "auto_move", "drop"]
CALENDAR_WRITE = ["preview_confirm", "auto_move_24h", "none"]
OVERRUN = ["ask", "stop", "extend"]
SUBJECT_STATES = ["live", "shadow", "legacy", "paused"]
CAL_PROVIDERS = ["none", "ics", "ticktick", "google", "other"]
PROFILES = ["exam", "course", "interview", "language", "code", "skill"]
INTENSITIES = ["standard", "light"]
LAYERS = ["procedural", "conceptual", "verbal", "reading", "production", "code"]
TOPIC_SCOPES = ["in", "out"]
TAUGHT_BY = ["sheet", "external", "chat", "tutor"]
SHEET_TYPES = [
    "theory", "external", "example", "drills", "cold", "mixed", "repair", "review", "probe",
    "diagnostic", "mock", "checkpoint", "words", "triage", "miss-review", "explain",
]
MEASURING_TYPES = ["cold", "diagnostic", "mock", "checkpoint", "probe", "words"]
SHEET_STATUSES = ["built", "linted", "rendered", "issued", "sat", "graded", "void"]
VERDICTS = ["right", "half", "wrong", "dont_know", "skip"]
CHECKS = ["filled", "missing", "caught", "n/a"]
INSTRUMENTS = ["practice", "cold", "diagnostic", "mock", "checkpoint", "probe", "words"]
PROVENANCE = ["practice", "measured"]
ERROR_KINDS = ["belief", "slip", "shaky"]
ERROR_STATUSES = ["untreated", "spacing", "retired", "reopened"]
CLOSED_STATUSES = ["same-day", "late", "with-todos"]
EXPOSURE_KINDS = ["teach", "repair", "chat", "drill", "review"]
BLOCK_KINDS = [
    "teach", "cold", "repair", "review", "mixed", "mock", "diagnostic", "checkpoint", "words",
    "oral", "project", "long", "tutor_lesson", "buffer", "admin",
]
BLOCK_STATUSES = ["planned", "synced", "done", "missed?", "missed", "moved", "cancelled"]
LEDGER_KINDS = ["owed", "decision", "defect", "override", "hypothesis", "status"]
LEDGER_CLOSE_STATUSES = ["done", "dropped", "scored"]
DEFECT_CATEGORIES = [
    "sizing", "floor", "undefined_term", "late_build", "content_error", "promise_broken",
    "contamination", "late_close", "scheduling", "misclassification", "wrong_inference",
]
FIX_TYPES = ["rule", "template", "lint", "script", "planner"]
CHECKPOINT_STATUSES = ["armed", "passed", "failed"]
THEORY_SECTION_KINDS = ["worked", "rule", "contrast", "both_hold", "warning", "where", "text"]
PRACTICE_TYPES = ["drills", "mixed", "repair", "review", "example"]

SHEET_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")
TOPIC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
ORIGIN_RE = re.compile(r"^(new|cold:[A-Za-z0-9_-]+|(error|sentinel):E-[a-z0-9-]+-\d+|official:.+)$")
ERROR_ID_RE = re.compile(r"^E-[a-z0-9-]+-\d{4,}$")
SESSION_ID_RE = re.compile(r"^S-[a-z0-9-]+-\d{4,}$")
BLOCK_ID_RE = re.compile(r"^B-\d{8}-[a-z0-9-]+-\d+$")
LEDGER_ID_RE = re.compile(r"^L-\d{4,}$")
TZ_RE = re.compile(r"^(UTC|[A-Za-z_]+(/[A-Za-z0-9_+-]+)+)$")


def is_sheet_id(value):
    return isinstance(value, str) and bool(SHEET_ID_RE.match(value))


def instrument_for_type(sheet_type):
    """The attempt instrument for a sheet type (non-measuring types are practice)."""
    return sheet_type if sheet_type in MEASURING_TYPES else "practice"


def measures(sheet_type):
    return sheet_type in MEASURING_TYPES


# ==========================================================================
# Typed path specs (used by ``set`` and the config validators)
# ==========================================================================

def INT(lo=None, hi=None, null=False, ro=False):
    return {"t": "int", "min": lo, "max": hi, "null": null, "ro": ro}


def NUM(lo=None, hi=None, null=False):
    return {"t": "num", "min": lo, "max": hi, "null": null}


def STR(null=False, max_len=None, pattern=None, ro=False, min_len=0):
    return {"t": "str", "null": null, "max": max_len, "pattern": pattern, "ro": ro, "min_len": min_len}


def ENUM(values, null=False):
    return {"t": "enum", "values": list(values), "null": null}


def BOOL():
    return {"t": "bool"}


def DATE(null=False):
    return {"t": "date", "null": null}


def DATETIME(null=False):
    return {"t": "datetime", "null": null}


def HHMM(null=False):
    return {"t": "hhmm", "null": null}


def DAY(null=False):
    return {"t": "day", "null": null}


def TZ(null=False):
    return {"t": "tz", "null": null}


def LIST(item, min_len=None, max_len=None):
    return {"t": "list", "item": item, "min_len": min_len, "max_len": max_len}


def OBJ(fields, null=False, open_=False, required=None):
    return {"t": "obj", "fields": fields, "null": null, "open": open_, "required": list(required or [])}


def MAP(value, keys=None):
    return {"t": "map", "value": value, "keys": list(keys) if keys else None}


def ANY():
    return {"t": "any"}


WINDOW_SPEC = OBJ({
    "days": LIST(DAY(), min_len=1), "from": HHMM(), "to": HHMM(), "quality": STR(null=True),
}, open_=True, required=["days", "from", "to"])

BLOCKED_SPEC = OBJ({
    "days": LIST(DAY()), "date": DATE(), "from": HHMM(null=True), "to": HHMM(null=True),
    "what": STR(null=True, max_len=120),
}, open_=True)

SUBJECT_ENTRY_SPEC = OBJ({
    "id": STR(ro=True), "dir": STR(ro=True), "state": ENUM(SUBJECT_STATES), "priority": INT(1, 99),
    "target_weekly_min": INT(0, 10080, null=True), "min_weekly_min": INT(0, 10080, null=True),
}, open_=True, required=["id", "state"])

INDELIBLE_SPEC = OBJ({
    "v": INT(1, 1, ro=True),
    "timezone": TZ(null=True),
    "learner": OBJ({
        "age_band": ENUM(AGE_BANDS), "l1": STR(null=True, max_len=16),
        "instruction_lang": STR(null=True, max_len=16), "gloss": ENUM(GLOSS), "tone": ENUM(TONES),
        "vocab": ENUM(VOCABS), "chat_math": ENUM(CHAT_MATH),
    }, open_=True),
    "time": OBJ({
        "schedule": ENUM(SCHEDULES), "weekly_target_min": INT(0, 10080),
        "weekly_ceiling_min": INT(0, 10080),
        "sleep": OBJ({"bed": HHMM(), "wake": HHMM()}),
        "rest_day": DAY(null=True), "buffer_pct": INT(0, 50),
        "windows": LIST(WINDOW_SPEC), "blocked": LIST(BLOCKED_SPEC),
    }, open_=True),
    "session": OBJ({
        "length_min": INT(5, 600), "max_min": INT(5, 720), "days_per_week": INT(1, 7),
        "overrun": ENUM(OVERRUN), "extension_max_min": INT(0, 60), "break_every_min": INT(30, 180),
        "break_min": INT(0, 60),
    }, open_=True),
    "policies": OBJ({"missed": ENUM(MISSED_POLICIES), "calendar_write": ENUM(CALENDAR_WRITE)}, open_=True),
    "render": OBJ({"backend": STR(null=True), "verified_at": DATETIME(null=True)}, open_=True),
    "calendar": OBJ({
        "provider": ENUM(CAL_PROVIDERS), "signature": STR(null=True), "reminder_min": INT(0, 1440),
        "target": STR(null=True),
    }, open_=True),
    "subjects": LIST(SUBJECT_ENTRY_SPEC),
    "drop_order": LIST(STR()),
}, required=["v", "time", "session", "subjects"])

TOPIC_SPEC = OBJ({
    "id": STR(pattern=TOPIC_ID_RE.pattern), "name": STR(max_len=120, min_len=1),
    "weight": NUM(0, None, null=True), "layer": ENUM(LAYERS), "floor": LIST(STR()),
    "confusable_with": LIST(STR()), "scope": ENUM(TOPIC_SCOPES),
}, open_=True, required=["id", "name", "layer"])

CHECKPOINT_SPEC = OBJ({
    "date": DATE(), "instrument": STR(), "threshold": ANY(), "if_below": STR(null=True),
    "status": ENUM(CHECKPOINT_STATUSES), "result": ANY(),
}, open_=True, required=["date", "instrument", "status"])

OVERRIDE_SPEC = OBJ({
    "rule": STR(min_len=1, max_len=16), "value": ANY(), "why": STR(max_len=300), "date": DATE(),
    "locked": BOOL(),
}, open_=True, required=["rule", "value", "why", "date"])

SUBJECT_SPEC = OBJ({
    "v": INT(1, 1, ro=True),
    "id": STR(ro=True),
    "title": STR(max_len=120, min_len=1),
    "profile": ENUM(PROFILES),
    "intensity": ENUM(INTENSITIES),
    "target": OBJ({
        "goal": STR(null=True, max_len=300), "why": STR(null=True, max_len=300),
        "success": STR(null=True, max_len=300), "date": DATE(null=True), "floor": STR(null=True, max_len=120),
    }, open_=True),
    "format": OBJ({
        "minutes": INT(1, 1000, null=True), "answer_form": STR(null=True, max_len=60),
        "tools": STR(null=True, max_len=120), "reference_sheet": BOOL(), "time_of_day": HHMM(null=True),
        "accommodations": ANY(), "ai_policy": STR(null=True, max_len=200),
    }, open_=True),
    "topics": LIST(TOPIC_SPEC),
    "taxonomy": LIST(OBJ({"code": STR(min_len=1, max_len=8), "name": STR(), "treatment": STR(null=True)},
                         open_=True, required=["code", "name"])),
    "cold_window_h": LIST(NUM(1, 168), min_len=2, max_len=2),
    "block_size": OBJ({"min": INT(1, 20), "max": INT(1, 20), "default": INT(1, 20)}),
    "pace_s": MAP(INT(5, 3600), keys=LAYERS),
    "sense_list": LIST(STR()),
    "lexicon": LIST(ANY()),
    "checkpoints": LIST(CHECKPOINT_SPEC),
    "materials": OBJ({"sources": LIST(ANY()), "ration": LIST(ANY())}, open_=True),
    "overrides": LIST(OVERRIDE_SPEC),
}, required=["v", "id", "title", "profile"])


def _type_name(spec):
    t = spec["t"]
    if t == "int":
        lo, hi = spec.get("min"), spec.get("max")
        if lo is not None and hi is not None:
            return "an integer from %s to %s" % (lo, hi)
        if lo is not None:
            return "an integer >= %s" % lo
        return "an integer"
    if t == "num":
        return "a number"
    if t == "str":
        return "a string"
    if t == "enum":
        return "one of: " + ", ".join(spec["values"])
    if t == "bool":
        return "true or false"
    if t == "date":
        return "a date YYYY-MM-DD"
    if t == "datetime":
        return "a time YYYY-MM-DDTHH:MM+HH:MM"
    if t == "hhmm":
        return "a time HH:MM"
    if t == "day":
        return "a weekday (Mon..Sun)"
    if t == "tz":
        return "an IANA time zone such as Europe/Lisbon"
    if t == "list":
        return "a list"
    if t in ("obj", "map"):
        return "an object"
    return "any JSON value"


def type_name(spec):
    name = _type_name(spec)
    if spec.get("null"):
        name += " (or null)"
    return name


def check_value(spec, value, path="value"):
    """Problems with ``value`` against ``spec`` (empty list when fine)."""
    t = spec["t"]
    if value is None:
        if spec.get("null") or t == "any":
            return []
        return ["%s must be %s, not null" % (path, type_name(spec))]
    bad = ["%s must be %s (got %s)" % (path, type_name(spec), json.dumps(value, ensure_ascii=False)[:80])]
    if t == "any":
        return []
    if t == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            return bad
        if spec.get("min") is not None and value < spec["min"]:
            return bad
        if spec.get("max") is not None and value > spec["max"]:
            return bad
        return []
    if t == "num":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return bad
        if spec.get("min") is not None and value < spec["min"]:
            return bad
        if spec.get("max") is not None and value > spec["max"]:
            return bad
        return []
    if t == "str":
        if not isinstance(value, str):
            return bad
        if spec.get("max") and len(value) > spec["max"]:
            return ["%s is longer than %d characters" % (path, spec["max"])]
        if spec.get("min_len") and len(value.strip()) < spec["min_len"]:
            return ["%s must not be empty" % path]
        if spec.get("pattern") and not re.match(spec["pattern"], value):
            return ["%s has an unexpected format: %r" % (path, value)]
        return []
    if t == "enum":
        return [] if value in spec["values"] else bad
    if t == "bool":
        return [] if isinstance(value, bool) else bad
    if t == "date":
        return [] if dates.is_date(value) else bad
    if t == "datetime":
        return [] if dates.is_iso(value) else bad
    if t == "hhmm":
        return [] if isinstance(value, str) and dates.is_hhmm(value) else bad
    if t == "day":
        return [] if isinstance(value, str) and value in dates.WEEKDAYS else bad
    if t == "tz":
        return [] if isinstance(value, str) and TZ_RE.match(value) else bad
    if t == "list":
        if not isinstance(value, list):
            return bad
        if spec.get("min_len") is not None and len(value) < spec["min_len"]:
            return ["%s needs at least %d entries" % (path, spec["min_len"])]
        if spec.get("max_len") is not None and len(value) > spec["max_len"]:
            return ["%s allows at most %d entries" % (path, spec["max_len"])]
        out = []
        for i, item in enumerate(value):
            out.extend(check_value(spec["item"], item, "%s[%d]" % (path, i)))
        return out
    if t == "map":
        if not isinstance(value, dict):
            return bad
        out = []
        for k, v in value.items():
            if spec.get("keys") and k not in spec["keys"]:
                out.append("%s: unknown key %r (known: %s)" % (path, k, ", ".join(spec["keys"])))
                continue
            out.extend(check_value(spec["value"], v, "%s.%s" % (path, k)))
        return out
    if t == "obj":
        if not isinstance(value, dict):
            return bad
        out = []
        for k in spec.get("required") or []:
            if k not in value:
                out.append("%s is missing %r" % (path, k))
        for k, v in value.items():
            sub = spec["fields"].get(k)
            if sub is None:
                if not spec.get("open"):
                    out.append("%s: unknown field %r" % (path, k))
                continue
            out.extend(check_value(sub, v, "%s.%s" % (path, k)))
        return out
    return []


def spec_at(root, parts):
    """The spec for a dotted path (list parts: an index, an id, ``+`` or ``*``)."""
    spec = root
    for part in parts:
        t = spec["t"]
        if t == "obj":
            spec = spec["fields"].get(part)
        elif t == "map":
            if spec.get("keys") and part not in spec["keys"]:
                return None
            spec = spec["value"]
        elif t == "list":
            spec = spec["item"]
        elif t == "any":
            return spec
        else:
            return None
        if spec is None:
            return None
    return spec


def normalise_value(spec, value):
    """Canonical forms before checking: weekdays as Mon..Sun, times as HH:MM."""
    if spec is None or value is None:
        return value
    t = spec["t"]
    if t == "day" and isinstance(value, str) and dates.is_weekday_name(value):
        return dates.WEEKDAYS[dates.weekday_index(value)]
    if t == "hhmm" and isinstance(value, str) and dates.is_hhmm(value):
        return dates.parse_hhmm(value).strftime("%H:%M") if value.strip() != "24:00" else "24:00"
    if t == "list" and isinstance(value, list):
        return [normalise_value(spec["item"], v) for v in value]
    if t == "obj" and isinstance(value, dict):
        return {k: normalise_value(spec["fields"].get(k), v) for k, v in value.items()}
    if t == "map" and isinstance(value, dict):
        return {k: normalise_value(spec["value"], v) for k, v in value.items()}
    return value


def coerce_cli_value(spec, raw):
    """Parse a command-line value: JSON first; a bare word is accepted for strings."""
    try:
        return json.loads(raw)
    except ValueError:
        if spec is not None and spec["t"] in ("str", "enum", "date", "datetime", "hhmm", "day", "tz"):
            return raw
        raise ValueError("not valid JSON: %s (quote strings, e.g. '\"on_demand\"')" % raw)


def validate_config(cfg):
    """Problems in an indelible.json dict."""
    probs = check_value(INDELIBLE_SPEC, cfg, "indelible")
    t = (cfg or {}).get("time") or {}
    tgt, ceil = t.get("weekly_target_min"), t.get("weekly_ceiling_min")
    if isinstance(tgt, int) and isinstance(ceil, int) and ceil < tgt:
        probs.append("time.weekly_ceiling_min (%d) is below time.weekly_target_min (%d)" % (ceil, tgt))
    s = (cfg or {}).get("session") or {}
    if isinstance(s.get("length_min"), int) and isinstance(s.get("max_min"), int) and s["max_min"] < s["length_min"]:
        probs.append("session.max_min (%d) is below session.length_min (%d)" % (s["max_min"], s["length_min"]))
    seen = set()
    for sub in (cfg or {}).get("subjects") or []:
        if isinstance(sub, dict):
            if sub.get("id") in seen:
                probs.append("subject id %r appears twice" % sub.get("id"))
            seen.add(sub.get("id"))
    for w in t.get("windows") or []:
        if isinstance(w, dict) and dates.is_hhmm(w.get("from", "")) and dates.is_hhmm(w.get("to", "")):
            # "24:00" is the end of the day; a "to" earlier than "from" is an overnight
            # window (plan check reads both). Only an empty window is refused.
            if _clock_min(w["to"], end=True) == _clock_min(w["from"]):
                probs.append("time.windows: %s-%s is empty (it ends when it starts)" % (w["from"], w["to"]))
    return probs


def _clock_min(hhmm, end=False):
    """Minutes after midnight; "24:00" (and "00:00" as an end) counts as 1440."""
    t = dates.parse_hhmm(hhmm)
    m = t.hour * 60 + t.minute
    if str(hhmm).strip() == "24:00" or (end and m == 0):
        return 1440
    return m


def validate_subject(cfg):
    """Problems in a subject.json dict."""
    probs = check_value(SUBJECT_SPEC, cfg, "subject")
    w = (cfg or {}).get("cold_window_h")
    if isinstance(w, list) and len(w) == 2 and all(isinstance(x, (int, float)) for x in w) and w[0] >= w[1]:
        probs.append("cold_window_h must be [earliest, latest] hours with earliest < latest")
    b = (cfg or {}).get("block_size") or {}
    if all(isinstance(b.get(k), int) for k in ("min", "max", "default")):
        if not b["min"] <= b["default"] <= b["max"]:
            probs.append("block_size needs min <= default <= max")
    seen = set()
    for t in (cfg or {}).get("topics") or []:
        if isinstance(t, dict):
            if t.get("id") in seen:
                probs.append("topic id %r appears twice" % t.get("id"))
            seen.add(t.get("id"))
    return probs


# ==========================================================================
# Record validators (light: shape and enums)
# ==========================================================================

def _req(obj, keys, name):
    return ["%s is missing %r" % (name, k) for k in keys if k not in obj]


def _enum(obj, key, values, name, null=False):
    if key not in obj:
        return []
    v = obj[key]
    if v is None and null:
        return []
    if v not in values:
        return ["%s.%s must be one of: %s (got %r)" % (name, key, ", ".join(values), v)]
    return []


def _iso(obj, key, name, null=True):
    v = obj.get(key)
    if v is None:
        return [] if null else ["%s.%s is required" % (name, key)]
    return [] if dates.is_iso(v) else ["%s.%s is not an ISO time: %r" % (name, key, v)]


def validate_attempt(a):
    p = _req(a, ["v", "sheet", "ask", "verdict", "instrument", "at"], "attempt")
    p += _enum(a, "verdict", VERDICTS, "attempt")
    p += _enum(a, "check", CHECKS, "attempt")
    p += _enum(a, "instrument", INSTRUMENTS, "attempt")
    p += _enum(a, "prov", PROVENANCE, "attempt")
    p += _iso(a, "at", "attempt")
    return p


def validate_error(e):
    p = _req(e, ["v", "id", "topic", "kind", "status"], "error")
    if "id" in e and not ERROR_ID_RE.match(str(e["id"])):
        p.append("error.id must look like E-<subject>-NNNN")
    p += _enum(e, "kind", ERROR_KINDS, "error")
    p += _enum(e, "status", ERROR_STATUSES, "error")
    if isinstance(e.get("belief"), str) and len(e["belief"]) > 120:
        p.append("error.belief is longer than 120 characters")
    if e.get("next_due") is not None and not dates.is_date(e["next_due"]):
        p.append("error.next_due must be a date YYYY-MM-DD")
    if e.get("rung") is not None and e["rung"] not in (0, 1, 2, 3):
        p.append("error.rung must be 0-3")
    return p


def validate_session(s):
    p = _req(s, ["v", "id", "planned"], "session")
    if "id" in s and not SESSION_ID_RE.match(str(s["id"])):
        p.append("session.id must look like S-<subject>-NNNN")
    closed = s.get("closed") or {}
    p += _enum(closed, "status", CLOSED_STATUSES, "session.closed")
    if isinstance(s.get("note"), str) and len(s["note"]) > 120:
        p.append("session.note is longer than 120 characters")
    return p


def validate_exposure(x):
    p = _req(x, ["v", "topic", "at", "kind"], "exposure")
    p += _enum(x, "kind", EXPOSURE_KINDS, "exposure")
    p += _iso(x, "at", "exposure", null=False) if "at" in x else []
    return p


def validate_block(b):
    p = _req(b, ["v", "id", "subject", "kind", "status"], "block")
    if "id" in b and not BLOCK_ID_RE.match(str(b["id"])):
        p.append("block.id must look like B-YYYYMMDD-<subject>-N")
    p += _enum(b, "kind", BLOCK_KINDS, "block")
    p += _enum(b, "status", BLOCK_STATUSES, "block")
    p += _iso(b, "start", "block") + _iso(b, "end", "block")
    if b.get("start") is None:
        w = b.get("window")
        if not isinstance(w, dict) or not dates.is_iso(w.get("from", "")) or not dates.is_iso(w.get("to", "")):
            p.append("block: an obligation (start null) needs window {from, to}")
    return p


def validate_ledger(r):
    p = _req(r, ["v", "kind"], "ledger")
    p += _enum(r, "kind", LEDGER_KINDS, "ledger")
    k = r.get("kind")
    if k == "status":
        p += _req(r, ["ref", "status", "at"], "ledger status")
    else:
        if "id" in r and not LEDGER_ID_RE.match(str(r["id"])):
            p.append("ledger.id must look like L-NNNN")
        p += _req(r, ["id", "at"], "ledger")
    if k == "owed":
        p += _req(r, ["what", "due"], "ledger owed")
        p += _iso(r, "due", "ledger owed", null=False) if "due" in r else []
    if k == "decision":
        p += _req(r, ["summary", "why"], "ledger decision")
    if k == "defect":
        p += _req(r, ["category", "what", "fix_type", "fix"], "ledger defect")
        p += _enum(r, "category", DEFECT_CATEGORIES, "ledger defect")
        p += _enum(r, "fix_type", FIX_TYPES, "ledger defect")
    if k == "override":
        p += _req(r, ["said", "predict"], "ledger override")
    if k == "hypothesis":
        p += _req(r, ["statement", "rule"], "ledger hypothesis")
    return p


def validate_sheet(s):
    p = _req(s, ["v", "id", "subject", "type", "status"], "sheet")
    if "id" in s and not is_sheet_id(s["id"]):
        p.append("sheet.id must match [a-z0-9][a-z0-9-]{1,60}")
    p += _enum(s, "type", SHEET_TYPES, "sheet")
    p += _enum(s, "status", SHEET_STATUSES, "sheet")
    return p


def validate_sheetspec(spec):
    """Structural checks on a builder's sheet spec (lint does the rest)."""
    if not isinstance(spec, dict):
        return ["the sheet spec must be a JSON object"]
    p = _req(spec, ["v", "id", "type", "subject", "title", "est_min", "items"], "spec")
    if "id" in spec and not is_sheet_id(spec["id"]):
        p.append("spec.id must match [a-z0-9][a-z0-9-]{1,60}")
    p += _enum(spec, "type", SHEET_TYPES, "spec")
    if "est_min" in spec and (isinstance(spec["est_min"], bool) or not isinstance(spec["est_min"], (int, float))
                              or spec["est_min"] <= 0):
        p.append("spec.est_min must be a positive number of minutes")
    if "least_sure" in spec and not isinstance(spec["least_sure"], bool):
        p.append("spec.least_sure must be true or false")
    items = spec.get("items")
    if not isinstance(items, list):
        return p + ["spec.items must be a list"]
    ask_ids = set()
    for i, it in enumerate(items):
        name = "spec.items[%d]" % i
        if not isinstance(it, dict):
            p.append("%s must be an object" % name)
            continue
        p += _req(it, ["n", "topic", "asks"], name)
        p += _enum(it, "layer", LAYERS, name)
        if "origin" in it and not ORIGIN_RE.match(str(it["origin"])):
            p.append("%s.origin must be new, cold:<topic>, error:<E-id>, sentinel:<E-id> or official:<source>" % name)
        asks = it.get("asks")
        if not isinstance(asks, list):
            p.append("%s.asks must be a list" % name)
            continue
        for j, a in enumerate(asks):
            an = "%s.asks[%d]" % (name, j)
            if not isinstance(a, dict):
                p.append("%s must be an object" % an)
                continue
            p += _req(a, ["id", "label"], an)
            if a.get("id") in ask_ids:
                p.append("%s: ask id %r is used twice" % (an, a.get("id")))
            ask_ids.add(a.get("id"))
            if "check" in a and not isinstance(a["check"], bool):
                p.append("%s.check must be true or false" % an)
    for i, b in enumerate(spec.get("blocks") or []):
        if not isinstance(b, dict) or not isinstance(b.get("items"), list):
            p.append("spec.blocks[%d] needs a title and an items list" % i)
    for i, t in enumerate(spec.get("terms") or []):
        if not isinstance(t, dict) or not t.get("term") or not t.get("resolution"):
            p.append("spec.terms[%d] needs term and resolution" % i)
    th = spec.get("theory")
    if th is not None:
        if not isinstance(th, dict):
            p.append("spec.theory must be an object or null")
        else:
            for i, sec in enumerate(th.get("sections") or []):
                if isinstance(sec, dict):
                    p += _enum(sec, "kind", THEORY_SECTION_KINDS, "spec.theory.sections[%d]" % i)
    return p


def validate_answers(ans):
    """Structural checks on an answers file (the key). Never prints its content."""
    if not isinstance(ans, dict) or not ans:
        return ["the answers file must be a non-empty JSON object keyed by ask id"]
    p = []
    for k, v in ans.items():
        if not isinstance(v, dict):
            p.append("answers[%s] must be an object" % k)
            continue
        if not isinstance(v.get("accept"), list) or not v["accept"]:
            p.append("answers[%s].accept must be a non-empty list" % k)
    return p


def validate_grades(g):
    if not isinstance(g, dict):
        return ["the grades file must be a JSON object"]
    p = _req(g, ["asks"], "grades")
    if g.get("date") is not None and not dates.is_date(g["date"]):
        p.append("grades.date must be YYYY-MM-DD")
    for k in ("start", "stop"):
        if g.get(k) is not None and not dates.is_hhmm(g[k]):
            p.append("grades.%s must be HH:MM" % k)
    asks = g.get("asks")
    if not isinstance(asks, list):
        return p + ["grades.asks must be a list"]
    seen = set()
    for i, a in enumerate(asks):
        name = "grades.asks[%d]" % i
        if not isinstance(a, dict):
            p.append("%s must be an object" % name)
            continue
        p += _req(a, ["ask", "verdict"], name)
        if a.get("ask") in seen:
            p.append("%s: ask %r graded twice" % (name, a.get("ask")))
        seen.add(a.get("ask"))
        p += _enum(a, "verdict", VERDICTS, name)
        p += _enum(a, "check", CHECKS, name)
        p += _enum(a, "kind", ERROR_KINDS, name, null=True)
        if "least_sure" in a and not isinstance(a["least_sure"], bool):
            p.append("%s.least_sure must be true or false" % name)
        if isinstance(a.get("belief"), str) and len(a["belief"]) > 120:
            p.append("%s.belief is longer than 120 characters" % name)
    return p


VALIDATORS = {
    "indelible": validate_config, "subject": validate_subject, "attempt": validate_attempt,
    "error": validate_error, "session": validate_session, "exposure": validate_exposure,
    "block": validate_block, "ledger": validate_ledger, "sheet": validate_sheet,
    "sheetspec": validate_sheetspec, "answers": validate_answers, "grades": validate_grades,
}


def validate(record, obj):
    fn = VALIDATORS.get(record)
    return fn(obj) if fn else []


# ==========================================================================
# Examples and field notes (``schema <record>``)
# ==========================================================================

T = "2026-10-15T07:40+01:00"

RECORDS = {
    "indelible": {
        "file": "<ws>/indelible.json",
        "kind": "snapshot; learner-wide config",
        "example": {
            "v": 1, "timezone": "Europe/Lisbon",
            "learner": {"age_band": "18+", "l1": "pt", "instruction_lang": "en", "gloss": "first_use",
                        "tone": "B", "vocab": "plain", "chat_math": "unicode"},
            "time": {"schedule": "scheduled", "weekly_target_min": 240, "weekly_ceiling_min": 336,
                     "sleep": {"bed": "23:30", "wake": "07:00"}, "rest_day": "Sun", "buffer_pct": 15,
                     "windows": [{"days": ["Mon", "Tue", "Thu"], "from": "07:00", "to": "08:15"},
                                 {"days": ["Sat"], "from": "10:00", "to": "12:00"}],
                     "blocked": [{"days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "from": "09:00", "to": "18:00", "what": "work"},
                                 {"date": "2026-10-17", "what": "wedding"}]},
            "session": {"length_min": 60, "max_min": 90, "days_per_week": 4, "overrun": "ask",
                        "extension_max_min": 15, "break_every_min": 75, "break_min": 10},
            "policies": {"missed": "ask", "calendar_write": "preview_confirm"},
            "render": {"backend": None, "verified_at": None},
            "calendar": {"provider": "none", "signature": None, "reminder_min": 15, "target": None},
            "subjects": [{"id": "ielts", "dir": "ielts", "state": "live", "priority": 1,
                          "target_weekly_min": 240, "min_weekly_min": None}],
            "drop_order": ["buffer"],
        },
        "notes": [
            ("timezone", "IANA name, e.g. Europe/Lisbon; null until known"),
            ("learner.tone", "A (blunt) | B (wise feedback, the default)"),
            ("learner.vocab", "plain (learner sees '2-day recheck', 'fixed', 'to do', no IDs) | technical"),
            ("learner.gloss", "first_use | always | off: first-language glosses on hard words"),
            ("time.schedule", "scheduled | on_demand (no attendance questions in on_demand)"),
            ("time.weekly_ceiling_min", "defaults to round(1.4 x weekly_target_min)"),
            ("time.windows", "[{days:[Mon..Sun], from:HH:MM, to:HH:MM}] usual study windows (soft)"),
            ("time.blocked", "[{days, from, to, what}] or [{date, what}] hard unavailability"),
            ("session.*", "length_min, max_min, days_per_week, overrun ask|stop|extend, extension_max_min, break_every_min, break_min"),
            ("policies.missed", "ask | auto_move | drop"),
            ("policies.calendar_write", "preview_confirm | auto_move_24h | none"),
            ("render.backend", "first working renderer recorded by doctor (typst, chrome, html, md)"),
            ("calendar.provider", "none | ics | ticktick | google | other"),
            ("subjects[]", "{id, dir, state live|shadow|legacy|paused, priority, target_weekly_min, min_weekly_min}"),
            ("change", "indelible.py set root <dotted.path> <json-value> [--dry-run]"),
        ],
    },
    "subject": {
        "file": "<ws>/<subject>/subject.json",
        "kind": "snapshot; one per subject",
        "example": {
            "v": 1, "id": "ielts", "title": "IELTS Academic", "profile": "exam", "intensity": "standard",
            "target": {"goal": "IELTS Academic 7.0", "why": "master's offer",
                       "success": "7.0 overall, no band under 6.5", "date": "2026-12-12", "floor": "6.5"},
            "format": {"minutes": 165, "answer_form": "short", "tools": "none", "reference_sheet": False,
                       "time_of_day": "09:00", "accommodations": None, "ai_policy": None},
            "topics": [{"id": "T01", "name": "Matching headings", "weight": None, "layer": "reading",
                        "floor": [], "confusable_with": [], "scope": "in"}],
            "taxonomy": [{"code": "V", "name": "a word stopped me", "treatment": "glossary + words sheet"}],
            "cold_window_h": [44, 72],
            "block_size": {"min": 3, "max": 8, "default": 6},
            "pace_s": {"procedural": 30, "conceptual": 90, "verbal": 75, "reading": 70, "production": 180, "code": 300},
            "sense_list": [], "lexicon": [],
            "checkpoints": [],
            "materials": {"sources": [], "ration": []},
            "overrides": [],
        },
        "notes": [
            ("profile", "exam | course | interview | language | code | skill"),
            ("intensity", "standard | light"),
            ("target.date", "YYYY-MM-DD or null; caps the mistake ladder (due dates stop 2 days before)"),
            ("topics[]", "{id, name, weight, layer, floor[], confusable_with[], scope in|out}; add with: topic add"),
            ("topics[].layer", "procedural | conceptual | verbal | reading | production | code"),
            ("taxonomy[]", "{code, name, treatment}: miss modes for this subject; C = careless slip, V = a word stopped me"),
            ("cold_window_h", "[earliest, latest] hours after the last warm exposure for the 2-day recheck"),
            ("block_size", "drill blocks of one operation: min, max, default items"),
            ("pace_s", "seconds per question by layer; sizes the session budget"),
            ("sense_list / lexicon", "extra words the term check treats like sense_seed.txt / owned words"),
            ("checkpoints[]", "{date, instrument, threshold, if_below, status armed|passed|failed, result}"),
            ("overrides[]", "{rule, value, why (learner's words), date, locked}"),
            ("change", "indelible.py set <subject> <dotted.path> <json-value> [--dry-run]"),
        ],
    },
    "topics": {
        "file": "<ws>/<subject>/data/topics.json",
        "kind": "snapshot; computed by the CLI, never typed by hand",
        "example": {"T01": {"level": 2, "level_basis": "practice 5/6 on ielts-headings-01-drills (2026-10-13)",
                            "taught_at": "2026-10-13T07:20+01:00", "taught_by": "sheet", "last_cold": None,
                            "cold_passes": [], "explanation_on_file": False, "note": ""}},
        "notes": [
            ("level", "0 | 1 | 2 | \"3p\" | 3 | 4 | 5 (see below)"),
            ("0", "no evidence, or the latest measurement under 25%"),
            ("1", "latest measurement 25-74%"),
            ("2", "practice scored >= 75% on some day"),
            ("3p", ">= 75% on diagnostic/mock/checkpoint asks with >= 4 asks; 3 after a cold pass within 14 days"),
            ("3", ">= 75% on a cold sheet inside the cold window, no exposure in the prior 24 h"),
            ("4", "a second cold pass >= 75%, at least 7 days after the first"),
            ("5", ">= 75% on the topic's asks in a mock or checkpoint after reaching 4"),
            ("drop", "a later cold fail (< 50%) drops the level to 2; level_basis says so"),
            ("least_sure", "asks named on the Least-sure line never count toward a level"),
            ("taught_by", "sheet | external | chat | tutor"),
            ("recompute", "indelible.py topic recompute <subject>"),
        ],
    },
    "sheet": {
        "file": "<ws>/<subject>/data/sheets.jsonl",
        "kind": "snapshot; one row per sheet",
        "example": {"v": 1, "id": "ielts-cold-03", "subject": "ielts", "type": "cold", "measures": True,
                    "topics": ["T01", "T04"], "asks": 14, "est_min": 12, "status": "issued",
                    "created": "2026-10-14T19:05+01:00", "lint": "PASS",
                    "files": ["sheets/2026-10/ielts-cold-03.pdf"], "key_sha": "<sha256 of the sealed key>",
                    "issued_at": "2026-10-14T19:20+01:00", "sat": {"start": None, "stop": None, "date": None},
                    "evidence": [], "graded_at": None, "opens_unsat": 0, "block": None},
        "notes": [
            ("id", "free slug matching [a-z0-9][a-z0-9-]{1,60}, e.g. ielts-cold-03"),
            ("type", " | ".join(SHEET_TYPES)),
            ("measures", "true for " + ", ".join(MEASURING_TYPES)),
            ("status", "built -> linted -> rendered -> issued -> sat -> graded; or void"),
            ("sat", "{start HH:MM, stop HH:MM, date YYYY-MM-DD} from items 0 and N"),
            ("evidence", "filed by scan ingest; required before key open and grading"),
            ("opens_unsat", "brief opens while the sheet is issued but not yet taken; 2 force a decision"),
            ("sealed", "a sealed instrument is never edited after issue"),
        ],
    },
    "attempt": {
        "file": "<ws>/<subject>/data/attempts.jsonl",
        "kind": "append; one row per graded question",
        "example": {"v": 1, "sheet": "ielts-cold-03", "item": 3, "ask": "3a", "topic": "T04", "layer": "verbal",
                    "instrument": "cold", "cold": True, "interval_h": 49.0, "verdict": "wrong", "score": 0,
                    "check": "filled", "least_sure": False, "mode": "V",
                    "account": "didn't know 'albeit'; guessed 'because'", "error_id": "E-ielts-0031", "at": T,
                    "prov": "measured"},
        "notes": [
            ("verdict", "right (1) | half (0.5) | wrong (0) | dont_know (0) | skip (0)"),
            ("check", "filled | missing | caught (answer changed after a failed check) | n/a"),
            ("least_sure", "true if the ask is on the sheet's closing 'Least sure of' line"),
            ("instrument", " | ".join(INSTRUMENTS) + "; drills, mixed, repair, review, example -> practice"),
            ("interval_h", "hours since the topic's last warm exposure"),
            ("mode", "a code from the subject taxonomy; account = the learner's own words"),
            ("prov", "practice | measured (measured iff the instrument measures)"),
            ("sheet_type", "the sheet's type; theory, external, example and repair answers (done with the "
                           "explanation in view) never count toward a level"),
            ("contaminated", "true on a recheck question whose topic was seen in the 24 h before the sitting: "
                             "recorded, not counted"),
            ("levels", "a right answer on the Least-sure line does not count; a wrong one always does"),
            ("written by", "grade record; never by hand"),
        ],
    },
    "error": {
        "file": "<ws>/<subject>/data/errors.jsonl",
        "kind": "snapshot; open and recently retired mistakes",
        "example": {"v": 1, "id": "E-ielts-0031", "opened": "2026-10-15", "sheet": "ielts-cold-03", "item": 3,
                    "topic": "T04", "kind": "belief", "mode": "V", "belief": "reads 'albeit' as 'because'",
                    "account": "didn't know 'albeit'; guessed 'because'", "named_least_sure": False,
                    "status": "untreated", "repair_at": None, "rung": 0, "next_due": None, "passes": [],
                    "fails": [], "answer_ref": ".indelible/keys/errors/E-ielts-0031.json", "prov": "measured"},
        "notes": [
            ("id", "E-<subject>-NNNN, never reused"),
            ("kind", "belief (a wrong idea; repair before cold) | slip (careless or answer form) | shaky (right but on the Least-sure line, or a guess)"),
            ("status", "untreated | spacing | retired | reopened"),
            ("belief", "at most 120 characters; never contains the correct answer"),
            ("ladder", "rungs +1 d, +3 d, +7 d, +21 d; slip starts at rung 0, shaky at rung 1, belief after repair at rung 0"),
            ("next_due", "YYYY-MM-DD, capped 2 days before target.date (never before tomorrow)"),
            ("passes / fails", "dates of re-serves; a failed belief goes back to untreated"),
            ("answer_ref", "the key entry, readable only through key open"),
        ],
    },
    "session": {
        "file": "<ws>/<subject>/data/sessions.jsonl",
        "kind": "append; written by session close",
        "example": {"v": 1, "id": "S-ielts-0012", "block": "B-20261015-ielts-1", "kind": "teach",
                    "planned": {"start": "2026-10-15T07:00+01:00", "min": 60},
                    "actual": {"start": "2026-10-15T07:02+01:00", "end": "2026-10-15T08:04+01:00", "elapsed_min": 62},
                    "sheets": ["ielts-cold-03", "ielts-headings-01-drills"],
                    "asks": {"n": 26, "right": 19, "half": 1, "wrong": 4, "dont_know": 1, "skip": 1},
                    "overrun_min": 2, "note": "Recheck done; headings drills [practice].",
                    "closed": {"at": "2026-10-15T08:06+01:00", "status": "same-day"}},
        "notes": [
            ("id", "S-<subject>-NNNN"),
            ("asks", "tallies of the questions graded since the session started"),
            ("overrun_min", "max(0, elapsed - planned)"),
            ("note", "at most 120 characters"),
            ("closed.status", "same-day | late | with-todos"),
        ],
    },
    "exposure": {
        "file": "<ws>/<subject>/data/exposures.jsonl",
        "kind": "append; warm exposures for the 24-hour rule",
        "example": {"v": 1, "topic": "T04", "at": "2026-10-13T07:20+01:00", "kind": "teach"},
        "notes": [
            ("kind", "teach | repair | chat | drill | review"),
            ("rule", "a topic is not served cold within 24 h of any exposure"),
            ("written by", "session taught, session expose, error repair; grade record logs a drill exposure "
                           "for practice sheets only, timed at the sitting (a measuring sheet logs none)"),
        ],
    },
    "block": {
        "file": "<ws>/plan/blocks.jsonl",
        "kind": "snapshot; all subjects' blocks and obligations",
        "example": {"v": 1, "id": "B-20261015-ielts-1", "subject": "ielts", "kind": "teach",
                    "start": "2026-10-15T07:00+01:00", "end": "2026-10-15T08:00+01:00", "window": None,
                    "protected": True, "measurement": False, "soft": False, "pair": None,
                    "content": "2-day recheck, then new skill", "status": "planned", "cal": None,
                    "moved_from": None, "miss_reason": None},
        "notes": [
            ("id", "B-YYYYMMDD-<subject>-N"),
            ("kind", " | ".join(BLOCK_KINDS)),
            ("obligation", "start null and window {from, to}; the cold serve made by session taught (kind cold, protected, content cold:<topic>)"),
            ("status", " | ".join(BLOCK_STATUSES)),
            ("cal", "{provider, id, etag, start at last ack} or null"),
            ("misses", "[{at, slot, reason}] from plan miss; kept when the block is rebooked, so it still "
                       "counts as missed"),
            ("title rule", "a cold block's calendar title never names a topic: '2-day recheck (mixed)'"),
        ],
    },
    "ledger": {
        "file": "<ws>/ledger.jsonl",
        "kind": "append-only; the latest status event for a ref wins",
        "example": [
            {"v": 1, "id": "L-0004", "kind": "owed", "subject": "ielts", "by": "learner",
             "what": "Register for the 12 Dec sitting", "due": "2026-10-20T20:00+01:00", "at": T},
            {"v": 1, "id": "L-0005", "kind": "decision", "subject": "ielts", "by": "learner",
             "summary": "Saturday timed section moves to 09:00", "why": "learner's words",
             "safeguard": {"check_on": "2026-11-14", "rule": "timed accuracy < 0.70", "action": "revert"}, "at": T},
            {"v": 1, "id": "L-0006", "kind": "defect", "subject": "ielts", "category": "undefined_term",
             "what": "'gist' used undefined", "fix_type": "lint", "fix": "sense_list += gist", "at": T},
            {"v": 1, "id": "L-0007", "kind": "override", "subject": "ielts", "said": "learner's words",
             "predict": "items 2 and 5 right", "scored": None, "at": T},
            {"v": 1, "kind": "status", "ref": "L-0004", "status": "done", "at": T},
        ],
        "notes": [
            ("kind", "owed | decision | defect | override | hypothesis | status"),
            ("owed", "requires due (a time); 'tomorrow' without one is a broken promise"),
            ("defect.category", ", ".join(DEFECT_CATEGORIES)),
            ("defect.fix_type", "rule | template | lint | script | planner; a repeat category cannot be fixed by 'rule' again"),
            ("status", "{kind: status, ref, status done|dropped|scored, at}"),
            ("write", "indelible.py ledger add ... / ledger close <L-id>"),
        ],
    },
    "sheetspec": {
        "file": "<ws>/<subject>/.indelible/tmp/<id>.spec.json (written by the builder)",
        "kind": "visible sheet spec: no answers",
        "example": {"v": 1, "id": "ielts-cold-03", "type": "cold", "subject": "ielts", "title": "2-day recheck",
                    "est_min": 12, "tools": "none", "answer_form": "short",
                    "items": [{"n": 1, "topic": "T04", "layer": "verbal", "op": "match-paraphrase",
                               "origin": "cold:T04", "text": "<the question text>",
                               "asks": [{"id": "1a", "label": "Sentence that means the same:", "check": True,
                                         "check_hint": "Re-read the sentence with your answer in it"}]}],
                    "blocks": [{"title": "Block A", "items": [1]}],
                    "terms": [{"term": "paraphrase", "resolution": "defined_on:ielts-paraphrase-01-theory"}],
                    "theory": None, "least_sure": True},
        "notes": [
            ("type", " | ".join(SHEET_TYPES)),
            ("origin", "new | cold:<topic> | error:<E-id> | sentinel:<E-id> | official:<source>; error:/sentinel: "
                       "move the ladder only on cold, mixed and measuring sheets, so repair, theory and drill "
                       "pencils use new (name the E-id in op or text if useful)"),
            ("asks[]", "{id, label, check, check_hint}: one labelled blank per required answer; optional topic "
                       "(a question on another topic than its item, e.g. one hidden-test group), answer_form "
                       "(letter, number, word, test-line, short, sentence, long, code, none: sizes the box), "
                       "answer_in_passage (the answer is copied from the passage: lint L8 allows it there)"),
            ("check", "a written backwards check beside the answer (put the answer back in, rebuild the total, or test the definition used); required on drills, cold, mixed, diagnostic, mock, checkpoint, review"),
            ("least_sure", "true on every type except theory, external, example, triage: one closing line 'Least sure of: ___'. There are no per-answer confidence marks"),
            ("terms[]", "every sense-list word used on the sheet (code spans and fenced code are not scanned; "
                        "theory bodies are), with its resolution: defined_here (in theory.words), "
                        "defined_on:<sheet-id>, glossary (the learner owns it: glossary add), everyday (its plain "
                        "sense; not for a lexicon word) or measured_here (a measuring sheet that tests the word)"),
            ("theory", "{floor[], words[{term, gloss, def}], sections[{kind, title, body}], pages} on theory, external, example, repair"),
            ("unlabelled", "measuring sheets name no topic in titles or labels and, when they hold 2 or more "
                           "topics, never put two same-topic items together"),
            ("block", "sheet new/lint --block ID links the block it is built for: L5 uses its minutes, L7 judges "
                      "a recheck at its start"),
            ("next", "indelible.py sheet new <subject> <id> --spec PATH --answers PATH, then sheet lint"),
        ],
    },
    "answers": {
        "file": "<ws>/<subject>/.indelible/tmp/<id>.answers.json (builder only; sealed and deleted by sheet new)",
        "kind": "the answer key: never shown in chat",
        "example": {"1a": {"accept": ["<accepted answer>"], "check": "<what a correct check line shows>",
                           "solution": "<short worked solution>"}},
        "notes": [
            ("keys", "ask ids from the spec"),
            ("accept", "accepted answer strings; lint fails if one of 3+ characters appears in the visible sheet"),
            ("sealing", "sheet new moves it to .indelible/keys/<id>.json (mode 600) and deletes the answers file"),
            ("reading", "only indelible.py key open, and only after evidence of the attempt is filed"),
        ],
    },
    "grades": {
        "file": "any path, passed to: indelible.py grade record <subject> <id> --from grades.json",
        "kind": "input: verdicts for one sitting",
        "example": {"start": "07:05", "stop": "07:17", "date": "2026-10-15",
                    "asks": [{"ask": "1a", "verdict": "right", "check": "filled", "least_sure": False},
                             {"ask": "3a", "verdict": "wrong", "check": "filled", "least_sure": False, "mode": "V",
                              "account": "didn't know 'albeit'; guessed 'because'", "kind": "belief",
                              "belief": "reads 'albeit' as 'because'"}]},
        "notes": [
            ("start / stop", "HH:MM from items 0 and N; date YYYY-MM-DD"),
            ("verdict", "right | half | wrong | dont_know | skip ('I don't know' is always an accepted answer)"),
            ("check", "filled | missing | caught | n/a"),
            ("least_sure", "true if the learner named this ask on the Least-sure line"),
            ("kind", "belief | slip | shaky: creates an error for wrong, half or dont_know asks"),
            ("account", "the learner's own words, asked before classifying; or 'no account'"),
            ("belief", "at most 120 characters; never the correct answer"),
        ],
    },
    "lock": {
        "file": "<ws>/<subject>/.indelible/session.lock",
        "kind": "JSON; written by session open, removed by a passing session close",
        "example": {"session_id": "S-ielts-0012", "start": "2026-10-15T07:00+01:00", "planned_min": 60,
                    "planned_end": "2026-10-15T08:00+01:00", "close_start": "2026-10-15T07:55+01:00",
                    "block": "B-20261015-ielts-1", "kind": "teach"},
        "notes": [
            ("close_start", "planned_end - close minutes (2 if planned <= 30, 5 if <= 75, else 8)"),
            ("unclosed", "the lock exists and now > planned_end + 2 h, or .indelible/unclosed exists"),
        ],
    },
}

RECORD_NAMES = ["indelible", "subject", "topics", "sheet", "attempt", "error", "session", "exposure",
                "block", "ledger", "sheetspec", "answers", "grades", "lock"]


def example(record):
    return json.loads(json.dumps(RECORDS[record]["example"]))


def describe(record):
    """The text printed by ``schema <record>``."""
    r = RECORDS[record]
    lines = ["%s: %s (%s)" % (record, r["file"], r["kind"]), "", "Example:"]
    ex = r["example"]
    if isinstance(ex, list):
        lines.extend(json.dumps(row, ensure_ascii=False) for row in ex)
    else:
        lines.append(json.dumps(ex, ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("Fields:")
    width = max(len(k) for k, _ in r["notes"])
    for k, note in r["notes"]:
        lines.append("  %s  %s" % (k.ljust(width), note))
    if record not in ("topics", "lock", "answers", "grades"):
        lines.append("  %s  every record carries \"v\": 1" % "v".ljust(width))
    return "\n".join(lines)
