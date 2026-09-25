#!/usr/bin/env python3
"""indelible: the command-line core of the indelible study skill.

Usage: python3 indelible.py [--workspace PATH] <command> ...

Commands are registered automatically: every module ``lib/cmd_*.py`` that
defines ``register(subparsers)`` adds its subcommands. A module that fails to
import is skipped with a one-line warning, so a partial install still runs.

Handler convention (for ``lib/cmd_*.py``)::

    def register(subparsers):
        p = subparsers.add_parser("doctor", help="...")
        p.add_argument("--json", action="store_true")
        p.set_defaults(func=cmd_doctor)

    def cmd_doctor(args):        # returns an int exit code
        ...
        return 0

``--workspace`` is accepted before the command and after it, on every
subcommand. Exit codes: 0 OK, 1 a gate or check failed, 2 usage or
unexpected error. Python 3.9+, standard library only.
"""

import argparse
import importlib
import os
import sys
import traceback
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from lib import IndelibleError, VERSION, EXIT_FAIL, EXIT_USAGE  # noqa: E402

PROG = "indelible.py"


def _reconfigure_streams():
    """UTF-8 on every stream, whatever the locale says (cp1252 pipes on Windows).

    stdin is decoded as UTF-8 too (a BOM is dropped), so a transcript or typed
    answers piped in are stored as written.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
    try:
        sys.stdin.reconfigure(encoding="utf-8-sig", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass


def command_modules():
    """Names of the ``lib/cmd_*.py`` modules, sorted."""
    lib_dir = SCRIPTS_DIR / "lib"
    return sorted(p.stem for p in lib_dir.glob("cmd_*.py") if p.is_file())


def _add_workspace_everywhere(parser):
    """Give every (sub)parser a ``--workspace`` option that does not reset the global one."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for sub in set(action.choices.values()):
                if "--workspace" not in sub._option_string_actions:
                    sub.add_argument("--workspace", dest="workspace", default=argparse.SUPPRESS,
                                     metavar="PATH", help="the workspace folder (default: discovered)")
                _add_workspace_everywhere(sub)


def build_parser(warn=True):
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="indelible: learning that survives the cold test. "
                    "Files are read and written only inside the learner's workspace.",
    )
    parser.add_argument("--workspace", metavar="PATH", default=None,
                        help="the workspace folder (default: discovered)")
    parser.add_argument("--version", action="version", version="indelible " + VERSION)
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    loaded = []
    for name in command_modules():
        try:
            module = importlib.import_module("lib." + name)
        except Exception as exc:  # a broken module must not break the others
            if warn:
                sys.stderr.write("indelible: skipped %s (%s: %s)\n" % (name, type(exc).__name__, exc))
            continue
        register = getattr(module, "register", None)
        if not callable(register):
            continue
        try:
            register(subparsers)
            loaded.append(name)
        except Exception as exc:
            if warn:
                sys.stderr.write("indelible: skipped %s (register failed: %s: %s)\n"
                                 % (name, type(exc).__name__, exc))
    _add_workspace_everywhere(parser)
    parser.set_defaults(_loaded_modules=loaded)
    return parser


def registered_commands(parser):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return sorted(action.choices)
    return []


def dispatch(parser, argv):
    """Parse argv and run the handler. Returns an exit code."""
    args = parser.parse_args(argv)
    if getattr(args, "workspace", None) is None:
        # A subcommand that declares its own --workspace (default None) would
        # otherwise hide a global one given before the command name.
        pre = argparse.ArgumentParser(add_help=False)
        pre.add_argument("--workspace", default=None)
        known, _ = pre.parse_known_args(argv)
        args.workspace = known.workspace
    func = getattr(args, "func", None) or getattr(args, "handler", None)
    if func is None:
        if not getattr(args, "command", None):
            parser.print_usage(sys.stderr)
            cmds = registered_commands(parser)
            sys.stderr.write("indelible: choose a command: %s\n" % (", ".join(cmds) or "(none loaded)"))
        else:
            sys.stderr.write("indelible: '%s' needs a subcommand; run: %s %s -h\n"
                             % (args.command, PROG, args.command))
        return EXIT_USAGE
    args._parser = parser
    try:
        rc = func(args)
    except IndelibleError as exc:
        stream = sys.stdout if exc.exit_code == EXIT_FAIL else sys.stderr
        stream.write(str(exc).rstrip("\n") + "\n")
        stream.flush()
        return exc.exit_code
    if rc is None:
        return 0
    if isinstance(rc, bool):
        return 0 if rc else EXIT_FAIL
    return int(rc)


def main(argv=None):
    _reconfigure_streams()
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        parser = build_parser()
        return dispatch(parser, argv)
    except SystemExit as exc:  # argparse errors and --help
        code = exc.code
        if code is None:
            return 0
        return code if isinstance(code, int) else EXIT_USAGE
    except KeyboardInterrupt:
        sys.stderr.write("indelible: interrupted\n")
        return EXIT_USAGE
    except BrokenPipeError:
        return 0
    except IndelibleError as exc:
        stream = sys.stdout if exc.exit_code == EXIT_FAIL else sys.stderr
        stream.write(str(exc).rstrip("\n") + "\n")
        return exc.exit_code
    except Exception as exc:
        sys.stderr.write("indelible: %s\n" % (exc,))
        if os.environ.get("INDELIBLE_DEBUG"):
            traceback.print_exc()
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
