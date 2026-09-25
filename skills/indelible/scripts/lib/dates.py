"""Dates and times.

- ``now()`` returns an aware local datetime. If the environment variable
  ``INDELIBLE_NOW`` holds an ISO 8601 time, that value is used instead (every
  test sets it).
- Times are stored as ``YYYY-MM-DDTHH:MM+HH:MM``; seconds are accepted on read.
  Dates are stored as ``YYYY-MM-DD``.
- ``parse_iso`` accepts ``Z``, ``+HHMM``, ``+HH``, fractional seconds of any
  length and the compact calendar form ``20261015T070000Z``. Python 3.9's
  ``fromisoformat`` accepts none of these, so the parsing is done by hand.
- ``plus`` and ``hours_from`` do *elapsed* arithmetic (through UTC), so a
  window of 44-72 hours stays 44-72 hours across a clock change. Adding a
  timedelta to a zoneinfo-aware datetime is wall-clock arithmetic and is off
  by an hour across a change; use these instead.
- ``tz_for`` loads an IANA zone with zoneinfo. When the zone cannot be loaded
  (Windows without the ``tzdata`` package), it falls back to the computer's
  own zone rules through the operating system (``SystemLocalTimezone``),
  never to a fixed offset, except under the test clock ``INDELIBLE_NOW``.
  ``zone_problem`` says when that happened, for ``doctor`` and ``brief``.
"""

import os
import re
import time as _time
from datetime import date, datetime, time, timedelta, timezone, tzinfo

from lib import UsageError

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

_ISO_RE = re.compile(
    r"^(?P<y>\d{4})-(?P<mo>\d{2})-(?P<d>\d{2})"
    r"(?:[T t](?P<h>\d{2}):(?P<mi>\d{2})(?::(?P<s>\d{2})(?:[.,](?P<f>\d+))?)?)?"
    r"\s*(?P<tz>[Zz]|[+-]\d{2}(?::?\d{2})?)?$"
)
_COMPACT_RE = re.compile(
    r"^(?P<y>\d{4})(?P<mo>\d{2})(?P<d>\d{2})"
    r"(?:T(?P<h>\d{2})(?P<mi>\d{2})(?P<s>\d{2})?)?"
    r"(?P<tz>Z|[+-]\d{4})?$"
)
_HHMM_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# --------------------------------------------------------------------------
# Clock
# --------------------------------------------------------------------------

def _system_now():
    return datetime.now().astimezone()


def now():
    """The current time, aware. Honours ``INDELIBLE_NOW``."""
    fixed = os.environ.get("INDELIBLE_NOW", "").strip()
    if fixed:
        try:
            return parse_iso(fixed, tz=_system_now().tzinfo)
        except ValueError:
            raise UsageError("INDELIBLE_NOW is not an ISO 8601 time: %r" % fixed)
    return _system_now()


def local_tz():
    """The tzinfo of ``now()`` (a fixed offset when ``INDELIBLE_NOW`` is set)."""
    return now().tzinfo


def today():
    return now().date()


class SystemLocalTimezone(tzinfo):
    """The computer's own time zone, with its clock changes, read from the OS.

    The classic ``LocalTimezone`` pattern: each instant's offset comes from
    ``time.localtime``/``time.mktime``, so it is right on both sides of a
    clock change even when zoneinfo has no database (Windows without tzdata).
    """

    _EPOCH = datetime(1970, 1, 1)

    def _offset_at_wall(self, dt):
        tt = (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, dt.weekday(), 0, -1)
        try:
            stamp = _time.mktime(tt)
            return timedelta(seconds=_time.localtime(stamp).tm_gmtoff)
        except (OverflowError, ValueError, OSError):
            return timedelta(seconds=_time.localtime().tm_gmtoff)

    def utcoffset(self, dt):
        if dt is None:
            return timedelta(seconds=_time.localtime().tm_gmtoff)
        return self._offset_at_wall(dt)

    def dst(self, dt):
        if dt is None:
            return timedelta(0)
        tt = (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, dt.weekday(), 0, -1)
        try:
            isdst = _time.localtime(_time.mktime(tt)).tm_isdst > 0
        except (OverflowError, ValueError, OSError):
            isdst = False
        if not isdst:
            return timedelta(0)
        return timedelta(seconds=_time.timezone - _time.altzone) if _time.daylight else timedelta(0)

    def tzname(self, dt):
        return _time.tzname[1 if self.dst(dt) else 0]

    def fromutc(self, dt):
        naive = dt.replace(tzinfo=None)
        try:
            stamp = (naive - self._EPOCH).total_seconds()
            off = timedelta(seconds=_time.localtime(stamp).tm_gmtoff)
        except (OverflowError, ValueError, OSError):
            off = timedelta(seconds=_time.localtime().tm_gmtoff)
        return (naive + off).replace(tzinfo=self)

    def __repr__(self):
        return "SystemLocalTimezone()"


_SYSTEM_TZ = SystemLocalTimezone()


def system_tz():
    """The computer's own zone (OS-backed, right across clock changes)."""
    return _SYSTEM_TZ


def _load_zone(name):
    try:
        from zoneinfo import ZoneInfo  # Python 3.9+
        return ZoneInfo(name)
    except Exception:
        return None


def _test_clock():
    return bool(os.environ.get("INDELIBLE_NOW", "").strip())


def tz_for(name):
    """A tzinfo for an IANA name.

    ``zoneinfo`` needs the system tz database (or the ``tzdata`` package on
    Windows). When the zone cannot be loaded, or no name is given, the
    computer's own zone is used through the OS, so clock changes still apply.
    Under the test clock (``INDELIBLE_NOW``) the fallback is that clock's
    fixed offset, so tests do not depend on the machine they run on.
    """
    if name:
        zone = _load_zone(name)
        if zone is not None:
            return zone
    if _test_clock():
        return local_tz()
    return _SYSTEM_TZ


def zone_problem(name):
    """A one-line warning when the workspace time zone cannot be used as given, else None."""
    if not name:
        return ("no time zone is recorded for this workspace, so times follow this computer's zone; "
                "set it with: indelible.py set root timezone '\"Area/City\"'")
    if _load_zone(name) is None:
        return ("the time zone %s cannot be loaded here (no time zone database; on Windows run: "
                "py -3 -m pip install tzdata), so times follow this computer's own zone instead" % name)
    return None


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

def _offset(text):
    if text in ("Z", "z"):
        return timezone.utc
    sign = -1 if text[0] == "-" else 1
    digits = text[1:].replace(":", "")
    hours = int(digits[:2])
    minutes = int(digits[2:4]) if len(digits) >= 4 else 0
    return timezone(sign * timedelta(hours=hours, minutes=minutes))


def parse_iso(value, tz=None, aware=True):
    """Parse an ISO 8601 date or time into a datetime.

    Accepts datetime and date objects (returned as datetimes), ``Z``,
    ``+HH:MM``, ``+HHMM``, ``+HH``, fractional seconds and the compact
    calendar form. A value without an offset gets ``tz`` (default: the local
    tz of ``now()``) unless ``aware`` is False. Raises ValueError.
    """
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day)
    else:
        if value is None:
            raise ValueError("no time given")
        text = str(value).strip()
        m = _ISO_RE.match(text) or _COMPACT_RE.match(text)
        if not m:
            raise ValueError("not an ISO 8601 time: %r" % (value,))
        g = m.groupdict()
        frac = g.get("f") or ""
        micro = int((frac + "000000")[:6]) if frac else 0
        try:
            dt = datetime(
                int(g["y"]), int(g["mo"]), int(g["d"]),
                int(g.get("h") or 0), int(g.get("mi") or 0), int(g.get("s") or 0),
                micro,
            )
        except ValueError as exc:
            raise ValueError("not a valid time: %r (%s)" % (value, exc))
        if g.get("tz"):
            dt = dt.replace(tzinfo=_offset(g["tz"]))
    if aware and dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz if tz is not None else local_tz())
    return dt


def try_parse_iso(value, tz=None):
    """Like parse_iso but returns None instead of raising."""
    if value in (None, ""):
        return None
    try:
        return parse_iso(value, tz=tz)
    except (ValueError, TypeError):
        return None


def parse_date(value):
    """Parse ``YYYY-MM-DD`` (or any ISO time) into a date. Raises ValueError."""
    return to_date(value)


def to_date(value):
    """date, datetime or ISO string -> date. A datetime keeps its own local date."""
    if value is None:
        raise ValueError("no date given")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if _DATE_RE.match(text):
        try:
            return date(int(text[:4]), int(text[5:7]), int(text[8:10]))
        except ValueError as exc:
            raise ValueError("not a valid date: %r (%s)" % (value, exc))
    return parse_iso(text, aware=False).date()


def parse_hhmm(value):
    """``"07:00"`` -> time(7, 0). Raises ValueError."""
    m = _HHMM_RE.match(str(value).strip())
    if not m:
        raise ValueError("not a HH:MM time: %r" % (value,))
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 24 or mi > 59 or (h == 24 and mi != 0):
        raise ValueError("not a HH:MM time: %r" % (value,))
    if h == 24:
        return time(0, 0)
    return time(h, mi)


def is_hhmm(value):
    try:
        parse_hhmm(value)
        return True
    except (ValueError, TypeError):
        return False


def is_date(value):
    if not isinstance(value, str) or not _DATE_RE.match(value):
        return False
    try:
        to_date(value)
        return True
    except ValueError:
        return False


def is_iso(value):
    if not isinstance(value, str):
        return False
    try:
        parse_iso(value)
        return True
    except ValueError:
        return False


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------

def fmt_offset(dt):
    off = dt.utcoffset() or timedelta(0)
    total = int(off.total_seconds() // 60)
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return "%s%02d:%02d" % (sign, total // 60, total % 60)


def fmt_iso(dt, seconds=False):
    """datetime -> ``YYYY-MM-DDTHH:MM+HH:MM`` (seconds dropped unless asked)."""
    if dt is None:
        return None
    dt = parse_iso(dt)
    body = dt.strftime("%Y-%m-%dT%H:%M:%S" if seconds else "%Y-%m-%dT%H:%M")
    return body + fmt_offset(dt)


def fmt_date(d):
    if d is None:
        return None
    return to_date(d).isoformat()


def fmt_hhmm(dt):
    return parse_iso(dt).strftime("%H:%M")


def iso_week(d):
    """date -> ``2026-W42``."""
    y, w, _ = to_date(d).isocalendar()
    return "%d-W%02d" % (y, w)


def week_start(d):
    """The Monday of the ISO week containing d."""
    d = to_date(d)
    return d - timedelta(days=d.weekday())


# --------------------------------------------------------------------------
# Weekdays
# --------------------------------------------------------------------------

def weekday_name(d, long=False):
    idx = to_date(d).weekday()
    return WEEKDAY_NAMES[idx] if long else WEEKDAYS[idx]


def weekday_index(name):
    """``Mon``/``monday``/``MO`` -> 0. Raises ValueError."""
    text = str(name).strip().lower()
    for i, full in enumerate(WEEKDAY_NAMES):
        if len(text) >= 2 and full.lower().startswith(text):
            return i
    raise ValueError("not a weekday: %r" % (name,))


def is_weekday_name(name):
    try:
        weekday_index(name)
        return True
    except (ValueError, TypeError):
        return False


def expand_days(value):
    """A list of day names, or ``"Mon-Fri"``/``"Mon,Tue,Thu"`` -> ``["Mon", ...]``."""
    if value is None:
        return []
    parts = value if isinstance(value, (list, tuple)) else str(value).split(",")
    out = []
    for part in parts:
        part = str(part).strip()
        if not part:
            continue
        if "-" in part:
            a, b = [p.strip() for p in part.split("-", 1)]
            i, j = weekday_index(a), weekday_index(b)
            k = i
            while True:
                if WEEKDAYS[k] not in out:
                    out.append(WEEKDAYS[k])
                if k == j:
                    break
                k = (k + 1) % 7
        else:
            name = WEEKDAYS[weekday_index(part)]
            if name not in out:
                out.append(name)
    return out


# --------------------------------------------------------------------------
# Arithmetic
# --------------------------------------------------------------------------

def plus(dt, hours=0, minutes=0, seconds=0):
    """dt plus an *elapsed* duration, kept in dt's time zone (right across a clock change)."""
    dt = parse_iso(dt)
    delta = timedelta(hours=hours, minutes=minutes, seconds=seconds)
    return (dt.astimezone(timezone.utc) + delta).astimezone(dt.tzinfo)


def hours_from(a, b):
    """Elapsed hours from a to b (positive when b is later), through UTC."""
    a, b = parse_iso(a), parse_iso(b)
    return (b.astimezone(timezone.utc) - a.astimezone(timezone.utc)).total_seconds() / 3600.0


def hours_between(a, b):
    """Hours from a to b (positive when b is later). Accepts strings. Elapsed hours."""
    return hours_from(a, b)


def minutes_between(a, b):
    return hours_from(a, b) * 60.0


def add_days(d, n):
    return to_date(d) + timedelta(days=n)


def days_between(a, b):
    """Whole days from date a to date b."""
    return (to_date(b) - to_date(a)).days


def at_time(d, hhmm, tz=None):
    """Combine a date and ``HH:MM`` into an aware datetime (tz name or tzinfo)."""
    if isinstance(tz, str) or tz is None:
        tzinfo = tz_for(tz) if tz else local_tz()
    else:
        tzinfo = tz
    return datetime.combine(to_date(d), parse_hhmm(hhmm)).replace(tzinfo=tzinfo)
