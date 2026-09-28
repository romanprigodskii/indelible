"""The `ind …` usages in SKILL.md, the references and builder.md against the CLI parser.

The docs are how Claude learns the CLI, so a renamed flag or a typo there
becomes a usage error (exit 2) in the middle of a session. Every backticked
`ind …` span and every `ind …` line in a fenced block is checked:

- its command path resolves to a command that takes no further subcommand;
- every `--flag` in it is one of that command's own options, spelt in full
  (argparse would accept `--budget` for `--budget-min`, so parsing alone is
  not enough);
- a literal value after an option with choices is one of them;
- a complete usage (nothing elided with `…`) parses, with each placeholder
  filled from the option before it.

Placeholders are `<…>`, a quoted string holding `…`, and the words N, ISO,
DATE, TEXT, MIN or a single capital letter. Optional `[--opt …]` groups are
left out.
"""

import argparse
import contextlib
import io
import re
import shlex
import unittest

try:
    from helpers import SKILL_DIR
except ImportError:  # run as part of the tests package
    from tests.helpers import SKILL_DIR

import indelible  # helpers put scripts/ on sys.path

SPAN_RE = re.compile(r"`(ind [^`]+)`")
FENCE_RE = re.compile(r"^\s*```")
LINE_RE = re.compile(r"^\s*(ind \S.*)$")
OPTIONAL_RE = re.compile(r"\[--[^\]]*\]")
ANGLE_RE = re.compile(r"<[^>]*>")
QUOTED_ELLIPSIS_RE = re.compile("'[^']*…[^']*'|\"[^\"]*…[^\"]*\"")
PLACEHOLDER_RE = re.compile(r"^(<ph>|[A-Z]|N|ISO|DATE|TEXT|MIN)$")
FILL_ISO = "2026-10-15T07:00"
FILL_NUMBER = "60"
FILL_TEXT = "x"


def doc_files():
    return ([SKILL_DIR / "SKILL.md", SKILL_DIR / "assets" / "prompts" / "builder.md"]
            + sorted((SKILL_DIR / "references").glob("*.md")))


def usages(path):
    """(line number, usage) for every backticked `ind …` span and fenced `ind …` line."""
    found, fenced = [], False
    for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if FENCE_RE.match(line):
            fenced = not fenced
            continue
        found += [(no, s) for s in SPAN_RE.findall(line)]
        m = LINE_RE.match(line) if fenced else None
        if m:
            found.append((no, m.group(1)))
    return found


def _subparsers(parser):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    return None


def _option(parser, flag):
    for action in parser._actions:
        if flag in action.option_strings:
            return action
    return None


def _placeholder(token):
    return bool(PLACEHOLDER_RE.match(token))


def _fill(action, prev):
    """A value for a placeholder that follows ``prev`` (an option name, or None)."""
    if action is not None and action.choices:
        return list(action.choices)[0]
    if action is not None and action.type in (int, float):
        return FILL_NUMBER
    if prev == "--start":
        return FILL_ISO
    return FILL_TEXT


def check_usage(parser, usage):
    """None if the usage fits the parser, else the reason it doesn't."""
    s = OPTIONAL_RE.sub("", usage.split("<<")[0])
    s = ANGLE_RE.sub("<ph>", s)               # before shlex: "<the learner's words>" holds an apostrophe
    s = QUOTED_ELLIPSIS_RE.sub("<ph>", s)
    elided = "…" in s or "..." in s
    s = s.replace("…", " ").replace("...", " ")
    try:
        tokens = shlex.split(s)[1:]
    except ValueError as exc:
        return "cannot be split into words (%s)" % exc
    return _check_tokens(parser, tokens, elided)


def _check_tokens(parser, tokens, elided):
    p, i, path = parser, 0, []
    while i < len(tokens) and _subparsers(p):
        subs = _subparsers(p)
        alts = tokens[i].split("|")
        if not all(a in subs for a in alts):
            break
        if len(alts) > 1:
            # "error repair|pass|fail" names three commands: check each.
            for a in alts:
                why = _check_tokens(parser, tokens[:i] + [a] + tokens[i + 1:], elided)
                if why:
                    return why
            return None
        p = subs[tokens[i]]
        path.append(tokens[i])
        i += 1
    if _subparsers(p):
        if i >= len(tokens):
            return "%s needs a subcommand" % " ".join(path)
        return "no such command: %s" % " ".join(tokens[:i + 1])
    rest = tokens[i:]
    for j, t in enumerate(rest):
        if not t.startswith("--"):
            continue
        action = _option(p, t)
        if action is None:
            return "%s takes no option %s" % (" ".join(path), t)
        if action.choices and j + 1 < len(rest):
            value = rest[j + 1]
            if not _placeholder(value) and not value.startswith("--"):
                if any(v not in action.choices for v in value.split("|")):
                    return "%s %s: not one of %s" % (t, value, ", ".join(str(c) for c in action.choices))
    if elided or not rest or all(t.startswith("--") for t in rest):
        return None
    argv, prev = list(path), None
    for t in rest:
        if _placeholder(t):
            t = _fill(_option(p, prev) if prev else None, prev)
        argv.append(t)
        prev = t if t.startswith("--") else None
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        try:
            parser.parse_args(argv)
        except SystemExit as exc:
            if exc.code:
                lines = err.getvalue().strip().splitlines()
                return lines[-1] if lines else "does not parse"
    return None


class DocUsages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parser = indelible.build_parser(warn=False)

    def test_every_documented_usage_fits_the_cli(self):
        failures, n = [], 0
        for path in doc_files():
            for no, usage in usages(path):
                n += 1
                why = check_usage(self.parser, usage)
                if why:
                    failures.append("%s:%d `%s`: %s" % (path.relative_to(SKILL_DIR).as_posix(), no, usage, why))
        self.assertGreater(n, 300, "the docs hold far fewer `ind` usages than expected: is the extraction broken?")
        self.assertEqual(failures, [], "documented usages the CLI would refuse")

    def test_the_checker_passes_good_usages(self):
        for usage in (
            "ind sheet lint <s> <id> --budget-min <remaining> --json",
            "ind plan add <subject> --kind K --start ISO --min N [--protected] [--content TEXT]",
            "ind session open <subject> --planned 60 --kind <the block's kind>",
            "ind error repair|pass|fail",
            "ind grade record … --shaky",
            "ind cal ics <ws>/plan/ics/study.ics --ops create",
            "ind ledger add decision --subject <s> --summary \"…\" --why \"<their words>\" --check-on DATE",
            "ind scan ingest stats stats-cold-04 --transcript - <<'EOF'",
        ):
            self.assertIsNone(check_usage(self.parser, usage), usage)

    def test_the_checker_catches_broken_usages(self):
        for usage, why in (
            ("ind sheet lint <s> <id> --budget 5", "takes no option --budget"),       # truncated flag
            ("ind plan add <s> --kind K --start ISO --minutes 60", "takes no option --minutes"),
            ("ind session open <s> --planned 60 --kind diag", "not one of"),
            ("ind cal ics <out> --ops all|update", "not one of"),
            ("ind sheet sit <s> <id>", "no such command"),
            ("ind error repair|pass|drop", "no such command"),
            ("ind plan", "plan needs a subcommand"),
            ("ind session extend <s>", "required"),
        ):
            got = check_usage(self.parser, usage)
            self.assertIsNotNone(got, usage)
            self.assertIn(why, got, usage)


if __name__ == "__main__":
    unittest.main()
