"""RFC 5545 export: a VCALENDAR with one VEVENT per plan block.

Pure functions, standard library only. ``cmd_plan`` turns blocks into event
dicts and calls ``build_calendar``; this module knows nothing about the
workspace.

What the output guarantees:

- CRLF line endings, including after the last line.
- Content lines folded at 75 octets (RFC 5545 section 3.1). A continuation
  line starts with one space, which counts toward its 75 octets. Folding
  counts UTF-8 bytes and never splits a multi-byte character.
- TEXT values escape backslash, semicolon, comma and newlines (section
  3.3.11). Other control characters are dropped.
- DTSTART, DTEND and DTSTAMP are written in UTC (``YYYYMMDDTHHMMSSZ``).
- ``UID`` is ``<block-id>@indelible``; ``SEQUENCE`` counts the block's moves.
- A VALARM with ``TRIGGER:-PT<n>M`` when a reminder is set.

Event dict fields (``build_calendar(events)``)::

    {"uid": "B-20261015-ielts-1@indelible", "start": datetime, "end": datetime,
     "dtstamp": datetime, "summary": str, "description": str or None,
     "sequence": int, "alarm_min": int or None, "categories": [str]}

Datetimes must be timezone-aware.
"""

import re
from datetime import timezone

CRLF = "\r\n"
MAX_OCTETS = 75
PRODID = "-//indelible//indelible %s//EN"

_CTL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


# --------------------------------------------------------------------------
# Values
# --------------------------------------------------------------------------

def escape_text(value):
    """Escape a TEXT value: backslash, semicolon, comma and newlines."""
    text = "" if value is None else "%s" % (value,)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CTL_RE.sub("", text)
    text = text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    return text.replace("\n", "\\n")


def fmt_utc(dt):
    """An aware datetime as a UTC DATE-TIME: ``20261015T060000Z``."""
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("fmt_utc needs an aware datetime, got %r" % (dt,))
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def fmt_duration_min(minutes):
    """``15`` -> ``PT15M`` (whole minutes, never negative)."""
    return "PT%dM" % max(0, int(minutes))


# --------------------------------------------------------------------------
# Lines
# --------------------------------------------------------------------------

def fold_line(line, limit=MAX_OCTETS):
    """Fold one content line into physical lines of at most ``limit`` octets.

    The pieces are joined with CRLF plus one space. A cut never falls inside
    a UTF-8 sequence, so every physical line is valid UTF-8 on its own.
    """
    data = line.encode("utf-8")
    if len(data) <= limit:
        return line
    pieces = []
    pos = 0
    first = True
    while pos < len(data):
        room = limit if first else limit - 1  # the leading space takes one octet
        end = min(pos + room, len(data))
        # Step back over continuation bytes (10xxxxxx) to a character boundary.
        while end < len(data) and end > pos and (data[end] & 0xC0) == 0x80:
            end -= 1
        chunk = data[pos:end].decode("utf-8")
        pieces.append(chunk if first else " " + chunk)
        pos = end
        first = False
    return CRLF.join(pieces)


def join_lines(lines):
    """Fold every content line and join with CRLF (a CRLF also ends the text)."""
    return CRLF.join(fold_line(l) for l in lines) + CRLF


# --------------------------------------------------------------------------
# Components
# --------------------------------------------------------------------------

def vevent_lines(ev):
    """Unfolded content lines of one VEVENT."""
    summary = escape_text(ev.get("summary") or "")
    lines = [
        "BEGIN:VEVENT",
        "UID:" + escape_text(ev["uid"]),
        "DTSTAMP:" + fmt_utc(ev["dtstamp"]),
        "DTSTART:" + fmt_utc(ev["start"]),
        "DTEND:" + fmt_utc(ev["end"]),
        "SEQUENCE:%d" % max(0, int(ev.get("sequence") or 0)),
        "SUMMARY:" + summary,
    ]
    if ev.get("description"):
        lines.append("DESCRIPTION:" + escape_text(ev["description"]))
    cats = [c for c in (ev.get("categories") or []) if c]
    if cats:
        lines.append("CATEGORIES:" + ",".join(escape_text(c) for c in cats))
    lines.append("STATUS:CONFIRMED")
    lines.append("TRANSP:OPAQUE")
    alarm = ev.get("alarm_min")
    if alarm is not None:
        lines += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            "DESCRIPTION:" + (summary or "Reminder"),
            "TRIGGER:-" + fmt_duration_min(alarm),
            "END:VALARM",
        ]
    lines.append("END:VEVENT")
    return lines


def calendar_lines(events, version="0.1.0", name=None):
    """Unfolded content lines of a whole VCALENDAR."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:" + PRODID % version,
        "CALSCALE:GREGORIAN",
    ]
    if name:
        lines.append("X-WR-CALNAME:" + escape_text(name))
    for ev in events:
        lines.extend(vevent_lines(ev))
    lines.append("END:VCALENDAR")
    return lines


def build_calendar(events, version="0.1.0", name=None):
    """The complete .ics text: folded, CRLF line endings."""
    return join_lines(calendar_lines(events, version=version, name=name))
