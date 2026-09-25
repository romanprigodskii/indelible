"""indelible core library.

Every command module (``lib/cmd_*.py``) imports from here. This file stays
light: it defines the package paths and the error types that the entry point
turns into exit codes, and imports nothing else from the package.

Exit codes (shared by every command):
    0  OK
    1  a gate or check FAILED (expected; the message goes to stdout)
    2  usage error or unexpected error (the message goes to stderr)
"""

from pathlib import Path

VERSION = "0.1.0"
SCHEMA_VERSION = 1

LIB_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = LIB_DIR.parent
SKILL_DIR = SCRIPTS_DIR.parent
ASSETS_DIR = SKILL_DIR / "assets"
WORKSPACE_ASSETS = ASSETS_DIR / "workspace"
LISTS_DIR = ASSETS_DIR / "lists"
TEMPLATES_DIR = ASSETS_DIR / "templates"

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2


class IndelibleError(Exception):
    """Base error. ``exit_code`` decides the exit status and the stream.

    Exit code 1 messages are printed to stdout (they describe a failed gate);
    exit code 2 messages are printed to stderr.
    """

    exit_code = EXIT_USAGE

    def __init__(self, message, exit_code=None):
        Exception.__init__(self, message)
        if exit_code is not None:
            self.exit_code = exit_code


class UsageError(IndelibleError):
    """Bad arguments, unknown subject, missing file: exit 2."""

    exit_code = EXIT_USAGE


class CheckFailed(IndelibleError):
    """A gate or check failed: exit 1, message on stdout."""

    exit_code = EXIT_FAIL


# Alias: some modules read better with "gate".
GateFailed = CheckFailed


class NoWorkspace(UsageError):
    """No workspace could be found (exit 2)."""

    MESSAGE = "No indelible workspace found. Run: indelible.py init <path>"

    def __init__(self, detail=None):
        msg = self.MESSAGE
        if detail:
            msg = msg + "\n" + detail
        UsageError.__init__(self, msg)


class LockBusy(IndelibleError):
    """Another indelible command holds the workspace write lock (exit 2)."""

    exit_code = EXIT_USAGE


class DataError(IndelibleError):
    """A data file cannot be read or is structurally wrong (exit 2)."""

    exit_code = EXIT_USAGE
