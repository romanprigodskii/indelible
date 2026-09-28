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
left out of the parse, but their flags and choices are still checked.

The docs also point at each other by section ("[close.md](close.md) §6 step 5",
"builder.md rule 4"), and the CLI prints such pointers too. A section moved or
renumbered would leave them pointing at nothing, so every pointer to a
reference's section must name a "## N." heading of that file, and a step must
be a "### Step N" heading or a numbered line inside it.
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
from lib import lint

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


def _marked(s):
    """``s`` with its placeholders marked as <ph>."""
    s = ANGLE_RE.sub("<ph>", s)               # before shlex: "<the learner's words>" holds an apostrophe
    return QUOTED_ELLIPSIS_RE.sub("<ph>", s)


def _words(s):
    """The words of ``s``, with any `…` left out (ValueError if shlex can't split it)."""
    return shlex.split(s.replace("…", " ").replace("...", " "))


def check_usage(parser, usage):
    """None if the usage fits the parser, else the reason it doesn't."""
    s = usage.split("<<")[0]
    # The optional groups stay out of the parse, but their flags are checked.
    optional = _marked(" ".join(g[1:-1] for g in OPTIONAL_RE.findall(s)))
    s = _marked(OPTIONAL_RE.sub("", s))
    elided = "…" in s or "..." in s
    try:
        tokens = _words(s)[1:]
        extra = _words(optional)
    except ValueError as exc:
        return "cannot be split into words (%s)" % exc
    return _check_tokens(parser, tokens, elided, extra)


def _check_options(p, path, words):
    """None if every --flag in ``words`` is one of p's options, with a valid literal choice."""
    for j, t in enumerate(words):
        if not t.startswith("--"):
            continue
        action = _option(p, t)
        if action is None:
            return "%s takes no option %s" % (" ".join(path), t)
        if action.choices and j + 1 < len(words):
            value = words[j + 1]
            if not _placeholder(value) and not value.startswith("--"):
                if any(v not in action.choices for v in value.split("|")):
                    return "%s %s: not one of %s" % (t, value, ", ".join(str(c) for c in action.choices))
    return None


def _check_tokens(parser, tokens, elided, optional=()):
    p, i, path = parser, 0, []
    while i < len(tokens) and _subparsers(p):
        subs = _subparsers(p)
        alts = tokens[i].split("|")
        if not all(a in subs for a in alts):
            break
        if len(alts) > 1:
            # "error repair|pass|fail" names three commands: check each.
            for a in alts:
                why = _check_tokens(parser, tokens[:i] + [a] + tokens[i + 1:], elided, optional)
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
    why = _check_options(p, path, rest) or _check_options(p, path, list(optional))
    if why:
        return why
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
            ("ind plan add <s> --kind K --start ISO --min N [--protectd]", "takes no option --protectd"),
            ("ind sheet lint <s> <id> [--budget 5]", "takes no option --budget"),
            ("ind session open <s> --planned 60 [--kind diag]", "not one of"),
            ("ind cal ics <out> --ops all|update", "not one of"),
            ("ind sheet sit <s> <id>", "no such command"),
            ("ind error repair|pass|drop", "no such command"),
            ("ind plan", "plan needs a subcommand"),
            ("ind session extend <s>", "required"),
        ):
            got = check_usage(self.parser, usage)
            self.assertIsNotNone(got, usage)
            self.assertIn(why, got, usage)


# "[close.md](close.md) §6 step 5", "session-grade.md §8", "sheets.md section 8".
FILE_POINTER_RE = re.compile(r"\b([a-z][a-z-]*)\.md\]?(?:\([^)\s]*\))?`? (?:§ ?(\d+)|section (\d+))(?: step (\d+))?")
# A bare "§3" in a reference points into that file, unless another file is named before it on the line.
BARE_POINTER_RE = re.compile(r"§ ?(\d+)(?: step (\d+))?")
OTHER_FILE_RE = re.compile(r"[A-Za-z-]+\.md|CONTRACT")
BUILDER_RULE_RE = re.compile(r"builder\.md(?:\]\([^)\s]*\))?`? rules? (\d+)")


def sections(text):
    """{N: the text of section "## N. …", up to the next "## " heading}."""
    found = {}
    for m in re.finditer(r"(?m)^## (\d+)\. ", text):
        end = re.search(r"(?m)^## ", text[m.end():])
        found[int(m.group(1))] = text[m.start():m.end() + (end.start() if end else len(text))]
    return found


class SectionPointers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.refs = {p.stem: sections(p.read_text(encoding="utf-8"))
                    for p in (SKILL_DIR / "references").glob("*.md")}
        cls.sources = (doc_files() + [SKILL_DIR.parents[1] / "dev" / "CONTRACT.md", SKILL_DIR.parents[1] / "README.md"]
                       + sorted((SKILL_DIR / "scripts").rglob("*.py")))

    def resolves(self, name, number, step):
        section = self.refs[name].get(int(number))
        if section is None:
            return False
        return step is None or bool(re.search(r"(?m)^### Step %s\b|^\s*%s\. " % (step, step), section))

    def test_every_pointer_to_another_file_names_a_section_it_has(self):
        bad, n = [], 0
        for path in self.sources:
            for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for m in FILE_POINTER_RE.finditer(line):
                    if m.group(1) not in self.refs:
                        continue
                    n += 1
                    if not self.resolves(m.group(1), m.group(2) or m.group(3), m.group(4)):
                        bad.append("%s:%d %s" % (path.name, no, m.group(0)))
        self.assertGreater(n, 150, "far fewer section pointers than expected: is the extraction broken?")
        self.assertEqual(bad, [], "pointers to a section or step that doesn't exist")

    def test_every_pointer_inside_a_reference_names_a_section_it_has(self):
        bad = []
        for path in (SKILL_DIR / "references").glob("*.md"):
            for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for m in BARE_POINTER_RE.finditer(line):
                    if OTHER_FILE_RE.search(line[:m.start()]):
                        continue
                    if not self.resolves(path.stem, m.group(1), m.group(2)):
                        bad.append("%s:%d %s" % (path.name, no, m.group(0)))
        self.assertEqual(bad, [], "pointers to a section or step that doesn't exist")

    def test_every_pointer_to_a_builder_rule_names_a_rule_it_has(self):
        builder = (SKILL_DIR / "assets" / "prompts" / "builder.md").read_text(encoding="utf-8")
        rules = set(re.findall(r"(?m)^(\d+)\. \*\*", builder.split("### Writing rules", 1)[1]))
        bad = []
        for path in self.sources:
            for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                bad += ["%s:%d %s" % (path.name, no, m.group(0)) for m in BUILDER_RULE_RE.finditer(line)
                        if m.group(1) not in rules]
        self.assertEqual(bad, [], "pointers to a builder.md writing rule that doesn't exist")


class CheckerRules(unittest.TestCase):
    """builder.md's checker table is the builder's copy of the lint rules; sheets.md §7 names them."""

    def test_the_builders_table_has_every_rule_in_order(self):
        builder = (SKILL_DIR / "assets" / "prompts" / "builder.md").read_text(encoding="utf-8")
        table = builder.split("### The checker", 1)[1].split("\n### ", 1)[0]
        rows = re.findall(r"^\| ((?:L|W)\d+)( [^|]+?)? \|", table, re.M)
        self.assertEqual([r for r, _ in rows], lint.RULES)
        for rule, title in rows:
            if rule.startswith("L"):
                self.assertEqual(title.strip().lower(), lint.TITLES[rule].lower(), rule)

    def test_sheets_md_names_every_rule_with_its_title(self):
        stub = sections((SKILL_DIR / "references" / "sheets.md").read_text(encoding="utf-8"))[7]
        for rule in lint.RULES:
            if rule.startswith("L"):
                self.assertIn(("%s %s" % (rule, lint.TITLES[rule])).lower(), stub.lower(), rule)
        self.assertIn("W1–W%d" % len([r for r in lint.RULES if r.startswith("W")]), stub)


class CheckForms(unittest.TestCase):
    """The forms of the written check are one table, in sheets.md §3; copies elsewhere drift apart."""

    def test_only_sheets_md_section_3_has_a_table_of_check_forms(self):
        found = []
        for path in doc_files():
            text = path.read_text(encoding="utf-8")
            for no, line in enumerate(text.splitlines(), 1):
                cells = [c.strip().lower() for c in line.strip().strip("|").split("|")] if line.startswith("|") else []
                if "the learner writes" in cells:
                    found.append((path.name, no))
        self.assertEqual(len(found), 1, "tables of check forms: %s" % found)
        sheets = (SKILL_DIR / "references" / "sheets.md").read_text(encoding="utf-8")
        self.assertIn("| The learner writes |", sections(sheets)[3])


if __name__ == "__main__":
    unittest.main()
