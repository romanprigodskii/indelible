"""File I/O for workspace data.

- Every file is UTF-8. Readers accept a BOM and ``\\r\\n``; writers emit ``\\n``.
- Snapshot files (``*.json`` and snapshot ``.jsonl``) are written to a temp
  file, then ``os.replace``d into place, retried up to 5 times at 100 ms. The
  previous version is kept as ``<name>.bak``.
- Append files get one ``write()`` per line plus a newline, then a flush.
- Bad JSONL lines never crash a reader: they are appended to
  ``<ws>/.indelible/quarantine.jsonl`` as ``{file, line_no, text}`` and skipped.
- ``write_lock(ws_root)`` is the workspace write lock, taken by every writing
  command: ``<ws>/.indelible/write.lock`` created with O_CREAT|O_EXCL, holding
  the pid and a timestamp, stale after 10 minutes.
"""

import json
import os
import shutil
import socket
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from lib import DataError, LockBusy

RETRIES = 5
RETRY_DELAY_S = 0.1
LOCK_STALE_S = 10 * 60
QUARANTINE_NAME = "quarantine.jsonl"
STATE_DIR_NAME = ".indelible"


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def ensure_dir(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _retry(fn, *args):
    last = None
    for attempt in range(RETRIES):
        try:
            return fn(*args)
        except PermissionError as exc:  # Windows: file briefly held open elsewhere
            last = exc
        except OSError as exc:
            if getattr(exc, "winerror", None) in (5, 32, 33):
                last = exc
            else:
                raise
        if attempt < RETRIES - 1:
            time.sleep(RETRY_DELAY_S)
    raise last


def bak_path(path):
    path = Path(path)
    return path.with_name(path.name + ".bak")


def dumps(obj, pretty=False):
    """JSON text for storage: UTF-8 characters kept, NaN refused."""
    if pretty:
        return json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

def read_text(path, default=None):
    """Read a UTF-8 text file (BOM accepted, newlines normalised to \\n)."""
    path = Path(path)
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8-sig", newline=None) as fh:
        return fh.read()


def read_json(path, default=None):
    """Read a JSON file. Missing file -> ``default``. Corrupt file -> DataError."""
    path = Path(path)
    text = read_text(path)
    if text is None:
        return default
    if not text.strip():
        return default
    try:
        return json.loads(text)
    except ValueError as exc:
        hint = ""
        if bak_path(path).exists():
            hint = " The previous version is at %s." % bak_path(path).name
        raise DataError("Cannot read %s: %s.%s" % (path, exc, hint))


def find_ws_root(path, max_up=6):
    """The nearest folder at or above ``path`` holding ``indelible.json``."""
    p = Path(path).resolve()
    if p.is_file() or not p.exists():
        p = p.parent
    for _ in range(max_up + 1):
        if (p / "indelible.json").is_file():
            return p
        if p.parent == p:
            break
        p = p.parent
    return None


def quarantine_path(ws_root):
    return Path(ws_root) / STATE_DIR_NAME / QUARANTINE_NAME


def _rel(path, root):
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def read_quarantine(ws_root):
    """Rows in the quarantine file (its own bad lines are ignored)."""
    text = read_text(quarantine_path(ws_root))
    rows = []
    if not text:
        return rows
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def quarantine_count(ws_root):
    return len(read_quarantine(ws_root))


def _quarantine(bad, path, ws_root):
    if ws_root is None:
        for line_no, text in bad:
            sys.stderr.write("indelible: skipped unreadable line %d in %s\n" % (line_no, path))
        return
    rel = _rel(path, ws_root)
    seen = set()
    for row in read_quarantine(ws_root):
        seen.add((row.get("file"), row.get("line_no"), row.get("text")))
    for line_no, text in bad:
        text = text[:4000]
        if (rel, line_no, text) in seen:
            continue
        append_jsonl(quarantine_path(ws_root), {"v": 1, "file": rel, "line_no": line_no, "text": text})
        seen.add((rel, line_no, text))


def read_jsonl(path, ws_root=None, quarantine=True):
    """Read a JSONL file into a list of dicts.

    A line that is not a JSON object is skipped and recorded in the workspace
    quarantine (found from ``ws_root`` or by walking up from ``path``). The
    same bad line is recorded only once.
    """
    path = Path(path)
    text = read_text(path)
    if not text:
        return []
    rows, bad = [], []
    for line_no, line in enumerate(text.split("\n"), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except ValueError:
            bad.append((line_no, line.rstrip("\r")))
            continue
        if not isinstance(obj, dict):
            bad.append((line_no, line.rstrip("\r")))
            continue
        rows.append(obj)
    if bad and quarantine:
        root = ws_root if ws_root is not None else find_ws_root(path)
        _quarantine(bad, path, root)
    return rows


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------

def _default_mode(path):
    """Keep an existing file's mode; new files get 0o666 minus the umask (mkstemp uses 0o600)."""
    try:
        return path.stat().st_mode & 0o777
    except OSError:
        pass
    mask = os.umask(0)
    os.umask(mask)
    return 0o666 & ~mask


def _atomic_write_text(path, text, mode=None, backup=True):
    path = Path(path)
    ensure_dir(path.parent)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        try:
            os.chmod(tmp, mode if mode is not None else _default_mode(path))
        except OSError:
            pass
        if backup and path.exists():
            _retry(shutil.copyfile, str(path), str(bak_path(path)))
            if mode is not None:
                try:
                    os.chmod(str(bak_path(path)), mode)
                except OSError:
                    pass
        _retry(os.replace, tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def write_text(path, text, mode=None, backup=True):
    """Atomically write a text file (UTF-8, \\n newlines), keeping ``.bak``."""
    if text and not text.endswith("\n"):
        text += "\n"
    return _atomic_write_text(path, text, mode=mode, backup=backup)


def write_json(path, data, mode=None, backup=True):
    """Atomically write a JSON snapshot (pretty, UTF-8), keeping ``.bak``."""
    return _atomic_write_text(path, dumps(data, pretty=True) + "\n", mode=mode, backup=backup)


def write_jsonl(path, rows, mode=None, backup=True):
    """Atomically write a snapshot JSONL file: one compact object per line."""
    text = "".join(dumps(r) + "\n" for r in rows)
    return _atomic_write_text(path, text, mode=mode, backup=backup)


write_jsonl_snapshot = write_jsonl


def append_jsonl(path, row):
    """Append one record: a single ``write()`` of the line plus newline, flushed."""
    if not isinstance(row, dict):
        raise TypeError("append_jsonl expects a dict")
    path = Path(path)
    ensure_dir(path.parent)
    line = dumps(row) + "\n"
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    if size:
        with open(path, "rb") as fh:
            fh.seek(-1, os.SEEK_END)
            if fh.read(1) != b"\n":
                line = "\n" + line  # never glue a record onto a torn last line
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(line)
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass
    return path


def touch(path):
    """Create an empty file if it does not exist (never truncates)."""
    path = Path(path)
    ensure_dir(path.parent)
    if not path.exists():
        with open(path, "a", encoding="utf-8", newline="\n"):
            pass
    return path


# --------------------------------------------------------------------------
# Workspace write lock
# --------------------------------------------------------------------------

_HELD = {}  # lock path -> depth, for re-entry within one process


def _pid_alive(pid):
    if os.name != "posix":
        return True  # no safe probe on Windows; rely on the 10-minute rule
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def read_lock_info(lock_path):
    lock_path = Path(lock_path)
    info = {}
    try:
        text = read_text(lock_path) or ""
        info = json.loads(text) if text.strip() else {}
        if not isinstance(info, dict):
            info = {}
    except (ValueError, OSError):
        info = {}
    if "epoch" not in info:
        try:
            info["epoch"] = lock_path.stat().st_mtime
        except OSError:
            info["epoch"] = time.time()
    return info


def lock_is_stale(info, stale_after=LOCK_STALE_S):
    age = time.time() - float(info.get("epoch") or 0)
    if age > stale_after:
        return True
    pid = info.get("pid")
    if isinstance(pid, int) and info.get("host") == socket.gethostname() and pid != os.getpid():
        return not _pid_alive(pid)
    return False


class WriteLock(object):
    """Context manager for ``<ws>/.indelible/write.lock``.

    Re-entrant within one process. Waits up to ``timeout`` seconds for another
    process, takes over a stale lock, and raises LockBusy otherwise.
    """

    def __init__(self, ws_root, timeout=3.0, stale_after=LOCK_STALE_S):
        self.path = Path(ws_root) / STATE_DIR_NAME / "write.lock"
        self.timeout = timeout
        self.stale_after = stale_after
        self._key = str(self.path.resolve()) if self.path.parent.exists() else str(self.path)

    def acquire(self):
        ensure_dir(self.path.parent)
        self._key = str(self.path.resolve())
        if _HELD.get(self._key):
            _HELD[self._key] += 1
            return self
        deadline = time.time() + self.timeout
        payload = dumps({
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "epoch": time.time(),
        })
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                info = read_lock_info(self.path)
                if lock_is_stale(info, self.stale_after):
                    self._take_over(info)
                    continue
                if time.time() >= deadline:
                    raise LockBusy(
                        "The workspace is busy: another indelible command holds %s "
                        "(pid %s since %s). Wait for it to finish; a lock older than "
                        "10 minutes is cleared automatically."
                        % (self.path, info.get("pid", "?"), info.get("at", "?"))
                    )
                time.sleep(0.1)
                continue
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(payload + "\n")
            _HELD[self._key] = 1
            return self

    def _take_over(self, info):
        """Remove a stale lock atomically: rename it aside, and only if the renamed file is
        still the stale lock that was judged (same pid, host and epoch) is it dropped.
        If another process took the lock over in between, its fresh lock is put back
        (never deleted), and the caller simply tries again."""
        aside = self.path.with_name("%s.stale-%d-%s" % (self.path.name, os.getpid(), os.urandom(4).hex()))
        try:
            os.rename(str(self.path), str(aside))
        except OSError:
            return  # already gone or taken over: try again
        moved = read_lock_info(aside)
        same = all(moved.get(k) == info.get(k) for k in ("pid", "host", "epoch"))
        if same:
            try:
                os.unlink(str(aside))
            except OSError:
                pass
            return
        # We moved someone's fresh lock: put it back without overwriting a newer one.
        try:
            os.link(str(aside), str(self.path))
            os.unlink(str(aside))
        except (OSError, AttributeError, NotImplementedError):
            if not self.path.exists():
                try:
                    os.rename(str(aside), str(self.path))
                    return
                except OSError:
                    pass
            try:
                os.unlink(str(aside))
            except OSError:
                pass

    def release(self):
        depth = _HELD.get(self._key, 0)
        if depth > 1:
            _HELD[self._key] = depth - 1
            return
        _HELD.pop(self._key, None)
        try:
            info = read_lock_info(self.path)
            if info.get("pid") in (None, os.getpid()):
                os.unlink(str(self.path))
        except OSError:
            pass

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False


def write_lock(ws_root, timeout=3.0, stale_after=LOCK_STALE_S):
    """``with write_lock(ws.root): ...``"""
    return WriteLock(ws_root, timeout=timeout, stale_after=stale_after)
