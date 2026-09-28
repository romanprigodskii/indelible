"""dev/CONTRACT.md §7 against the CLI's own parser.

The contract says it wins when the code disagrees, so whatever the code grows
must reach it too. Every command the parser registers has a synopsis in §7: a
backticked span that starts with the command's words, such as
`sheet lint <subject> <id> [--budget-min N]`. A command's synopses together
name every long option it takes, and none it lacks. The sheet checker's rule
ids and the close check's promise words are compared the same way.
"""

import argparse
import re
import unittest

try:
    from helpers import REPO_DIR
except ImportError:  # run as part of the tests package
    from tests.helpers import REPO_DIR

import indelible  # helpers put scripts/ on sys.path
from lib import cmd_session, lint

CONTRACT = REPO_DIR / "dev" / "CONTRACT.md"
FENCE_RE = re.compile(r"(?ms)^[ \t]*```.*?^[ \t]*```")
SPAN_RE = re.compile(r"`([^`\n]+)`")
FLAG_RE = re.compile(r"--[a-z][a-z0-9-]*")
# Every command takes these; §7 says so once, at the top.
COMMON_OPTIONS = {"--help", "--workspace"}
FIX = "; bring dev/CONTRACT.md §7 in step with the code"


def _subparsers(parser):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    return None


def leaf_commands(parser):
    """{"sheet lint": its parser, ...}: every command path that takes no further subcommand."""
    found = {}

    def walk(p, path):
        subs = _subparsers(p)
        if subs:
            for name, sub in subs.items():
                walk(sub, path + [name])
        elif path:
            found[" ".join(path)] = p

    walk(parser, [])
    return found


def long_options(parser):
    return set(o for a in parser._actions for o in a.option_strings if o.startswith("--")) - COMMON_OPTIONS


def contract_section(number):
    """The text of one numbered section of the contract (up to the next one)."""
    text = CONTRACT.read_text(encoding="utf-8")
    start = text.index("\n## %d. " % number)
    return text[start:text.index("\n## %d. " % (number + 1), start)]


class ContractCli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parser = indelible.build_parser(warn=False)
        cls.commands = leaf_commands(cls.parser)
        # A fenced block's backticks would pair with a span's, so fences go first.
        cls.spans = SPAN_RE.findall(FENCE_RE.sub("", contract_section(7)))

    def synopses(self, command):
        return [s for s in self.spans if s == command or s.startswith(command + " ")]

    def test_every_command_module_is_loaded(self):
        # build_parser skips a module that fails to import, and its commands with it.
        self.assertEqual(self.parser.get_default("_loaded_modules"), indelible.command_modules())
        self.assertIn("sheet lint", self.commands)
        self.assertIn("ledger add owed", self.commands)

    def test_every_command_has_a_synopsis(self):
        missing = sorted(c for c in self.commands if not self.synopses(c))
        self.assertEqual(missing, [], "commands with no synopsis in §7" + FIX)

    def test_the_synopses_name_every_option(self):
        gaps = []
        for command, p in sorted(self.commands.items()):
            named = set(f for s in self.synopses(command) for f in FLAG_RE.findall(s))
            missing = sorted(long_options(p) - named)
            if missing:
                gaps.append("%s: %s" % (command, ", ".join(missing)))
        self.assertEqual(gaps, [], "options no synopsis names" + FIX)

    def test_no_synopsis_names_an_option_the_command_lacks(self):
        extra = []
        for s in self.spans:
            words = s.split()
            for n in (3, 2, 1):
                command = " ".join(words[:n])
                if command in self.commands:
                    unknown = sorted(set(FLAG_RE.findall(s)) - long_options(self.commands[command]))
                    if unknown:
                        extra.append("`%s`: %s" % (s, ", ".join(unknown)))
                    break
        self.assertEqual(extra, [], "options the command does not take" + FIX)

    def test_the_checker_rules_match(self):
        text = contract_section(7)
        rows = re.findall(r"^  \| (L\d+) ([^|]+?) \|", text, re.M)
        warns = re.findall(r"^  - (W\d+):", text, re.M)
        self.assertEqual([r for r, _ in rows] + warns, lint.RULES)
        for rule, title in rows:
            self.assertEqual(title, lint.TITLES[rule], rule)

    def test_the_promise_words_match(self):
        pattern = "`%s`" % cmd_session.PROMISE_RE.pattern
        self.assertTrue(pattern in contract_section(7), "C6 should give the regex %s%s" % (pattern, FIX))


if __name__ == "__main__":
    unittest.main()
