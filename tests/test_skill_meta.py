"""The SKILL.md frontmatter fits the Agent Skills limits, a session's instructions fit their
budget, and the trigger evals are well formed.

The Agent Skills format caps the description at 1,024 characters and
compatibility at 500. The description decides when the skill starts, and it
sits close to its cap, so an edit that adds a trigger must not quietly push
it past.

A study session loads SKILL.md and five references (session-open, -grade and
-teach, sheets and close), and every character of them is paid for again in
each session and after each compaction. Their total is capped at 110,000
characters: material only the builder reads belongs in builder.md, and a rule
is said once, in the file that owns it.

evals/trigger.json can only be run with a model (README.md, "Contributing"),
so no test here says whether a prompt triggers. These tests check what can go
wrong without one: every entry has a query and a true/false label, no query is
listed twice, and both labels are there.
"""

import json
import re
import unittest

try:
    from helpers import REPO_DIR, SKILL_DIR
except ImportError:  # run as part of the tests package
    from tests.helpers import REPO_DIR, SKILL_DIR

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)
TOP_LEVEL_RE = re.compile(r"^([a-z][a-z-]*):\s*(.*)$")
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

DESCRIPTION_MAX = 1024
COMPATIBILITY_MAX = 500
NAME_MAX = 64
SESSION_FILES = ("SKILL.md", "references/session-open.md", "references/session-grade.md",
                 "references/session-teach.md", "references/sheets.md", "references/close.md")
SESSION_LOAD_MAX = 110000


def frontmatter():
    """The top-level `key: value` fields of SKILL.md; a quoted value is read as JSON."""
    m = FRONTMATTER_RE.match((SKILL_DIR / "SKILL.md").read_text(encoding="utf-8"))
    if not m:
        raise AssertionError("SKILL.md has no frontmatter between two '---' lines")
    fields = {}
    for line in m.group(1).splitlines():
        t = TOP_LEVEL_RE.match(line)
        if not t:
            continue
        key, value = t.group(1), t.group(2).strip()
        fields[key] = json.loads(value) if value.startswith('"') else value
    return fields


class Frontmatter(unittest.TestCase):
    def setUp(self):
        self.fm = frontmatter()

    def test_name_is_the_folder_name(self):
        name = self.fm.get("name")
        self.assertEqual(name, SKILL_DIR.name)
        self.assertRegex(name, NAME_RE)
        self.assertLessEqual(len(name), NAME_MAX)

    def test_description_fits_its_limit(self):
        d = self.fm.get("description")
        self.assertIsInstance(d, str)
        self.assertTrue(d.strip(), "the description is empty")
        self.assertLessEqual(len(d), DESCRIPTION_MAX,
                             "the description is %d characters; the limit is %d" % (len(d), DESCRIPTION_MAX))

    def test_compatibility_fits_its_limit(self):
        c = self.fm.get("compatibility")
        self.assertIsInstance(c, str)
        self.assertLessEqual(len(c), COMPATIBILITY_MAX,
                             "compatibility is %d characters; the limit is %d" % (len(c), COMPATIBILITY_MAX))


class SessionLoad(unittest.TestCase):
    def test_a_sessions_instructions_fit_their_budget(self):
        sizes = dict((name, len((SKILL_DIR / name).read_text(encoding="utf-8"))) for name in SESSION_FILES)
        total = sum(sizes.values())
        self.assertLessEqual(total, SESSION_LOAD_MAX, "a session loads %d characters (%s); the budget is %d" % (
            total, ", ".join("%s %d" % (n.split("/")[-1], s) for n, s in sizes.items()), SESSION_LOAD_MAX))

    def test_the_session_route_loads_session_grade_when_no_recheck_did(self):
        # A session with nothing due has no recheck, so session-grade is first needed when a
        # practice sheet comes back; the route must not call it "already loaded" then.
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        row = [ln for ln in skill.splitlines() if ln.startswith("| `session [subject]`")][0]
        self.assertNotIn("already loaded", row)
        self.assertIn("session-grade, loaded at the recheck or the first sheet back, marks each later sheet", row)


class TriggerEvals(unittest.TestCase):
    def setUp(self):
        with open(REPO_DIR / "evals" / "trigger.json", encoding="utf-8") as f:
            self.cases = json.load(f)

    def test_every_entry_has_a_query_and_a_label(self):
        self.assertIsInstance(self.cases, list)
        for i, case in enumerate(self.cases):
            self.assertIsInstance(case, dict, "entry %d" % i)
            self.assertEqual(set(case), {"query", "should_trigger"}, "entry %d" % i)
            self.assertIsInstance(case["query"], str, "entry %d" % i)
            self.assertTrue(case["query"].strip(), "entry %d has an empty query" % i)
            self.assertIsInstance(case["should_trigger"], bool, "entry %d" % i)

    def test_no_query_is_listed_twice(self):
        seen = {}
        for i, case in enumerate(self.cases):
            key = " ".join(case["query"].split()).casefold()
            self.assertFalse(key in seen, "entries %s and %d have the same query" % (seen.get(key), i))
            seen[key] = i

    def test_both_labels_are_there(self):
        labels = [case["should_trigger"] for case in self.cases]
        self.assertIn(True, labels)
        self.assertIn(False, labels)


if __name__ == "__main__":
    unittest.main()
